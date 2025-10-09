# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import random
import pytest
import string
import subprocess

from charmed_kubeflow_chisme.rock import CheckRock


@pytest.mark.abort_on_fail
def test_rock():
    """Test rock."""
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    LOCAL_ROCK_IMAGE = f"{rock_image}:{rock_version}"

    # assert we have the expected files
    subprocess.run(
        [
            "docker",
            "run",
            "--entrypoint",
            "/bin/bash",
            LOCAL_ROCK_IMAGE,
            "-c",
            "ls -la /usr/local/lib/python3.12/dist-packages/huggingfaceserver",
        ],
        check=True,
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--entrypoint",
            "/bin/bash",
            LOCAL_ROCK_IMAGE,
            "-c",
            "ls -la /usr/local/lib/python3.12/dist-packages/kserve",
        ],
        check=True,
    )
    subprocess.run(
        [
            "docker",
            "run",
            "--entrypoint",
            "/bin/bash",
            LOCAL_ROCK_IMAGE,
            "-c",
            "ls -la /third_party",
        ],
        check=True,
    )
