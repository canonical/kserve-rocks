# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import shlex
import socket
import subprocess
import time

import pytest
import requests
import logging

from charmed_kubeflow_chisme.rock import CheckRock

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

_HF_HOME_CONTAINER = "/tmp/huggingface"
_MODEL = "facebook/opt-125m"
_SERVER_PORT_CONTAINER = 8000
_STARTUP_TIMEOUT_SECONDS = 600
_POLL_INTERVAL_SECONDS = 10


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
    logger.info(f"Starting vLLM server container on port {port} using image {local_rock_image}")    

    result = subprocess.run(
        [
            "docker", "run", "-d",
            "-p", f"{port}:{_SERVER_PORT_CONTAINER}",
            "-e", f"HF_HOME={_HF_HOME_CONTAINER}",
            local_rock_image,
            "--model", _MODEL,
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

    assert "0.19.0" in result.stdout, (
        f"Expected vllm version 0.19.0 in output, got: {result.stdout!r}"
    )


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

    logger.info(f"Received completions response from vLLM server: {response.status_code} {response.text!r}")
    assert response.status_code == 200, (
        f"Expected HTTP 200 from /v1/completions, got {response.status_code}: {response.text!r}"
    )

    body = response.json()
    logger.info(f"Parsed JSON body from completions response: {body!r}")
    assert "choices" in body and len(body["choices"]) > 0, (
        f"Expected non-empty 'choices' in response, got: {body!r}"
    )
    text = body["choices"][0].get("text", "")
    assert isinstance(text, str) and text, (
        f"Expected a non-empty text in choices[0], got: {body['choices'][0]!r}"
    )
    logger.info(f"Received completions text from vLLM server: {text!r}")
