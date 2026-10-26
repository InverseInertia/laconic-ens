"""The PDF export: the printable HTML document, its layout in a real Chromium, and the plumbing
around the headless print (CLI and server)."""
import html
import json
import os
import re
import subprocess

import pytest

from laconic import evaluate, pdfdoc, server
from laconic.server import Sheet


def doc(text, **kw):
    return pdfdoc.page(evaluate(text).results, **kw)


def texs(out):
    return [html.unescape(t) for t in re.findall(r'data-tex="([^"]*)"', out)]


def test_one_block_per_line_with_live_math():
    out = doc("## Beam\n# Inputs\n# in kN\nL = 4.5'm\nM = 2 * L", title="beam")
    assert "<h1>beam</h1>" in out and "<h2>Beam</h2>" in out
    assert "<p>Inputs<br>in kN</p>" in out   # a comment over several lines stays one paragraph
    assert texs(out) == ["L = 4.5\\,\\mathrm{m}",
                         "\\begin{aligned}M &= 2 \\cdot L \\\\ &= 2 \\cdot 4.5\\,\\mathrm{m} \\\\ &= 9\\,\\mathrm{m}\\end{aligned}"]
    assert out.count('<div class="block">') == 2
    assert '<span class="ln">4</span>' in out and '<span class="ln">5</span>' in out


def test_wrapped_rows_drop_the_alignment_mark():
    rows = re.search(r'data-rows="([^"]*)"', doc("M = 2 * 3'm")).group(1)
    assert json.loads(html.unescape(rows)) == ["M = 2 \\cdot 3\\,\\mathrm{m}", "= 6\\,\\mathrm{m}"]


def test_page_breaking_rules():
    out = doc("x = 1")
    assert ".block { break-inside: avoid" in out
    assert "h2 {" in out and "break-after: avoid" in out
    assert 'counter(page) " of " counter(pages)' in out


def test_commands_left_out_globals_plain_errors_shown():
    out = doc("~g = 9.81'm/'s^2\n!clear\nW = 2'kg * g\ny = nosuch + 1")
    assert "!clear" not in out and "htmlData" not in out
    assert '<div class="block callout error"><b>Line 4</b>' in out


def test_text_is_escaped():
    out = doc("# a <b> & \"c\"", title="<x>")
    assert "<p>a &lt;b&gt; &amp; &quot;c&quot;</p>" in out and "<h1>&lt;x&gt;</h1>" in out


def test_plots_are_inline_svg():
    out = doc("f(x) = x^2\n!plot f(x), x = 0 .. 1\n  title: Square")
    assert '<div class="block plot"><svg' in out


def test_assets_and_autoprint():
    local = doc("x = 1")
    assert pdfdoc.STATIC.as_uri() + "/vendor/katex/katex.min.js" in local and "print()" not in local
    served = doc("x = 1", assets="/static/", autoprint=True)
    assert 'src="/static/vendor/katex/katex.min.js"' in served and "print()" in served


def test_lens_chromium_names_the_browser(monkeypatch, tmp_path):
    exe = tmp_path / "mybrowser"
    exe.write_text("")
    monkeypatch.setenv("LENS_CHROMIUM", str(exe))
    assert pdfdoc.find_chromium() == str(exe)


def test_no_browser(monkeypatch, tmp_path):
    monkeypatch.setattr(pdfdoc, "find_chromium", lambda: None)
    with pytest.raises(pdfdoc.NoBrowser):
        pdfdoc.pdf("<p>x")
    # The page falls back to the browser's print dialog on a 501.
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))
    with pytest.raises(server.HTTPException) as e:
        server.export_pdf(Sheet(text="x = 1"))
    assert e.value.status_code == 501
    assert "print()" in server.export_print(Sheet(text="x = 1", title="t"))


def test_cli_without_a_browser(monkeypatch, tmp_path):
    from laconic.__main__ import main
    monkeypatch.setattr(pdfdoc, "find_chromium", lambda: None)
    sheet = tmp_path / "s.lens"
    sheet.write_text("x = 1")
    monkeypatch.setattr("sys.argv", ["lens", str(sheet), "--pdf", str(tmp_path / "s.pdf")])
    with pytest.raises(SystemExit, match="PDF export failed"):
        main()


def test_layout_in_chromium(tmp_path):
    """The real layout: every formula fits the column, a very wide one is wrapped, and the
    document prints to several pages."""
    playwright = pytest.importorskip("playwright.sync_api")
    wide = "w = " + " + ".join(f"a * b / c * {i}" for i in range(1, 16))
    text = "a = 1.5'm\nb = 2.25'm\nc = 3'm\n" + wide + "\n" + "\n".join(f"x_{i} = {i} * a^2 / b" for i in range(40))
    path = tmp_path / "s.html"
    path.write_text(doc(text, title="s"), encoding="utf-8")
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        except Exception as e:
            pytest.skip(f"no Chromium: {e}")
        pg = browser.new_page()
        pg.emulate_media(media="print")
        pg.goto(path.as_uri())
        pg.wait_for_function("document.querySelectorAll('.math .katex').length > 40")
        pg.evaluate("document.fonts.ready")
        assert pg.evaluate("document.querySelectorAll('.math.wrapped').length") == 1
        over = pg.evaluate("""[...document.querySelectorAll('.math')].filter(el =>
            [...el.children].some(k => k.getBoundingClientRect().width > el.getBoundingClientRect().width + 1)).length""")
        assert over == 0
        out = pg.pdf()
        browser.close()
    assert out.startswith(b"%PDF") and len(re.findall(rb"/Type\s*/Page[^s]", out)) > 1


@pytest.mark.skipif(not os.environ.get("LENS_CHROMIUM"), reason="set LENS_CHROMIUM to run the headless print")
def test_headless_print(tmp_path):
    from laconic.__main__ import main
    import sys
    sheet = tmp_path / "s.lens"
    sheet.write_text("## A\nx = 2'm\ny = x^2")
    out = tmp_path / "s.pdf"
    old = sys.argv
    sys.argv = ["lens", str(sheet), "--pdf", str(out)]
    try:
        main()
    finally:
        sys.argv = old
    assert out.read_bytes().startswith(b"%PDF")
