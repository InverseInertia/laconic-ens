import pytest

from laconic import server
from laconic.blockedit import apply
from laconic.rename import RenameError, RenameWarning, rename
from laconic.server import RenameBody


def renamed(text, old, new, confirm=False):
    """`rename`'s edits, made."""
    edits, n = rename(text, old, new, confirm)
    return apply(text, edits), n


def test_every_use_is_renamed():
    text = "L = 4.5'm\nA = L * 2\nf(x) = x^2 + L\nf(L)\n"
    out, n = renamed(text, "L", "span")
    assert out == "span = 4.5'm\nA = span * 2\nf(x) = x^2 + span\nf(span)\n"
    assert n == 4


def test_units_comments_commands_and_numbers_are_left_alone():
    text = "m = 2'kg\n# m is the mass\n## m\nd = 3'm\ne5 = 1e5 * m\n!clear\n"
    out, n = renamed(text, "m", "mass")
    assert out == "mass = 2'kg\n# m is the mass\n## m\nd = 3'm\ne5 = 1e5 * mass\n!clear\n"
    assert n == 2


def test_function_names_parameters_and_decorated_names():
    out, _ = renamed("x` = 2\nx = 1\ng(x) = x + 1\n", "x", "y")
    assert out == "x` = 2\ny = 1\ng(y) = y + 1\n"
    out, _ = renamed("~g = 9.81'm/'s^2\nF = 2 * ~g\n", "~g", "~grav")
    assert out == "~grav = 9.81'm/'s^2\nF = 2 * ~grav\n"
    out, n = renamed("~g = 9.81\nF = 2 * g\n", "g", "grav")
    assert out == "~grav = 9.81\nF = 2 * grav\n" and n == 2
    out, _ = renamed("σ_max = 3\nσ_max * 2\n", "σ_max", "s_y")
    assert out == "s_y = 3\ns_y * 2\n"


def test_line_endings_are_kept():
    assert renamed("a = 1\r\nb = a\r\n", "a", "c")[0] == "c = 1\r\nb = c\r\n"


@pytest.mark.parametrize("old,new,msg", [
    ("a", "1a", "not a valid"), ("a", "a", "same"), ("sin", "q", "built in"),
    ("a", "pi", "built in"), ("zz", "q", "does not appear"), ("a", "b", "already used")])
def test_unsafe_renames_are_refused(old, new, msg):
    with pytest.raises(RenameError, match=msg):
        renamed("a = 1\nb = a\n", old, new)


def test_endpoint():
    ok = server.rename_symbol(RenameBody(text="a = 1\nb = a", old="a", new="c"))
    assert ok == {"ok": True, "count": 2, "edits": [{"from": 0, "to": 1, "insert": "c"}, {"from": 10, "to": 11, "insert": "c"}]}
    bad = server.rename_symbol(RenameBody(text="a = 1", old="a", new="9"))
    assert bad["ok"] is False and "not a valid" in bad["error"]


def test_custom_units_are_renamed_with_their_uses():
    text = "'smoot = 1.7018'm\nd = 3'smoot -> 'm\nsmoot = 2\n# 'smoot\n"
    out, n = renamed(text, "'smoot", "'span_u")
    assert out == "'span_u = 1.7018'm\nd = 3'span_u -> 'm\nsmoot = 2\n# 'smoot\n"
    assert n == 2
    assert renamed(text, "'smoot", "span_u")[0] == out


@pytest.mark.parametrize("old,new,msg", [
    ("'zz", "'q", "does not appear"),
    ("'u", "'m", "already a unit"), ("'u", "'dm", "already a unit"),
    ("'u", "'v", "already a unit"), ("'u", "'9", "not a valid"), ("'u", "'u", "same")])
def test_unsafe_unit_renames_are_refused(old, new, msg):
    with pytest.raises(RenameError, match=msg):
        renamed("'u = 2'm\n'v = 3'm\nx = 1'u\n", old, new)


def test_replacing_a_standard_unit_warns_then_swaps_for_an_existing_unit():
    text = "d = 3'm + 2'm\n# 'm\n"
    with pytest.raises(RenameWarning, match="standard unit"):
        renamed(text, "'m", "'ft")
    out, n = renamed(text, "'m", "'ft", confirm=True)
    assert (out, n) == ("d = 3'ft + 2'ft\n# 'm\n", 2)


def test_replacing_a_standard_unit_with_a_new_one_adds_a_definition():
    out, n = renamed("d = 3'm\n", "'m", "'span", confirm=True)
    assert n == 1 and out == "'span = 1'm\nd = 3'span\n"
    out, _ = renamed("d = 3'm\r\n", "'m", "'span", confirm=True)
    assert out == "'span = 1'm\r\nd = 3'span\r\n"
