"""The Markdown (Obsidian) export."""
import base64
import re

from laconic import evaluate, markdown
from laconic.markdown import plain_math


def md(text, title=None):
    return markdown(evaluate(text).results, title=title)


def test_headings_comments_and_math():
    out = md("## Beam\n# Inputs\n# in kN\nL = 4.5'm\nM = 2 * L", title="beam")
    assert out.startswith("# beam\n\n## Beam\n\nInputs\nin kN\n\n")
    assert "$$\nL = 4.5\\,\\mathrm{m}\n$$" in out
    assert "\\begin{aligned}\nM &= 2 \\cdot L \\\\\n&= 2 \\cdot 4.5\\,\\mathrm{m} \\\\\n&= 9\\,\\mathrm{m}\n\\end{aligned}" in out


def test_no_latex_preamble_commands_or_siunitx():
    out = md("x = 2'm\n!clear\ny = 3'kN")
    assert "!clear" not in out and "% " not in out
    assert "\\qty" not in out and "\\unit" not in out and "\\documentclass" not in out


def test_global_names_are_plain():
    out = md("~g = 9.81'm/'s^2\nW = 2'kg * g")
    assert "htmlData" not in out
    assert "W &= 2\\,\\mathrm{kg} \\cdot g" in out


def test_plain_math_keeps_the_tagged_name():
    assert plain_math("\\htmlData{global=M_max}{M_{\\mathrm{max}}} + 1") == "M_{\\mathrm{max}} + 1"
    assert plain_math("a = b") == "a = b"


def test_errors_become_callouts():
    out = md("x = nosuch + 1")
    assert out.startswith("> [!error] Line 1\n> ")


def test_plots_are_embedded_svg_images():
    out = md("f(x) = x^2\n!plot f(x), x = 0 .. 1\n  title: Square")
    m = re.search(r"!\[Square\]\(data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)\)", out)
    assert m and base64.b64decode(m.group(1)).decode().lstrip().startswith("<?xml")
    assert "title:" not in out


def test_unsolved_solver_is_marked_out_of_date():
    out = md("x = 1\n!root x\n  equation: x^2 = 4")
    assert "> [!warning] Out of date" in out and "$$" in out
