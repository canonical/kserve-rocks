# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
import subprocess

from charmed_kubeflow_chisme.rock import CheckRock


@pytest.mark.abort_on_fail
def test_rock():
    """Test rock."""
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    LOCAL_ROCK_IMAGE = f"{rock_image}:{rock_version}"

    checks = [
        # assert the server executable and shared library are present
        "test -x /opt/tritonserver/bin/tritonserver",
        "ls -la /opt/tritonserver/lib/libtritonserver.so",
        # assert the built backends are present
        "ls -la /opt/tritonserver/backends/python "
        "/opt/tritonserver/backends/tensorrt "
        "/opt/tritonserver/backends/tensorflow "
        "/opt/tritonserver/backends/openvino "
        "/opt/tritonserver/backends/onnxruntime "
        "/opt/tritonserver/backends/pytorch",
        # assert the checksum repository agent is present
        "ls -la /opt/tritonserver/repoagents/checksum",
    ]

    for check in checks:
        subprocess.run(
            [
                "docker",
                "run",
                "--entrypoint",
                "/bin/bash",
                LOCAL_ROCK_IMAGE,
                "-c",
                check,
            ],
            check=True,
        )
