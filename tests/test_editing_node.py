import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
@pytest.mark.parametrize("suite", ["test_editing.js", "test_autocomplete.js", "test_paste.js"])
def test_editor_suites(suite):
    r = subprocess.run(["node", str(Path(__file__).with_name(suite))], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr or r.stdout
