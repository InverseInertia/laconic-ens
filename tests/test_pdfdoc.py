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


def test_assets_and_no_print_of_its_own():
    """The page prints the served document from a hidden frame (#102), so no document calls
    print() itself, and none waits on a timer."""
    local = doc("x = 1")
    assert pdfdoc.STATIC.as_uri() + "/vendor/katex/katex.min.js" in local
    served = doc("x = 1", assets="/static/")
    assert 'src="/static/vendor/katex/katex.min.js"' in served
    for out in (local, served):
        assert "print()" not in out and "setTimeout" not in out


def test_headless_command_skips_browser_startup_work(tmp_path):
    cmd = pdfdoc.command("chrome", tmp_path / "s.html", tmp_path / "s.pdf", tmp_path / "p")
    assert cmd[0] == "chrome" and cmd[-1] == (tmp_path / "s.html").as_uri()
    assert f"--print-to-pdf={tmp_path / 's.pdf'}" in cmd and f"--user-data-dir={tmp_path / 'p'}" in cmd
    # A built-in field trial config stalled the command-line print until it was killed (#102).
    assert "--disable-field-trial-config" in cmd and "--disable-background-networking" in cmd
    budget = [int(a.split("=")[1]) for a in cmd if a.startswith("--virtual-time-budget=")]
    assert budget and budget[0] <= 1000


def _fake_browser(tmp_path, body):
    exe = tmp_path / "fakechrome"
    exe.write_text("#!/bin/sh\n" + body)
    exe.chmod(0o755)
    return str(exe)


@pytest.mark.skipif(os.name == "nt", reason="a shell script stands in for the browser")
def test_pdf_runs_the_browser_once_and_returns_what_it_printed(monkeypatch, tmp_path):
    log = tmp_path / "args"
    exe = _fake_browser(tmp_path, f"""echo "$@" >> {log}
for a in "$@"; do case "$a" in --print-to-pdf=*) printf '%%PDF-1.4 fake' > "${{a#--print-to-pdf=}}";; esac; done
""")
    monkeypatch.setenv("LENS_CHROMIUM", exe)
    assert pdfdoc.pdf("<p>x") == b"%PDF-1.4 fake"
    assert len(log.read_text().splitlines()) == 1 and "--disable-field-trial-config" in log.read_text()


@pytest.mark.skipif(os.name == "nt", reason="a shell script stands in for the browser")
def test_a_stalled_or_failing_browser_is_a_501_for_the_page_to_fall_back_on(monkeypatch, tmp_path):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("LENS_CHROMIUM", _fake_browser(tmp_path, "exec sleep 30\n"))
    with pytest.raises(subprocess.TimeoutExpired):
        pdfdoc.pdf("<p>x", timeout=0.5)
    monkeypatch.setattr(pdfdoc, "TIMEOUT", 0.5)
    with pytest.raises(server.HTTPException) as e:
        server.export_pdf(Sheet(text="x = 1"))
    assert e.value.status_code == 501
    monkeypatch.setenv("LENS_CHROMIUM", _fake_browser(tmp_path, "exit 0\n"))   # starts, writes nothing
    with pytest.raises(server.HTTPException) as e:
        server.export_pdf(Sheet(text="x = 1"))
    assert e.value.status_code == 501 and "did not write a PDF" in e.value.detail


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
    printable = server.export_print(Sheet(text="x = 1", title="t"))
    assert 'src="/static/vendor/katex/katex.min.js"' in printable and "print()" not in printable


def test_cli_without_a_browser(monkeypatch, tmp_path):
    from laconic.__main__ import main
    monkeypatch.setattr(pdfdoc, "find_chromium", lambda: None)
    sheet = tmp_path / "s.lens"
    sheet.write_text("x = 1")
    monkeypatch.setattr("sys.argv", ["lens", str(sheet), "--pdf", str(tmp_path / "s.pdf")])
    with pytest.raises(SystemExit, match="PDF export failed"):
        main()


def test_layout_in_chromium(tmp_path):
    """The real layout: every formula fits the printed column, whatever the window's width (the
    fallback prints from a full-size tab), a very wide one is wrapped, and the document prints
    to several pages."""
    playwright = pytest.importorskip("playwright.sync_api")
    wide = "w = " + " + ".join(f"a * b / c * {i}" for i in range(1, 16))
    medium = "v = " + " + ".join(f"a * b / c * {i}" for i in range(1, 6))   # wider than the column, not the window
    text = "a = 1.5'm\nb = 2.25'm\nc = 3'm\n" + wide + "\n" + medium + "\n" + "\n".join(f"x_{i} = {i} * a^2 / b" for i in range(40))
    path = tmp_path / "s.html"
    path.write_text(doc(text, title="s"), encoding="utf-8")
    with playwright.sync_playwright() as p:
        try:
            browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        except Exception as e:
            pytest.skip(f"no Chromium: {e}")
        pg = browser.new_page(viewport={"width": 1600, "height": 900})
        pg.goto(path.as_uri())
        pg.wait_for_function("document.querySelectorAll('.math .katex').length > 40")
        column = pg.evaluate("document.querySelector('.math').getBoundingClientRect().width")
        assert column < 178 / 25.4 * 96   # the printed column (178 mm), not the window
        pg.evaluate("document.fonts.ready")
        assert pg.evaluate("document.querySelectorAll('.math.wrapped').length") == 1
        over = pg.evaluate("""[...document.querySelectorAll('.math')].filter(el =>
            [...el.children].some(k => k.getBoundingClientRect().width > el.getBoundingClientRect().width + 1)).length""")
        assert over == 0
        assert pg.evaluate("[...document.querySelectorAll('.math .katex-display')].some(k => k.style.zoom)")
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
