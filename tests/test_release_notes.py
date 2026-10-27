"""packaging/release_notes.py: a release's GitHub body taken from CHANGELOG.md."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "packaging" / "release_notes.py")
rn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rn)

CHANGELOG = """# Changelog

Intro text.

## Unreleased

<!-- one line per change -->
### Fixes
- Pending fix. (#9)

## [v0.2.0](https://example.com/v0.2.0) (2026-10-26)

### New
- Second. (#2)

## [v0.1.0](https://example.com/v0.1.0) (2026-10-20)

First release.
"""


def test_tag_section_with_compare_link():
    assert rn.notes("v0.2.0", CHANGELOG, "v0.1.0") == (
        "## New\n- Second. (#2)\n\n"
        "**Full changelog**: https://github.com/InverseInertia/laconic-ens/compare/v0.1.0...v0.2.0\n")


def test_first_release_has_no_compare_link():
    assert rn.notes("v0.1.0", CHANGELOG) == "First release.\n"


def test_untitled_tag_takes_unreleased_without_comments():
    assert rn.notes("v0.3.0", CHANGELOG) == "## Fixes\n- Pending fix. (#9)\n"


def test_nothing_to_say():
    assert rn.notes("v0.3.0", "# Changelog\n\n## Unreleased\n\n<!-- none -->\n") == (
        "No changelog entries for this release.\n")


def test_the_real_changelog_has_unreleased_and_its_sections_read():
    found = rn.sections((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert "Unreleased" in found
    assert rn.body(found["v0.1.0"])
