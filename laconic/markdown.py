"""Line results -> a Markdown note in the style Obsidian reads: headings as `#`, comments as
plain text, each calculation as a `$$ ... $$` block and each plot as an embedded SVG image.

The math is the live preview's flavour (`\\mathrm{kN}`, not siunitx), which MathJax renders
as it is; commands such as `!clear` and the option lines of a block are left out."""
import base64

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


def block(r):
    """The Markdown for one line result, or None for a line the note leaves out."""
    if r.kind == "heading":
        return "## " + r.text
    if r.kind == "comment":
        return r.text
    if r.kind == "error":
        return _callout("error", f"Line {r.n}", r.error)
    if r.plot:
        title = r.plot.spec.get("title") or f"Plot, line {r.n}"
        data = base64.b64encode(r.plot.image(uid=r.n).encode("utf-8")).decode("ascii")
        return f"![{title}](data:image/svg+xml;base64,{data})"
    if r.solver:
        math = _math([f"{v['lhs']} &= {v['rhs']}" for v in r.solver.values])
        if not r.solver.current:
            math = _callout("warning", "Out of date",
                            "This solver result is out of date or was never run; the values may be starting values.") + "\n\n" + math
        return math
    if r.kind in ("assign", "expr", "funcdef", "unitdef"):
        rows = [f"{r.lhs} &= {r.stages[0]}" if r.lhs else f"&{r.stages[0]}"]
        return _math(rows + [f"&= {s}" for s in r.stages[1:]])
    return None


def markdown(results, title=None):
    """The whole sheet as one Markdown note. Run the sheet without siunitx for it."""
    out, prev = ([f"# {title}"] if title else []), None
    for r in results:
        x = block(r)
        if x is None:
            continue
        if r.kind == "comment" and prev == "comment":
            out[-1] += "\n" + x        # a comment that runs over several lines stays one paragraph
        else:
            out.append(x)
        prev = r.kind
    return "\n\n".join(out) + "\n"
