# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import shlex
import subprocess

import pytest
from charmed_kubeflow_chisme.rock import CheckRock

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@pytest.mark.abort_on_fail
def test_rock():
    """Test that the vllm rock contains the expected files."""
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    local_rock_image = f"{rock_image}:{rock_version}"

    # Paths that must exist inside the rock.
    paths = [
        "/opt/venv/bin/vllm",
        "/opt/venv/bin/vllm-original",
        "/opt/venv/bin/python",
        "/opt/venv/lib/python3.12/site-packages/vllm",
        "/opt/uv",
        "/usr/local/cuda-12.9",
        "/opt/pebble/vllmd.sh",
        "/opt/pebble/log-layer.yaml",
    ]

    for p in paths:
        logger.info(f"Checking that {p} exists in the rock...")
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
    logger.info("All expected paths exist in the rock.")


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
def test_log_forwarding_bootstraps_pebble_without_daemon():
    """The wrapper starts Pebble itself when the rock entrypoint is overridden.

    KServe sets an explicit `command: [vllm, serve, /mnt/models, ...]`, which
    replaces the rock's `pebble enter` entrypoint. vLLM then runs as PID 1 with
    no Pebble daemon, so `pebble add` would fail and no logs would be forwarded
    unless the wrapper bootstraps a daemon first.

    The equivalent end-to-end test lives in the vllm-cpu rock, which can
    run its container without a GPU; here the wrapper's logic is asserted
    statically so the two flavours cannot drift apart.
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
            "cat /opt/pebble/vllmd.sh",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    script = result.stdout

    assert (
        "pebble enter --verbose --args vllm" in script
    ), f"Expected a re-exec through 'pebble enter', got: {script!r}"
    assert (
        ".pebble.socket" in script
    ), f"Expected a check for a running Pebble daemon, got: {script!r}"
    # Adding the layer must be idempotent across service restarts.
    assert (
        "pebble add --combine logging" in script
    ), f"Expected 'pebble add --combine logging', got: {script!r}"
    # A re-exec loop would fork-bomb the container.
    assert (
        "VLLM_PEBBLE_BOOTSTRAP" in script
    ), f"Expected a re-exec loop guard in the wrapper, got: {script!r}"


@pytest.mark.abort_on_fail
def test_vllm_entrypoint():
    """Test that the vllm binary works."""
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
        capture_output=True,
        text=True,
    )

    out = "Triton is installed but 0 active driver(s)"

    assert (
        out in result.stdout
    ), f"Expected error message in output, got: {result.stdout!r}"