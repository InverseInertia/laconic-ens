"""`!loop` blocks (#131): what the block leaves below it, entries of vectors and matrices, loops
inside loops, the errors, and the block in the editor's text, Rename and the exports."""
from laconic.blockedit import apply
from laconic.exports import export
from laconic.loop import MAX_LINES
from laconic.rename import rename
from laconic.sheet import run
from laconic.sheettext import scan

HILBERT = """S = 0
M = zeros(3, 3)
!loop i = 1 .. 3
  S = S + i^2
  !loop j = 1 .. 3
    elem(M, i, j) = 1 / (i + j - 1)
S
M"""


def errors(rs):
    return {r.n: r.error for r in rs if r.error}


def test_a_loop_sums_and_fills_a_matrix_for_the_lines_below():
    rs = run(HILBERT)
    assert not errors(rs)
    assert rs[2].kind == "loop" and [r.kind for r in rs[3:6]] == ["loopline"] * 3
    assert rs[6].text == "14"
    assert rs[7].text == "[[1 0.5 0.3333]\n [0.5 0.3333 0.25]\n [0.3333 0.25 0.2]]"
    assert rs[2].text.startswith("S = 14; M = ") and rs[2].text.endswith("(ran 3 times)")


def test_the_block_is_typeset_as_steps_then_what_it_left():
    r = run(HILBERT)[2]
    assert r.loop.code == [r"&\textbf{for}\ i = 1, \ldots, 3",
                           r"&\quad S \leftarrow S + i^{2}",
                           r"&\quad \textbf{for}\ j = 1, \ldots, 3",
                           r"&\quad \quad {M}_{i,\,j} \leftarrow \frac{1}{i + j - 1}"]
    assert [v["latex"] for v in r.loop.values][0] == "S = 14"
    assert r.latex.startswith(r"\begin{aligned} &\textbf{for}\ i = 1, \ldots, 3 \\ &\quad S")
    assert r.latex.endswith(r"\end{bmatrix} \end{aligned}") and r"\\ S &= 14 \\ M &= " in r.latex


def test_the_value_above_the_block_is_left_as_it_was():
    rs = run("v = zeros(3, 1)\nw = v\n!loop k = 1 .. 3\n  idx(v, k) = k\nw\nv")
    assert rs[4].text == "[[0]\n [0]\n [0]]" and rs[5].text == "[[1]\n [2]\n [3]]"


def test_an_inner_loop_reads_the_outer_index():
    rs = run("n = 3\nT = zeros(n, n)\n!loop i = 1 .. n\n  !loop j = 1 .. i\n    elem(T, i, j) = i*j\nT")
    assert rs[-1].text == "[[1 0 0]\n [2 4 0]\n [3 6 9]]"


def test_a_vector_takes_the_units_of_what_is_put_in_it():
    rs = run("v = zeros(1, 3)\n!loop k = 1 .. 3\n  idx(v, k) = k * 2'm\nv")
    assert rs[-1].text == "[[2 4 6]] m"


def test_a_matrix_row_is_set_whole():
    rs = run("M = [1, 2; 3, 4]\n!loop i = 1 .. 2\n  idx(M, i) = [i, 10*i]\nM")
    assert rs[-1].text == "[[1 10]\n [2 20]]"


def test_an_entry_keeps_the_matrix_dimension():
    rs = run("v = [1, 2]*'m\n!loop k = 1 .. 2\n  idx(v, k) = 3's")
    assert "every entry of a matrix has the same dimension" in rs[2].error


def test_a_loop_that_runs_no_times_leaves_names_as_they_were():
    rs = run("S = 5\n!loop i = 1 .. 0\n  S = S + 1\nS")
    assert rs[1].text == "ran 0 times" and rs[3].text == "5"


def test_the_index_is_gone_below_and_a_name_it_hid_is_back():
    rs = run("k = 7\nS = 0\n!loop k = 1 .. 2\n  S = S + k\nk\nS")
    assert rs[4].text == "7" and rs[5].text == "3"


def test_lines_call_functions_and_assign_globals():
    rs = run("f(x) = x^2\n~G = 0\n!loop i = 1 .. 4\n  ~G = G + f(i)\n  # comments are skipped\nG")
    assert not errors(rs) and rs[-1].text == "30"


def test_a_failing_line_says_where_and_what_it_left_is_out_of_date():
    rs = run("S = 0'm\n!loop i = 1 .. 3\n  S = S + i\nS")
    assert rs[1].error == "Line 3 failed (at i = 1)"
    assert rs[2].error.endswith("(at i = 1)")
    assert rs[3].stale


def test_an_error_inside_names_every_index():
    rs = run("v = [1, 2]\n!loop i = 1 .. 2\n  !loop j = 1 .. 3\n    idx(v, j) = i")
    assert rs[3].error == "idx: index 3 is out of range 1..2 (at i = 1, j = 3)"


def test_a_long_loop_is_stopped():
    rs = run("!loop i = 1 .. 200\n  !loop j = 1 .. 200\n    x = j")
    assert rs[2].error.startswith(f"The loop ran more than {MAX_LINES:,} lines")


def test_lines_that_do_not_read():
    assert run("!loop i\n  x = i")[0].error.startswith("A loop reads `!loop i = 1 .. n`")
    assert run("!loop i = 1 .. 2.5\n  x = i")[0].error == "A loop counts in whole numbers; 2.5 is not one"
    assert run("!loop i = 1 .. 3")[0].error.startswith("The loop has nothing to run")
    assert "cannot change" in run("!loop i = 1 .. 3\n  i = 2")[0].error
    rs = run("!loop i = 1 .. 3\n  S + 1\n  !plot x, x = 0 .. 1\n  x = 1\n    y = 2\n  !loop j = 1 .. 2\n  z = 1")
    assert rs[0].error == "4 lines below need fixing"
    assert errors(rs)[2].startswith("A line in a loop assigns a name")
    assert errors(rs)[3].startswith("Only another !loop can go inside a loop; !plot")
    assert errors(rs)[5].startswith("This line's indent does not match")
    assert errors(rs)[6].startswith("This loop has nothing to run")


def test_the_text_reads_a_loop_as_one_block_with_expression_spans():
    sheet = scan(HILBERT + "\nafter = 1")
    b = sheet.owner(6)
    assert (b.kind, b.header, b.end, b.args) == ("loop", 3, 6, "i = 1 .. 3")
    assert sheet.owner(9) is None
    assert [t.text for t in sheet.line(4).tokens("name")] == ["S", "S", "i"]
    assert [t.text for t in sheet.line(5).tokens("name")] == ["j"]
    assert sheet.line(4).definition.name == "S"


def test_rename_reaches_the_loop_lines():
    edits, n = rename(HILBERT, "M", "H")
    assert apply(HILBERT, edits).splitlines()[5] == "    elem(H, i, j) = 1 / (i + j - 1)" and n == 3


def test_the_exports_print_the_steps_and_the_values():
    tex = export(HILBERT, "tex")
    assert "&\\textbf{for}\\ i = 1, \\ldots, 3 \\\\\n&\\quad S \\leftarrow S + i^{2} \\\\" in tex
    assert "S &= 14 \\\\" in tex
    assert "&\\quad \\quad {M}_{i,\\,j} \\leftarrow" in export(HILBERT, "md")
