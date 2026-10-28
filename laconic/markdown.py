"""Line results -> a Markdown note in the style Obsidian reads: headings as `#`, comments as
plain text, each calculation as a `$$ ... $$` block and each plot as an embedded SVG image.

The math is the live preview's flavour (`\\mathrm{kN}`, not siunitx), which MathJax renders
as it is; commands such as `!clear` and the option lines of a block are left out."""
import base64

from .exports import OUT_OF_DATE, Error, Figure, Heading, Paragraph, elements

_TAG = "\\htmlData{"


def plain_math(tex):
    """`tex` without the live view's `\\htmlData{global=g}{g}` tags (KaTeX only), keeping
    the tagged name."""
    out, i = [], 0
    while (j := tex.find(_TAG, i)) >= 0:
        out.append(tex[i:j])
        k = tex.index("}", j) + 1          # past {global=...}; the key holds no braces
        if not tex.startswith("{", k):     # not the form Fmt.var writes; keep it as it is
            out.append(tex[j:k])
            i = k
            continue
        depth, end = 0, k
        for end in range(k, len(tex)):
            depth += {"{": 1, "}": -1}.get(tex[end], 0)
            if depth == 0:
                break
        out.append(tex[k + 1:end])
        i = end + 1
    out.append(tex[i:])
    return "".join(out)


def _math(rows):
    """A display block: one row per stage, aligned at the equals signs when there is more than one."""
    rows = [plain_math(r) for r in rows]
    if len(rows) == 1:
        return "$$\n" + rows[0].replace("&", "", 1) + "\n$$"
    return "$$\n\\begin{aligned}\n" + " \\\\\n".join(rows) + "\n\\end{aligned}\n$$"


def _callout(kind, title, body=""):
    return f"> [!{kind}] {title}" + "".join(f"\n> {l}" for l in body.splitlines())


def block(e):
    """The Markdown for one export element (see exports.py)."""
    if isinstance(e, Heading):
        return "## " + e.text
    if isinstance(e, Paragraph):
        return "\n".join(e.lines)       # a comment that runs over several lines stays one paragraph
    if isinstance(e, Error):
        return _callout("error", f"Line {e.n}", e.message)
    if isinstance(e, Figure):
        title = e.plot.spec.get("title") or f"Plot, line {e.n}"
        data = base64.b64encode(e.plot.image(uid=e.n).encode("utf-8")).decode("ascii")
        return f"![{title}](data:image/svg+xml;base64,{data})"
    math = _math(e.rows)
    if e.out_of_date:
        math = _callout("warning", *OUT_OF_DATE) + "\n\n" + math
    return math


def markdown(results, title=None):
    """The whole sheet as one Markdown note. Run the sheet without siunitx for it."""
    return "\n\n".join(([f"# {title}"] if title else []) + [block(e) for e in elements(results)]) + "\n"
