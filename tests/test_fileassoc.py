"""Windows .lens registration (fileassoc.py), against an in-memory stand-in for winreg."""
from contextlib import contextmanager
from pathlib import Path

from laconic import fileassoc


class FakeReg:
    HKEY_CURRENT_USER, KEY_WRITE, KEY_ALL_ACCESS, REG_SZ = "HKCU", 1, 2, 1

    def __init__(self):
        self.keys = {}   # path -> {value name: value}

    @contextmanager
    def CreateKeyEx(self, root, path, reserved, access):
        parts = path.split("\\")
        for i in range(1, len(parts) + 1):
            self.keys.setdefault("\\".join(parts[:i]), {})
        yield path

    @contextmanager
    def OpenKey(self, root, path, reserved=0, access=0):
        if path not in self.keys:
            raise FileNotFoundError(path)
        yield path

    def SetValueEx(self, key, name, reserved, kind, value):
        self.keys[key][name] = value

    def QueryValueEx(self, key, name):
        return self.keys[key][name], self.REG_SZ

    def EnumKey(self, key, i):
        children = sorted(p for p in self.keys if p.startswith(key + "\\") and "\\" not in p[len(key) + 1:])
        if i >= len(children):
            raise OSError("no more")
        return children[i][len(key) + 1:]

    def DeleteKey(self, root, path):
        assert not any(p.startswith(path + "\\") for p in self.keys), "a key with subkeys"
        del self.keys[path]


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    (bundle / fileassoc.ICON).write_bytes(b"ico")
    return bundle


def test_register_points_lens_files_at_the_program(tmp_path, monkeypatch):
    reg, bundle = FakeReg(), setup(tmp_path, monkeypatch)
    fileassoc.register(r"C:\Apps\lens.exe", bundle, winreg=reg)
    cls = r"Software\Classes"
    assert reg.keys[cls + r"\.lens"][""] == "LaconicLens.Worksheet"
    assert reg.keys[cls + r"\LaconicLens.Worksheet\shell\open\command"][""] == r'"C:\Apps\lens.exe" --window "%1"'
    icon = Path(reg.keys[cls + r"\LaconicLens.Worksheet\DefaultIcon"][""].strip('"'))
    assert icon.read_bytes() == b"ico" and str(tmp_path / "local") in str(icon)


def test_unregister_removes_what_register_wrote(tmp_path, monkeypatch):
    reg, bundle = FakeReg(), setup(tmp_path, monkeypatch)
    reg.keys[r"Software\Classes"] = {}
    fileassoc.register("lens.exe", bundle, winreg=reg)
    fileassoc.unregister(winreg=reg)
    assert set(reg.keys) <= {"Software", r"Software\Classes"}
    assert not (tmp_path / "local" / "laconic-lens").exists()


def test_unregister_leaves_an_extension_another_program_took(tmp_path, monkeypatch):
    reg, bundle = FakeReg(), setup(tmp_path, monkeypatch)
    fileassoc.register("lens.exe", bundle, winreg=reg)
    reg.keys[r"Software\Classes\.lens"][""] = "Other.App"
    fileassoc.unregister(winreg=reg)
    assert reg.keys[r"Software\Classes\.lens"][""] == "Other.App"


def test_the_command_is_only_for_the_windows_build(capsys):
    assert fileassoc.main() == 2
    assert "Windows build" in capsys.readouterr().err
