"""The changelog at the bottom of Help: finding CHANGELOG.md, rendering it, and shipping it."""
from pathlib import Path

from laconic import changelog, server

ROOT = Path(__file__).resolve().parent.parent

SAMPLE = """# Changelog

Notes for contributors, not shown in Help.

## Unreleased

<!-- nothing yet -->

## [v0.2.0](https://github.com/InverseInertia/laconic-ens/releases/tag/v0.2.0) (2026-10-23)

### New
- **Solving**: `!root` and `x < y` blocks, ``v&` `` too. (#29, #31)
  - Run and **Verify** controls.
- A [wiki page](https://example.com/a?b=1&c=2) and a [bad link](javascript:alert(1)).

### Fixes
- <script>alert(1)</script> is shown as text.

PR: #28
"""


def test_the_repository_changelog_is_found_and_rendered():
    assert changelog.read() == (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    html = changelog.html()
    assert "<h4>" in html and changelog.MISSING not in html
    assert "Every pull request" not in html     # the contributors' preamble is left out


def test_markdown_subset():
    html = changelog.to_html(SAMPLE, "0+dev")
    assert html.startswith('<h4><a href="https://github.com/InverseInertia/laconic-ens/releases/tag/v0.2.0" '
                           'target="_blank" rel="noopener">v0.2.0</a> (2026-10-23)</h4><h5>New</h5><ul><li>')
    assert "<strong>Solving</strong>: <code>!root</code> and <code>x &lt; y</code> blocks, <code>v&amp;` </code> too." in html
    assert f'(<a href="{changelog.REPO}/issues/29" target="_blank" rel="noopener">#29</a>, ' in html
    assert "<ul><li>Run and <strong>Verify</strong> controls.</li></ul></li>" in html   # nested list
    assert '<a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener">wiki page</a>' in html
    assert "javascript:" not in html.split("bad link")[0] and "<a href=\"javascript" not in html
    assert "&lt;script&gt;" in html and "<script>" not in html
    assert f'<p>PR: <a href="{changelog.REPO}/issues/28"' in html
    assert "nothing yet" not in html


def test_unreleased_is_shown_only_when_it_has_entries():
    assert "Unreleased" not in changelog.to_html(SAMPLE, "0+dev")
    text = SAMPLE.replace("<!-- nothing yet -->", "### Fixes\n- Something. (#9)")
    assert changelog.to_html(text, "0+dev").startswith("<h4>Unreleased</h4><h5>Fixes</h5>")


def test_a_release_build_shows_unreleased_under_its_version():
    # The tagged commit's changelog still says Unreleased; the release job renames it afterwards.
    text = SAMPLE.replace("<!-- nothing yet -->", "### Fixes\n- Something. (#9)")
    assert changelog.to_html(text, "0.2.1").startswith("<h4>v0.2.1</h4><h5>Fixes</h5>")
    # ...unless the changelog already has a section for that version.
    assert changelog.to_html(text, "0.2.0").startswith("<h4>Unreleased</h4>")


def test_a_missing_changelog_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(changelog, "PLACES", (tmp_path / "CHANGELOG.md",))
    assert changelog.read() is None
    assert changelog.html() == changelog.MISSING
    (tmp_path / "CHANGELOG.md").write_bytes(b"\xff\xfe not utf-8")
    assert changelog.html() == changelog.MISSING


def test_an_installed_copy_is_preferred(monkeypatch, tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("## Unreleased\n\n### New\n- Shipped copy. (#1)\n", encoding="utf-8")
    monkeypatch.setattr(changelog, "PLACES", (tmp_path / "CHANGELOG.md", ROOT / "CHANGELOG.md"))
    assert "Shipped copy." in changelog.html()


def test_help_ends_with_the_changelog_and_links_to_it(monkeypatch, tmp_path):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))
    page = server.index().body.decode()
    assert "<!-- changelog:" not in page
    assert '<a href="#changelog" id="changelogLink">Changelog</a>' in page
    help_dialog = page[page.index('<dialog id="helpDlg"'):]
    help_dialog = help_dialog[:help_dialog.index("</dialog>")]
    section = help_dialog[help_dialog.index('<section id="changelog"'):]
    assert changelog.html() in section and section.rstrip().endswith("</section>\n  </div>")


def test_builds_ship_a_copy():
    # The frozen program and the wheel each put CHANGELOG.md inside the laconic package.
    assert '(os.path.join(ROOT, "CHANGELOG.md"), "laconic")' in (ROOT / "packaging" / "lens.spec").read_text()
    assert '"laconic", "CHANGELOG.md"' in (ROOT / "setup.py").read_text()
    assert "include CHANGELOG.md" in (ROOT / "MANIFEST.in").read_text()
