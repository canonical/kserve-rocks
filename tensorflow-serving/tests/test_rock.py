# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import os
import logging
import random
import pytest
import string
import subprocess
import yaml

from charmed_kubeflow_chisme.rock import CheckRock


@pytest.mark.abort_on_fail
def test_rock():
    """Test rock."""
    temp_dir, container_name = rock_test_env
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
            "ls -la /usr/bin/tensorflow_model_server",
        ],
        check=True,
    )
