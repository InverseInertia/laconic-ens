"""Everything else is in pyproject.toml. This only copies CHANGELOG.md, which lives at the
repository root, into the built package, so Help can show it in an installed LENS
(laconic/changelog.py). An editable install reads the root file directly."""
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py

CHANGELOG = Path(__file__).resolve().parent / "CHANGELOG.md"


class BuildPy(build_py):
    def run(self):
        super().run()
        if CHANGELOG.exists() and not self.editable_mode:
            self.copy_file(str(CHANGELOG), str(Path(self.build_lib, "laconic", "CHANGELOG.md")))


setup(cmdclass={"build_py": BuildPy})
