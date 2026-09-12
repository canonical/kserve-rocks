import http.server
import logging
import shlex
import socket
import subprocess
import threading
import time

import pytest
import requests
from charmed_kubeflow_chisme.rock import CheckRock

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_HF_HOME_CONTAINER = "/tmp/huggingface"
_MODEL = "facebook/opt-125m"
_SERVER_PORT_CONTAINER = 8000
_STARTUP_TIMEOUT_SECONDS = 600
_POLL_INTERVAL_SECONDS = 10
# Log forwarding surfaces logs during container startup (well before the model
# finishes loading), so it needs a shorter budget than full server readiness.
_LOG_FORWARDING_TIMEOUT_SECONDS = 300


def _free_port() -> int:
    """Return an available TCP port on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def vllm_server():
    """Start the vllm-cpu container and yield its base URL; stop it on teardown."""
    check_rock = CheckRock("rockcraft.yaml")
    local_rock_image = f"{check_rock.get_name()}:{check_rock.get_version()}"

    port = _free_port()
    logger.info(
        f"Starting vLLM server container on port {port} using image {local_rock_image}"
    )

    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "-p",
            f"{port}:{_SERVER_PORT_CONTAINER}",
            "-e",
            f"HF_HOME={_HF_HOME_CONTAINER}",
            local_rock_image,
            "--model",
            _MODEL,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    container_id = result.stdout.strip()
    logger.info(f"Started container {container_id} for vLLM server")

    try:
        yield f"http://localhost:{port}"
    finally:
        subprocess.run(["docker", "stop", container_id], check=False)
        subprocess.run(["docker", "rm", container_id], check=False)


@pytest.mark.abort_on_fail
def test_rock():
    """Test that the vllm-cpu rock contains the expected files."""
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    local_rock_image = f"{rock_image}:{rock_version}"

    # Paths that must exist inside the rock
    paths = [
        "/opt/venv/bin/vllm",
        "/opt/venv/bin/vllm-original",
        "/opt/venv/bin/python",
        "/opt/venv/lib/python3.12/site-packages/vllm",
        "/opt/uv",
        "/opt/pebble/vllmd.sh",
        "/opt/pebble/log-layer.yaml",
    ]

    for p in paths:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "/bin/bash",
                local_rock_image,
                "-c",
                f"ls -la {shlex.quote(p)}",
            ],
            check=True,
        )


@pytest.mark.abort_on_fail
def test_vllm_wrapper_symlink():
    """`/opt/venv/bin/vllm` is a wrapper that routes through the Pebble service script.

    The command is a symlink to /opt/pebble/vllmd.sh, which forwards logs (when
    LOKI_URL is set) and then execs the real binary /opt/venv/bin/vllm-original.
    This keeps `vllm serve ...` (the upstream image entrypoint and KServe
    manifests) working against the rock.
    """
    check_rock = CheckRock("rockcraft.yaml")
    local_rock_image = f"{check_rock.get_name()}:{check_rock.get_version()}"

    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            local_rock_image,
            "-c",
            "readlink /opt/venv/bin/vllm",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (
        result.stdout.strip() == "/opt/pebble/vllmd.sh"
    ), f"Expected /opt/venv/bin/vllm to symlink to /opt/pebble/vllmd.sh, got: {result.stdout!r}"


@pytest.mark.abort_on_fail
def test_log_forwarding_assets():
    """The Pebble log-forwarding assets are present and well-formed."""
    check_rock = CheckRock("rockcraft.yaml")
    local_rock_image = f"{check_rock.get_name()}:{check_rock.get_version()}"

    # The wrapper script that renders the log layer is executable.
    subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            local_rock_image,
            "-c",
            "test -x /opt/pebble/vllmd.sh",
        ],
        check=True,
    )

    # The log-layer template declares a Loki log target.
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            local_rock_image,
            "-c",
            "cat /opt/pebble/log-layer.yaml",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert (
        "log-targets:" in result.stdout
    ), f"Expected 'log-targets:' in log-layer.yaml, got: {result.stdout!r}"
    assert (
        "type: loki" in result.stdout
    ), f"Expected 'type: loki' in log-layer.yaml, got: {result.stdout!r}"


@pytest.mark.abort_on_fail
def test_vllm_version():
    """Test that the vllm binary reports the expected version."""
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    local_rock_image = f"{rock_image}:{rock_version}"

    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/opt/venv/bin/vllm",
            local_rock_image,
            "--version",
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert (
        "0.19.0" in result.stdout
    ), f"Expected vllm version 0.19.0 in output, got: {result.stdout!r}"


@pytest.mark.abort_on_fail
def test_endpoint_completions(vllm_server):
    """Test that the vLLM server responds correctly to a completions request."""
    base_url = vllm_server
    logger.info(f"Testing vLLM server at {base_url}")
    # Wait for the server to become ready
    deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
    while True:
        try:
            resp = requests.get(f"{base_url}/health", timeout=5)
            if resp.status_code == 200:
                break
        except requests.ConnectionError:
            pass

        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"vLLM server did not become healthy within {_STARTUP_TIMEOUT_SECONDS}s"
            )
        time.sleep(_POLL_INTERVAL_SECONDS)

    logger.info("vLLM server is healthy, sending completions request")
    # Send a completions request matching the README example
    response = requests.post(
        f"{base_url}/v1/completions",
        headers={"Content-Type": "application/json"},
        json={
            "model": _MODEL,
            "prompt": "The capital of France is",
            "max_tokens": 20,
        },
        timeout=60,
    )

    logger.info(
        f"Received completions response from vLLM server: {response.status_code} {response.text!r}"
    )
    assert (
        response.status_code == 200
    ), f"Expected HTTP 200 from /v1/completions, got {response.status_code}: {response.text!r}"

    body = response.json()
    logger.info(f"Parsed JSON body from completions response: {body!r}")
    assert (
        "choices" in body and len(body["choices"]) > 0
    ), f"Expected non-empty 'choices' in response, got: {body!r}"
    text = body["choices"][0].get("text", "")
    assert (
        isinstance(text, str) and text
    ), f"Expected a non-empty text in choices[0], got: {body['choices'][0]!r}"
    logger.info(f"Received completions text from vLLM server: {text!r}")


@pytest.fixture
def fake_loki():
    """Run an in-process HTTP server that records Loki push requests.

    Yields ``(snapshot, port)`` where ``snapshot()`` returns the concatenation of
    all request bodies received so far. The server is always shut down on
    teardown, whether the test passes or fails.
    """
    received = []
    lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 (name mandated by the base class)
            length = int(self.headers.get("Content-Length", 0) or 0)
            body = self.rfile.read(length) if length else b""
            with lock:
                received.append(body)
            # Loki's push API replies 204 on success.
            self.send_response(204)
            self.end_headers()

        def do_GET(self):  # noqa: N802
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            # Silence the default per-request stderr logging.
            pass

    server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Fake Loki server listening on port {port}")

    def snapshot() -> bytes:
        with lock:
            return b"".join(received)

    try:
        yield snapshot, port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        logger.info("Fake Loki server stopped")


def _wait_for_forwarded_logs(snapshot, container_id) -> bytes:
    """Wait until vLLM logs reach the fake Loki endpoint and return them.

    Raises an ``AssertionError`` including the container logs if nothing is
    forwarded within ``_LOG_FORWARDING_TIMEOUT_SECONDS``.
    """
    deadline = time.monotonic() + _LOG_FORWARDING_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        combined = snapshot()
        if b"pebble_service" in combined and b"vllm" in combined:
            logger.info("Received forwarded vLLM logs at the fake Loki endpoint")
            return combined
        time.sleep(5)

    container_logs = subprocess.run(
        ["docker", "logs", container_id],
        capture_output=True,
        text=True,
        check=False,
    )
    raise AssertionError(
        "No vLLM logs were forwarded to Loki within "
        f"{_LOG_FORWARDING_TIMEOUT_SECONDS}s.\n"
        f"--- container logs ---\n{container_logs.stdout}\n{container_logs.stderr}"
    )


@pytest.mark.abort_on_fail
def test_log_forwarding_to_loki(fake_loki):
    """vLLM service logs are forwarded to Loki when LOKI_URL is set.

    Starts the rock with LOKI_URL pointing at an in-process fake Loki endpoint
    and asserts that Pebble forwards the vLLM service logs to it. The container
    is always stopped and removed on completion or failure.
    """
    snapshot, loki_port = fake_loki
    check_rock = CheckRock("rockcraft.yaml")
    local_rock_image = f"{check_rock.get_name()}:{check_rock.get_version()}"

    # The container reaches the host-side fake Loki through Docker's
    # host-gateway alias (Docker Engine 20.10+).
    loki_url = f"http://host.docker.internal:{loki_port}/loki/api/v1/push"
    logger.info(f"Starting vLLM container with LOKI_URL={loki_url}")

    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--add-host",
            "host.docker.internal:host-gateway",
            "-e",
            f"HF_HOME={_HF_HOME_CONTAINER}",
            "-e",
            f"LOKI_URL={loki_url}",
            local_rock_image,
            "--model",
            _MODEL,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    container_id = result.stdout.strip()
    logger.info(f"Started container {container_id}")

    try:
        combined = _wait_for_forwarded_logs(snapshot, container_id)

        assert (
            b"pebble_service" in combined
        ), "Expected the default 'pebble_service' label in the forwarded logs"
        assert (
            b"vllm" in combined
        ), "Expected the vLLM service name in the forwarded logs"
        logger.info("Forwarded logs:\n%s", combined)
        logger.info("Log forwarding to Loki test completed successfully")
    finally:
        subprocess.run(["docker", "stop", container_id], check=False)
        subprocess.run(["docker", "rm", container_id], check=False)


@pytest.mark.abort_on_fail
def test_log_forwarding_with_overridden_entrypoint(fake_loki):
    """Logs are forwarded even when the rock's entrypoint is overridden.

    KServe does not use the rock's `pebble enter` entrypoint: it sets an
    explicit `command: [vllm, serve, /mnt/models, ...]` on the container, which
    replaces it. vLLM then runs as PID 1 with no Pebble daemon, so the wrapper
    has to start one itself before logs can be forwarded. Without that
    bootstrap, `pebble add` fails with "cannot communicate with server ...
    .pebble.socket not found" and no logs ever reach Loki.

    This reproduces that invocation with `--entrypoint vllm` and asserts the
    logs still arrive, labelled the way the charm's Loki queries expect.
    """
    snapshot, loki_port = fake_loki
    check_rock = CheckRock("rockcraft.yaml")
    local_rock_image = f"{check_rock.get_name()}:{check_rock.get_version()}"

    loki_url = f"http://host.docker.internal:{loki_port}/loki/api/v1/push"
    logger.info(
        f"Starting vLLM container with an overridden entrypoint and LOKI_URL={loki_url}"
    )

    result = subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--add-host",
            "host.docker.internal:host-gateway",
            "-e",
            f"HF_HOME={_HF_HOME_CONTAINER}",
            "-e",
            f"LOKI_URL={loki_url}",
            # Replaces the rock entrypoint, exactly as KServe's `command:` does.
            "--entrypoint",
            "vllm",
            local_rock_image,
            "serve",
            "--model",
            _MODEL,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    container_id = result.stdout.strip()
    logger.info(f"Started container {container_id}")

    try:
        combined = _wait_for_forwarded_logs(snapshot, container_id)

        # The charm queries Loki with `{app=~"vllm"}`, so the label set from
        # log-layer.yaml must survive the bootstrap.
        assert (
            b'"app":"vllm"' in combined
        ), f'Expected an app="vllm" label in the forwarded logs, got: {combined!r}'
        assert (
            b"pebble_service" in combined
        ), "Expected the default 'pebble_service' label in the forwarded logs"

        container_logs = subprocess.run(
            ["docker", "logs", container_id],
            capture_output=True,
            text=True,
            check=False,
        )
        stdout_and_stderr = container_logs.stdout + container_logs.stderr

        # The wrapper must have taken the bootstrap path rather than silently
        # skipping log forwarding.
        assert "starting Pebble to supervise vLLM" in stdout_and_stderr, (
            "Expected the wrapper to bootstrap Pebble when the entrypoint is "
            f"overridden, got: {stdout_and_stderr!r}"
        )
        assert (
            "cannot communicate with server" not in stdout_and_stderr
        ), f"Pebble socket was unavailable while adding the log layer: {stdout_and_stderr!r}"

        # 'serve' is fixed in the Pebble service command, so a leading 'serve'
        # from the caller must be dropped instead of passed through twice.
        assert (
            "vllm serve serve" not in stdout_and_stderr
        ), f"'serve' was passed to vLLM twice: {stdout_and_stderr!r}"

        logger.info("Forwarded logs:\n%s", combined)
        logger.info("Log forwarding with an overridden entrypoint works")
    finally:
        subprocess.run(["docker", "stop", container_id], check=False)
        subprocess.run(["docker", "rm", container_id], check=False)
