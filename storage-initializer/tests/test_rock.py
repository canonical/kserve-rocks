# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import random
import pytest
import string
import subprocess

from charmed_kubeflow_chisme.rock import CheckRock


@pytest.fixture()
def rock_test_env(tmpdir):
    """Yields a temporary directory and random docker container name, then cleans them up after."""
    container_name = "".join(
        [str(i) for i in random.choices(string.ascii_lowercase, k=8)]
    )
    yield tmpdir, container_name

    try:
        subprocess.run(["docker", "rm", container_name])
    except Exception:
        pass
    # tmpdir fixture we use here should clean up the other files for us


@pytest.mark.abort_on_fail
def test_rock(rock_test_env):
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
            "ls -la /usr/local/lib/python3.11/dist-packages/kserve",
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
    subprocess.run(
        [
            "docker",
            "run",
            "--entrypoint",
            "/bin/bash",
            LOCAL_ROCK_IMAGE,
            "-c",
            "ls -la /storage-initializer/scripts/initializer-entrypoint",
        ],
        check=True,
    )

