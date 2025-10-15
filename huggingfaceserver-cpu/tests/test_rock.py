# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import random
import pytest
import string
import subprocess
import shlex

from charmed_kubeflow_chisme.rock import CheckRock


@pytest.mark.abort_on_fail
def test_rock():
    """Test rock."""
    check_rock = CheckRock("rockcraft.yaml")
    rock_image = check_rock.get_name()
    rock_version = check_rock.get_version()
    LOCAL_ROCK_IMAGE = f"{rock_image}:{rock_version}"

    paths = [
        "/usr/local/lib/python3.10/dist-packages/huggingfaceserver",
        "/usr/local/lib/python3.10/dist-packages/kserve",
        "/third_party",
    ]

    for p in paths:
        subprocess.run(
            [
                "docker",
                "run",
                "--entrypoint",
                "/bin/bash",
                LOCAL_ROCK_IMAGE,
                "-c",
                f"ls -la {shlex.quote(p)}",
            ],
            check=True,
        )
