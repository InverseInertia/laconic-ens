"""The API endpoints, called as plain functions (no HTTP client needed)."""
import pytest

from laconic import server, settings
from laconic.commands import COMMANDS, help_rows
from laconic.server import GreekBody, Sheet, UnitRow, UnitsBody


@pytest.fixture(autouse=True)
def config(tmp_path, monkeypatch):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))
    return tmp_path


def put_units(*pairs):
    return server.put_units(UnitsBody(units=[UnitRow(name=n, definition=d) for n, d in pairs]))


def test_defaults_when_nothing_is_stored():
    assert server.get_settings() == {"welcomed": False, "greek": None, "units": []}


def test_greek_table_is_stored_and_can_be_reset():
    assert server.put_greek(GreekBody(greek={"a": "ȧ"})) == {"ok": True}
    assert server.get_settings()["greek"] == {"a": "ȧ"}
    server.put_greek(GreekBody(greek=None))
    assert server.get_settings()["greek"] is None


def test_units_are_validated_before_anything_is_stored():
    bad = put_units(("smoot", "1.7018'm"), ("m", "2'ft"))
    assert bad["ok"] is False and bad["errors"][0] is None and "already a unit" in bad["errors"][1]
    assert server.get_settings()["units"] == []
    assert put_units((" smoot ", " 1.7018'm "))["ok"] is True
    assert server.get_settings()["units"] == [{"name": "smoot", "definition": "1.7018'm"}]


def test_stored_units_reach_every_endpoint():
    put_units(("smoot", "1.7018'm"))
    sheet = Sheet(text="d = 3'smoot -> 'm", title="t")
    assert "5.105" in server.evaluate(sheet)[0]["text"]
    assert "\\DeclareSIUnit{\\smoot}" in server.export(sheet)
    assert "'smoot = 1.7018'm" in server.save(sheet)
    assert server.vocab()["globalUnits"] == [["smoot", "1.7018'm"]]


def test_vocabulary_has_what_the_editor_completes():
    v = server.vocab()
    units = {u[0]: u for u in v["units"]}
    assert units["kN"][1] == "kilonewton" and units["kN"][2] == 1 and "mm" in units and "GPa" in units
    assert ["sqrt", "sqrt(x)"] in v["functions"] and "pi" in v["constants"]
    assert v["commands"] == [[c.name, c.summary] for c in COMMANDS]


def test_the_page_carries_the_command_help_rows():
    page = server.index().body.decode()
    assert help_rows() in page and "<!-- command help" not in page


def test_settings_survive_a_broken_file(config):
    (config / "settings.json").write_text("{not json")
    assert server.get_settings() == {"welcomed": False, "greek": None, "units": []}
    assert settings.global_units() == []


def test_saving_one_setting_keeps_the_other():
    server.put_greek(GreekBody(greek={"a": "ȧ"}))
    put_units(("smoot", "1.7018'm"))
    server.put_greek(GreekBody(greek={"b": "ḃ"}))
    cfg = server.get_settings()
    assert cfg["greek"] == {"b": "ḃ"} and cfg["units"][0]["name"] == "smoot"


def test_vocabulary_has_solver_options_and_methods():
    v = server.vocab()["solver"]
    assert [k for k, _ in v["keys"]["root"]][:2] == ["equation", "bounds"]
    assert "objective" in [k for k, _ in v["keys"]["minimize"]]
    assert [m for m, _ in v["methods"]["root"]] == ["hybr", "lm", "broyden1", "broyden2", "krylov", "brentq"]
    assert "SLSQP" in [m for m, _ in v["methods"]["optimize"]] and all(d for _, d in v["methods"]["optimize"])
    assert [c for c, _ in v["choices"]["autorun"]] == ["on", "off"]


def test_props_vocabulary_lists_keys_and_fluids():
    v = server.vocab_props()
    keys = {k[0]: k for k in v["keys"]}
    assert keys["T"][1:] == ["Temperature", "K", True, False]
    assert keys["Tcrit"][4] is True and keys["Cpmass"][3] is False and keys["Prandtl"][2] == ""
    names = [f[0] for f in v["fluids"]]
    assert names[:2] == ["Water", "Air"] and "R134a" in names and "INCOMP::MEG[0.3]" in names
    assert "H2O" in dict(v["fluids"])["Water"]


def test_examples_are_served_from_the_package(config):
    names = [e["name"] for e in server.list_examples()]
    assert {"beam", "plots", "solve"} <= set(names)
    assert "L = 4.5'm" in server.get_example("beam").body.decode()
    with pytest.raises(Exception):
        server.get_example("../settings")


def test_welcomed_flag_is_remembered(config):
    assert server.get_settings()["welcomed"] is False
    server.put_welcomed()
    assert server.get_settings()["welcomed"] is True
