"""Give a released tag its own section in CHANGELOG.md, in place of ## Unreleased.

Usage: stamp_changelog.py TAG DATE [CHANGELOG]

Run by the release job on main after a v* tag is released. The entries that were under
## Unreleased on the tagged commit move to a new ## [vX.Y.Z](...) (DATE) section; anything merged
to main since the tag stays under a fresh ## Unreleased above it. Does nothing when the changelog
already has a section for the tag."""
import re
import subprocess
import sys
from pathlib import Path

from release_notes import REPO, sections

UNRELEASED = re.compile(r"^## Unreleased[ \t]*\n", re.M)
NEXT = re.compile(r"^## ", re.M)


def heading(tag, date):
    return f"## [{tag}]({REPO}/releases/tag/{tag}) ({date})"


def drop_empty_groups(lines):
    """Lines without the ### groups that have no entries left under them."""
    out = []
    for line in lines:
        if out and out[-1].startswith("###") and (line.startswith("###") or not line.strip()):
            if line.startswith("###"):
                out.pop()
            continue
        out.append(line)
    if out and out[-1].startswith("###"):
        out.pop()
    return out


def stamp(text, tag, date, released=None):
    """text with the tag's section split off ## Unreleased. released is the Unreleased body as
    it was on the tagged commit (all of today's Unreleased when None)."""
    if tag in sections(text):
        return text
    m = UNRELEASED.search(text)
    if not m:
        raise SystemExit("CHANGELOG.md has no ## Unreleased section")
    end = NEXT.search(text, m.end())
    end = end.start() if end else len(text)
    current = text[m.end():end]
    if released is None:
        released = current
    released = re.sub(r"<!--.*?-->\n?", "", released, flags=re.S).strip()
    shipped = {line for line in released.splitlines() if line.startswith("- ")}
    kept = [line for line in current.splitlines() if line not in shipped]
    kept = "\n".join(drop_empty_groups(kept)).strip()
    section = heading(tag, date) + "\n\n" + (released or "No changelog entries for this release.")
    unreleased = "## Unreleased\n\n" + (kept + "\n\n" if kept else "")
    return text[:m.start()] + unreleased + section + "\n\n" + text[end:]


def at_tag(tag, path):
    """The Unreleased body of CHANGELOG.md on the tagged commit, or None if git can't show it."""
    r = subprocess.run(["git", "show", f"{tag}:CHANGELOG.md"], capture_output=True, text=True,
                       cwd=path.parent)
    return sections(r.stdout).get("Unreleased") if r.returncode == 0 else None


if __name__ == "__main__":
    tag, date = sys.argv[1], sys.argv[2]
    path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path(__file__).resolve().parent.parent / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    path.write_text(stamp(text, tag, date, at_tag(tag, path)), encoding="utf-8")
