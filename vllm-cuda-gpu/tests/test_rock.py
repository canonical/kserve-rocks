# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import shlex
import socket
import subprocess
import time

import pytest
import requests

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
        "/opt/venv/bin/python",
        "/opt/venv/lib/python3.12/site-packages/vllm",
        "/opt/uv",
        "/usr/local/cuda-12.9",
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
