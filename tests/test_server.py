import pytest
from fastapi.testclient import TestClient

from laconic import settings


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LENS_CONFIG_DIR", str(tmp_path))
    from laconic.server import app
    return TestClient(app)


def test_defaults_when_nothing_is_stored(client):
    assert client.get("/api/settings").json() == {"greek": None, "units": []}


def test_greek_table_is_stored_and_can_be_reset(client):
    assert client.put("/api/greek", json={"greek": {"a": "ȧ"}}).json() == {"ok": True}
    assert client.get("/api/settings").json()["greek"] == {"a": "ȧ"}
    client.put("/api/greek", json={"greek": None})
    assert client.get("/api/settings").json()["greek"] is None


def test_units_are_validated_before_anything_is_stored(client):
    bad = client.put("/api/units", json={"units": [
        {"name": "smoot", "definition": "1.7018'm"}, {"name": "m", "definition": "2'ft"}]}).json()
    assert bad["ok"] is False and bad["errors"][0] is None and "already a unit" in bad["errors"][1]
    assert client.get("/api/settings").json()["units"] == []
    ok = client.put("/api/units", json={"units": [{"name": " smoot ", "definition": " 1.7018'm "}]}).json()
    assert ok["ok"] is True
    assert client.get("/api/settings").json()["units"] == [{"name": "smoot", "definition": "1.7018'm"}]


def test_stored_units_reach_every_endpoint(client):
    client.put("/api/units", json={"units": [{"name": "smoot", "definition": "1.7018'm"}]})
    sheet = {"text": "d = 3'smoot -> 'm", "title": "t"}
    assert "5.105" in client.post("/api/eval", json=sheet).json()[0]["text"]
    assert "\\DeclareSIUnit{\\smoot}" in client.post("/api/export", json=sheet).text
    assert "'smoot = 1.7018'm" in client.post("/api/save", json=sheet).text
    assert client.get("/api/vocab").json()["globalUnits"] == [["smoot", "1.7018'm"]]


def test_vocabulary_has_what_the_editor_completes(client):
    v = client.get("/api/vocab").json()
    units = {u[0]: u for u in v["units"]}
    assert units["kN"][1] == "kilonewton" and units["kN"][2] == 1 and "mm" in units and "GPa" in units
    assert ["sqrt", "sqrt(x)"] in v["functions"] and "pi" in v["constants"]
    assert [c[0] for c in v["commands"]] == ["clear", "noassume", "assume"]


def test_settings_survive_a_broken_file(client, tmp_path):
    (tmp_path / "settings.json").write_text("{not json")
    assert client.get("/api/settings").json() == {"greek": None, "units": []}
    assert settings.global_units() == []


def test_saving_one_setting_keeps_the_other(client):
    client.put("/api/greek", json={"greek": {"a": "ȧ"}})
    client.put("/api/units", json={"units": [{"name": "smoot", "definition": "1.7018'm"}]})
    client.put("/api/greek", json={"greek": {"b": "ḃ"}})
    cfg = client.get("/api/settings").json()
    assert cfg["greek"] == {"b": "ḃ"} and cfg["units"][0]["name"] == "smoot"
