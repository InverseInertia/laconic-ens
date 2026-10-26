"""The program's version, written in one place.

A source checkout says "0+dev". The build workflow writes the tag's version here
(v0.2.0 -> 0.2.0) before it installs and freezes the program, so the package
metadata (pyproject.toml reads this line), the release file names and the page
all agree."""
__version__ = "0+dev"


def label(version=__version__):
    """The version as the page shows it: "v0.2.0", or "dev" for an unstamped source checkout."""
    return "dev" if version.endswith("+dev") else "v" + version
