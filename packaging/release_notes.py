"""Print a release's notes from CHANGELOG.md, for the body of its GitHub release.

Usage: release_notes.py TAG [CHANGELOG]

The notes are the tag's section (## [v0.3.4](...)), or the ## Unreleased section when the
changelog has no section for the tag yet, followed by a compare link to the tag before it.
Sub-headings move up a level (### New -> ## New), as they read on a release page."""
import re
import subprocess
import sys
from pathlib import Path

REPO = "https://github.com/InverseInertia/laconic-ens"
HEADING = re.compile(r"^## \[?([^\]\s]+)")


def sections(text):
    """{key: body} for each ## section; the key is the tag (v0.3.4) or Unreleased."""
    out, key, lines = {}, None, []
    for line in text.splitlines() + ["## end"]:
        m = HEADING.match(line)
        if m:
            if key:
                out[key] = "\n".join(lines)
            key, lines = m.group(1), []
        elif key:
            lines.append(line)
    return out


def body(section):
    """The section as a release body: comments dropped, sub-headings one level up."""
    section = re.sub(r"<!--.*?-->", "", section, flags=re.S)
    return re.sub(r"^###", "##", section, flags=re.M).strip()


def previous_tag(tag):
    # LENS's own tags only, not the installer's (installer-v1.0.0)
    r = subprocess.run(["git", "describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", f"{tag}^"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else None


def notes(tag, text, previous=None):
    found = sections(text)
    notes = body(found.get(tag) or found.get("Unreleased", ""))
    if not notes:
        notes = "No changelog entries for this release."
    if previous:
        notes += f"\n\n**Full changelog**: {REPO}/compare/{previous}...{tag}"
    return notes + "\n"


if __name__ == "__main__":
    tag = sys.argv[1]
    path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    sys.stdout.write(notes(tag, path.read_text(encoding="utf-8"), previous_tag(tag)))
