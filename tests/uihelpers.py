"""Small helpers shared by the browser tests (see conftest.py for the fixtures)."""


def reset(page, text):
    page.evaluate("t => { const s = document.querySelector('#src'); s.value = t; s.focus(); s.setSelectionRange(t.length, t.length); }", text)


def value(page):
    return page.evaluate("document.querySelector('#src').value")
