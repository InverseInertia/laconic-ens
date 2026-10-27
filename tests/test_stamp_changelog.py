"""packaging/stamp_changelog.py: a released tag's Unreleased entries become its own section."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))
spec = importlib.util.spec_from_file_location("stamp_changelog", ROOT / "packaging" / "stamp_changelog.py")
sc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sc)

LINK = "https://github.com/InverseInertia/laconic-ens/releases/tag/v0.3.0"

CHANGELOG = """# Changelog

Intro text.

## Unreleased

<!-- one line per change -->
### New
- Feature. (#10)

### Fixes
- Pending fix. (#9)

## [v0.2.0](https://example.com/v0.2.0) (2026-10-26)

### New
- Second. (#2)
"""

OLD = """## [v0.2.0](https://example.com/v0.2.0) (2026-10-26)

### New
- Second. (#2)
"""


def test_unreleased_becomes_the_tag_section():
    # the authors' comment stays with Unreleased and is left out of the release
    assert sc.stamp(CHANGELOG, "v0.3.0", "2026-10-27") == (
        "# Changelog\n\nIntro text.\n\n## Unreleased\n\n<!-- one line per change -->\n\n"
        f"## [v0.3.0]({LINK}) (2026-10-27)\n\n"
        "### New\n- Feature. (#10)\n\n### Fixes\n- Pending fix. (#9)\n\n" + OLD)


def test_entries_merged_after_the_tag_stay_unreleased():
    at_tag = "\n### Fixes\n- Pending fix. (#9)\n"
    assert sc.stamp(CHANGELOG, "v0.3.0", "2026-10-27", at_tag) == (
        "# Changelog\n\nIntro text.\n\n## Unreleased\n\n"
        "<!-- one line per change -->\n### New\n- Feature. (#10)\n\n"
        f"## [v0.3.0]({LINK}) (2026-10-27)\n\n"
        "### Fixes\n- Pending fix. (#9)\n\n" + OLD)


def test_a_tag_with_a_section_is_left_alone():
    assert sc.stamp(CHANGELOG, "v0.2.0", "2026-10-27") == CHANGELOG


def test_a_release_without_entries_says_so():
    text = "# Changelog\n\n## Unreleased\n\n## v0.1.0\n\nFirst.\n"
    assert sc.stamp(text, "v0.2.0", "2026-10-27") == (
        "# Changelog\n\n## Unreleased\n\n"
        "## [v0.2.0](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.2.0) (2026-10-27)\n\n"
        "No changelog entries for this release.\n\n## v0.1.0\n\nFirst.\n")
