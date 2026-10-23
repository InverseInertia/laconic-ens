"""The solver controls in the real page (Chromium, through Playwright): Run, Auto, Interrupt, Verify,
Log and the out-of-date marks. Skipped when Playwright or a browser is not available, like test_ui.py."""
import pytest

pytest.importorskip("playwright.sync_api")
pytest.importorskip("scipy")
from test_ui import page, reset, server, value  # noqa: E402,F401  (fixtures and helpers)

ROOT = "x = 1'm\\ny = 1'm\\n!root x, y\\n  equation: x^2 + y^2 = 4'm^2\\n  equation: x = y\\nz = x * 2\\n"
STATE = "document.querySelector('.solver-tools').dataset.state"


def show(page, text):
    page.evaluate("t => { const s = document.querySelector('#src'); s.value = t; s.dispatchEvent(new Event('input')); }",
                  text.replace("\\n", "\n"))
    page.wait_for_selector(".solver-tools")
    page.wait_for_timeout(250)


def state(page):
    return page.evaluate(STATE)


def wait_state(page, want, timeout=30000):
    page.wait_for_function(f"{STATE} === '{want}'", timeout=timeout)


def run_and_wait(page):
    page.click(".s-run")
    wait_state(page, "ok")
    page.wait_for_timeout(300)


def test_an_unsolved_block_says_so_and_marks_what_depends_on_it(page):
    show(page, ROOT)
    assert state(page) == "none"
    assert "Not run yet" in page.inner_text(".s-status")
    assert page.locator(".row.stale").count() == 2         # the block and `z = x * 2`
    assert page.is_disabled(".s-stop") and page.is_disabled(".s-verify") and page.is_enabled(".s-run")


def test_run_stores_the_result_in_the_worksheet(page):
    show(page, ROOT)
    run_and_wait(page)
    assert "  #@ result {" in value(page)
    assert "Up to date" in page.inner_text(".s-status")
    assert "1.414" in page.inner_text(".s-values")
    assert page.locator(".row.stale").count() == 0
    assert "hybr" in page.inner_text(".s-sub")


def test_changing_an_input_marks_the_result_out_of_date(page):
    show(page, ROOT)
    run_and_wait(page)
    edited = value(page).replace("4'm^2", "9'm^2")
    show(page, edited)
    assert state(page) == "warn" and "Out of date" in page.inner_text(".s-status")
    assert page.locator(".row.stale").count() == 2
    assert page.is_disabled(".s-verify")           # only a current result can be verified


def test_verify_reruns_and_compares(page):
    show(page, ROOT)
    run_and_wait(page)
    before = value(page)
    page.click(".s-verify")
    page.wait_for_function("document.querySelector('.s-text').textContent.startsWith('Verified')", timeout=30000)
    assert value(page) == before                   # verifying never rewrites the sheet


def test_the_log_dialog_shows_the_run(page):
    show(page, ROOT)
    run_and_wait(page)
    page.click(".s-log")
    page.wait_for_selector("#solverLogDlg[open]")
    text = page.inner_text("#solverLogText")
    assert "converged" in text and "Inputs hash:" in text and "start:  x = 1 m" in text
    page.click("#solverLogDlg .close")


def test_a_failed_run_says_what_went_wrong_and_changes_nothing(page):
    show(page, "x = 1\\n!root x\\n  equation: x^2 = -1\\n  maxiter: 3\\n")
    before = value(page)
    page.click(".s-run")
    wait_state(page, "fail")
    assert "Failed" in page.inner_text(".s-status")
    assert value(page) == before
    page.click(".s-log")
    assert page.inner_text("#solverLogText").count("NOT converged") == 1
    page.click("#solverLogDlg .close")


def test_interrupt_stops_a_calculation_that_will_not_finish(page):
    slow = ("x = 1'm\\n!minimize x\\n  objective: det(identity(2500)) * x^2 / 'm^2\\n"
            "  method: Nelder-Mead\\n  maxiter: 100000\\n")
    show(page, slow)
    before = value(page)
    page.click(".s-run")
    wait_state(page, "run")
    assert page.is_enabled(".s-stop") and page.is_disabled(".s-run")
    page.click(".s-stop")
    wait_state(page, "fail", timeout=10000)
    assert "Interrupted" in page.inner_text(".s-status")
    assert page.is_enabled(".s-run") and page.is_disabled(".s-stop")
    assert value(page) == before                   # nothing stored


def test_auto_run_solves_again_after_an_edit_and_gives_up_on_a_failure(page):
    show(page, ROOT)
    run_and_wait(page)
    page.check(".s-auto")
    page.wait_for_function("document.querySelector('#src').value.includes('autorun: on')")
    page.wait_for_timeout(600)
    assert state(page) == "ok"                     # turning Auto on changes no input
    show(page, value(page).replace("4'm^2", "9'm^2"))
    wait_state(page, "ok")                         # re-solved by itself, a moment after the edit
    page.wait_for_timeout(300)
    assert "2.121" in page.inner_text(".s-values")
    # a problem that cannot be solved is tried once, not over and over
    show(page, "x = 1\\n!root x\\n  autorun: on\\n  equation: x^2 = -1\\n  maxiter: 3\\n")
    wait_state(page, "fail")
    page.wait_for_timeout(2500)
    assert state(page) == "fail"
    assert page.evaluate("[...Solvers.runs.values()].filter(r => r.state === 'failed').length") == 1


def popup(page):
    page.wait_for_selector("#ac:not([hidden])")
    return page.eval_on_selector_all("#ac .ac-item .lbl", "els => els.map(e => e.textContent)")


def test_suggestions_offer_solver_options_and_methods(page):
    reset(page, "x = 1\ny = 2\n!minimize x, y\n  objective: x^2 + y^2\n  ")
    page.keyboard.type("me")
    assert popup(page) == ["method"]
    page.keyboard.press("Tab")
    assert value(page).endswith("  method: ")
    page.wait_for_timeout(100)
    page.keyboard.press("Control+Space")
    items = popup(page)
    assert items[:3] == ["BFGS", "Nelder-Mead", "Powell"] and "SLSQP" in items
    page.keyboard.type("sl")
    assert popup(page) == ["SLSQP"]
    page.keyboard.press("Tab")
    assert value(page).endswith("  method: SLSQP")


def test_props_suggests_keys_and_fluids_once_coolprop_has_loaded(page):
    reset(page, "rho = props(")
    page.keyboard.type('"')
    items = popup(page)                     # arrives after the lazy /api/vocab/props fetch
    assert items[:3] == ["T", "P", "D"]
    page.keyboard.type("D")
    assert popup(page) == ["D"]                 # still open: Tab closes the string
    assert "Mass density [kg/m^3]" in page.inner_text("#ac")
    page.keyboard.press("Tab")
    assert value(page) == 'rho = props("D"'
    page.keyboard.type(', "T", 20\'degC, "P", 1\'atm, "h2o')
    assert popup(page)[0] == "Water"
    page.keyboard.press("Tab")
    assert value(page) == 'rho = props("D", "T", 20\'degC, "P", 1\'atm, "Water"'
    page.keyboard.type(", \"1-")
    assert value(page).endswith('"1-')          # math keys leave a hyphen in quotes alone
