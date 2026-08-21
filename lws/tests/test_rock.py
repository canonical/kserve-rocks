# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import subprocess

import pytest
from charmed_kubeflow_chisme.rock import CheckRock


@pytest.mark.abort_on_fail
def test_rock():
    """Test rock."""
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    LOCAL_ROCK_IMAGE = f"{rock_image}:{rock_version}"

    subprocess.run(
        ["docker", "run", "--rm", LOCAL_ROCK_IMAGE, "exec", "ls", "-la", "/manager"],
        check=True,
    )
