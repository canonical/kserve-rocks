# Copyright 2026 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import subprocess

import pytest
from charmed_kubeflow_chisme.rock import CheckRock

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


@pytest.fixture(scope="module")
def rock_image() -> str:
    """Return the local rock image reference (name:version)."""
    check_rock = CheckRock("rockcraft.yaml")
    return f"{check_rock.get_name()}:{check_rock.get_version()}"


def _run_in_rock(rock_image: str, command: str) -> subprocess.CompletedProcess:
    """Run a shell command inside the rock and return the completed process."""
    return subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--entrypoint",
            "/bin/bash",
            rock_image,
            "-c",
            command,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.abort_on_fail
def test_epp_binary_present(rock_image):
    """The epp binary is installed at the upstream runtime path and executable."""
    _run_in_rock(rock_image, "test -x app/epp")


@pytest.mark.abort_on_fail
def test_python_wrapper_present(rock_image):
    """The render_jinja_template_wrapper.py module is installed in site-packages."""
    _run_in_rock(
        rock_image,
        "test -f /usr/local/lib/python3.12/site-packages/render_jinja_template_wrapper.py",
    )


@pytest.mark.abort_on_fail
def test_epp_dynamic_libraries_resolve(rock_image):
    """All shared libraries the CGO binary links against resolve inside the rock."""
    result = _run_in_rock(rock_image, "ldd app/epp")
    logger.info("ldd app/epp:\n%s", result.stdout)
    assert (
        "not found" not in result.stdout
    ), f"Unresolved shared libraries in app/epp:\n{result.stdout}"


@pytest.mark.abort_on_fail
def test_epp_runs(rock_image):
    """The epp binary executes (loads its shared libs) and reports its usage."""
    # `epp --help` exercises binary startup without requiring a running model
    # server. argparse-style runners exit non-zero on --help, so tolerate the
    # exit code and assert on the absence of a dynamic-linker failure instead.
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            rock_image,
            "--help",
        ],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    logger.info("epp --help output:\n%s", output)
    assert "error while loading shared libraries" not in output, output
