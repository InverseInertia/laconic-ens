"""The changelog, shown at the bottom of Help.

`CHANGELOG.md` lives at the repository root. A source checkout (and an editable install) reads it
from there; an installed wheel and the frozen program carry a copy inside the package
(`setup.py` and `packaging/lens.spec` put it there), which is looked for first. Without either,
Help says so and points at the releases page.

The renderer covers what the changelog uses: `##`/`###` headings, `-` lists (nested by two-space
indent), paragraphs, `**bold**`, `` `code` ``, `[links](...)` and `#N` issue references."""
import re
from html import escape
from pathlib import Path

from ._version import __version__

REPO = "https://github.com/InverseInertia/laconic-ens"
HERE = Path(__file__).parent
PLACES = (HERE / "CHANGELOG.md", HERE.parent / "CHANGELOG.md")  # installed copy, then checkout
MISSING = ('<p class="u-empty">The changelog is not included in this copy of LENS. '
           f'See the <a href="{REPO}/releases" target="_blank" rel="noopener">releases page</a>.</p>')

_CODE = re.compile(r"(`+)(.+?)(?<!`)\1(?!`)")  # ``a `b` c`` holds backticks
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ISSUE = re.compile(r"(?<![\w&/])#(\d+)\b")
_HELD = re.compile("\x00(\\d+)\x00")
_BULLET = re.compile(r"^( *)[-*] +(.*)$")
_TAG = re.compile(r"^\[(v[^\]]+)\]")


def read():
    """The changelog's text, or None when this copy of LENS has none."""
    for path in PLACES:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return None


def inline(text):
    """One line of Markdown as HTML: code, links, bold and #N issue links; the rest escaped."""
    held = []

    def hold(html):
        held.append(html)
        return f"\x00{len(held) - 1}\x00"

    def code(m):
        body = m.group(2)
        if len(body) > 2 and body[0] == body[-1] == " ":
            body = body[1:-1]
        return hold(f"<code>{escape(body, quote=False)}</code>")

    text = _CODE.sub(code, text)

    def link(m):
        label, url = m.group(1), m.group(2)
        if not url.startswith(("https://", "http://")):
            return m.group(0)
        return hold(f'<a href="{escape(url)}" target="_blank" rel="noopener">{_plain(label)}</a>')

    text = _LINK.sub(link, text)
    text = _plain(text)
    text = _ISSUE.sub(lambda m: f'<a href="{REPO}/issues/{m.group(1)}" target="_blank" '
                                f'rel="noopener">#{m.group(1)}</a>', text)
    while _HELD.search(text):  # a held link can hold code
        text = _HELD.sub(lambda m: held[int(m.group(1))], text)
    return text


def _plain(text):
    return _BOLD.sub(r"<strong>\1</strong>", escape(text, quote=False))


def sections(text):
    """[(heading, body lines)] for each ## section, in order; text before the first is dropped."""
    out = []
    for line in re.sub(r"<!--.*?-->", "", text, flags=re.S).splitlines():
        if line.startswith("## "):
            out.append((line[3:].strip(), []))
        elif out:
            out[-1][1].append(line)
    return out


def _body(lines):
    out, lists, para = [], [], []   # lists: the indents of the open <ul>s, each with an open <li>

    def close_lists():
        while lists:
            lists.pop()
            out.append("</li></ul>")

    def close_para():
        if para:
            out.append("<p>" + " ".join(inline(p) for p in para) + "</p>")
            para.clear()

    for line in lines:
        bullet = _BULLET.match(line)
        if bullet:
            close_para()
            indent = len(bullet.group(1))
            while lists and lists[-1] > indent:
                lists.pop()
                out.append("</li></ul>")
            if lists and lists[-1] == indent:
                out.append("</li><li>")
            else:
                lists.append(indent)
                out.append("<ul><li>")
            out.append(inline(bullet.group(2).strip()))
        elif not line.strip():
            close_lists()
            close_para()
        elif lists and line.startswith(" "):   # an item wrapped onto the next line
            out.append(" " + inline(line.strip()))
        elif line.startswith("#"):
            close_lists()
            close_para()
            out.append(f"<h5>{inline(line.lstrip('#').strip())}</h5>")
        else:
            close_lists()
            para.append(line.strip())
    close_lists()
    close_para()
    return "".join(out)


def to_html(text, version=__version__):
    """The changelog's sections as HTML, newest first. An empty Unreleased section is left out.
    A release build (version stamped from its tag) is made before the release job gives the tag
    its own section, so there Unreleased is shown under the release's version."""
    parts = sections(text)
    tags = {m.group(1) for heading, _ in parts if (m := _TAG.match(heading))}
    html = []
    for heading, lines in parts:
        body = _body(lines)
        if heading == "Unreleased":
            if not body:
                continue
            if not version.endswith("+dev") and "v" + version not in tags:
                heading = "v" + version
        html.append(f"<h4>{inline(heading)}</h4>{body}")
    return "\n".join(html)


def html(version=__version__):
    """What Help shows: the rendered changelog, or a note when there is none to show."""
    text = read()
    rendered = to_html(text, version) if text else ""
    return rendered or MISSING
