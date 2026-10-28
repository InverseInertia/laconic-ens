"""!regression and large matrices in the real page (Chromium, through Playwright). Skipped when
Playwright or a browser is not available, like test_ui.py."""
import pytest

pytest.importorskip("playwright.sync_api")
from uihelpers import reset  # noqa: E402


def show(page, text, selector):
    reset(page, text)
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('input'))")
    page.wait_for_selector(selector)
    page.wait_for_timeout(150)


def test_a_regression_block_shows_its_polynomial_and_values_without_solver_controls(page):
    show(page, "t = [0, 1, 2, 3] * 's\ns = [0, 4.9, 19.6, 44.1] * 'm\n!regression p, q, r\n  data: t, s\n  r2: R2\ng = 2*r\n",
         ".row.regression .katex")
    rows = page.eval_on_selector_all("#out .row", "rs => rs.map((r) => r.className.replace(' active', ''))")
    assert rows == ["row assign", "row assign", "row regression", "row assign"]
    shown = page.inner_text(".row.regression .body")
    assert "4.9" in shown and "R" in shown
    assert page.locator(".solver-tools").count() == 0
    assert "9.8" in page.inner_text(".row[data-line='6'] .body")


def test_a_large_matrix_is_collapsed_and_its_button_shows_it_whole(page):
    show(page, "M = ones(2, 40) * 'm\nx = 1\n", ".row .mx-toggle")
    columns = "(document.querySelector(\".row[data-line='1'] .math\").textContent.match(/1/g) || []).length"
    assert page.inner_text(".row .mx-toggle") == "Show all 2 × 40"
    few = page.evaluate(columns)
    page.click(".row .mx-toggle")
    page.wait_for_function("document.querySelector('.row .mx-toggle').textContent.startsWith('Collapse')")
    assert page.evaluate(columns) > few + 50
    # it stays whole when the sheet runs again, and the button collapses it
    reset(page, "M = ones(2, 40) * 'm\nx = 2\n")
    page.evaluate("document.querySelector('#src').dispatchEvent(new Event('input'))")
    page.wait_for_function("document.querySelector(\".row[data-line='2'] .body\").textContent.includes('2')")
    page.wait_for_timeout(150)
    assert page.inner_text(".row .mx-toggle") == "Collapse 2 × 40"
    page.click(".row .mx-toggle")
    page.wait_for_function("document.querySelector('.row .mx-toggle').textContent.startsWith('Show all')")
    assert page.evaluate(columns) == few
