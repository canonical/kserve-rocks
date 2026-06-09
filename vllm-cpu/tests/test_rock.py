# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import os
import shlex
import socket
import subprocess
import time

import pytest
import requests

from charmed_kubeflow_chisme.rock import CheckRock


_HF_CACHE_HOST = "/tmp/hf-cache"
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

    os.makedirs(_HF_CACHE_HOST, exist_ok=True)
    port = _free_port()

    result = subprocess.run(
        [
            "docker", "run", "-d",
            "-p", f"{port}:{_SERVER_PORT_CONTAINER}",
            "-e", f"HF_HOME={_HF_HOME_CONTAINER}",
            "-v", f"{_HF_CACHE_HOST}:{_HF_HOME_CONTAINER}",
            local_rock_image,
            "--model", _MODEL,
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    container_id = result.stdout.strip()

    try:
        yield f"http://localhost:{port}"
    finally:
        subprocess.run(["docker", "stop", container_id], check=False)
        subprocess.run(["docker", "rm", container_id], check=False)


@pytest.mark.abort_on_fail
def test_rock():
    """Test that the vllm-cpu rock contains the expected files and the vllm binary works."""
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


@pytest.mark.integration
@pytest.mark.abort_on_fail
def test_endpoint_completions(vllm_server):
    """Test that the vLLM server responds correctly to a completions request."""
    base_url = vllm_server

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

    assert response.status_code == 200, (
        f"Expected HTTP 200 from /v1/completions, got {response.status_code}: {response.text!r}"
    )

    body = response.json()
    assert "choices" in body and len(body["choices"]) > 0, (
        f"Expected non-empty 'choices' in response, got: {body!r}"
    )
    text = body["choices"][0].get("text", "")
    assert isinstance(text, str) and text, (
        f"Expected a non-empty text in choices[0], got: {body['choices'][0]!r}"
    )
