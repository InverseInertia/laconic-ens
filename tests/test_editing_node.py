import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_editing_hotkeys():
    r = subprocess.run(["node", str(Path(__file__).with_name("test_editing.js"))],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr or r.stdout
