"""Write the license texts of everything the frozen build bundles, for THIRD-PARTY-NOTICES.txt.

Usage: notices.py OUT. The packages are laconic's installed dependencies, followed down to their
own (extras left out), each with the license files its wheel ships; then Python itself and the
PyInstaller bootloader. The front-end files under laconic/static carry their licenses beside them.
lens.spec runs it, so run it in the environment that builds."""
import importlib.metadata as md
import os
import sys

from packaging.requirements import Requirement  # a dependency of PyInstaller

LICENSE_NAMES = ("LICENSE", "LICENCE", "COPYING", "NOTICE")


def dependencies(root):
    """The installed distributions root needs at run time, by normalized name, root excluded."""
    seen, todo = {}, [root]
    while todo:
        for spec in md.distribution(todo.pop()).requires or []:
            req = Requirement(spec)
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue  # an extra, or another platform's
            key = req.name.lower().replace("_", "-")
            if key not in seen:
                seen[key] = md.distribution(req.name)
                todo.append(req.name)
    return [seen[k] for k in sorted(seen)]


def license_files(dist):
    """(name, text) of each license file in the distribution's .dist-info folder."""
    out = []
    for f in dist.files or []:
        if ".dist-info" in f.parts[0] and f.name.upper().startswith(LICENSE_NAMES):
            out.append(("/".join(f.parts[1:]), f.locate().read_text(encoding="utf-8", errors="replace")))
    return out


def summary(dist):
    m = dist.metadata
    if m.get("License-Expression"):
        return m["License-Expression"]
    classifiers = [c.rsplit(" :: ", 1)[-1] for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
    short = (m.get("License") or "").strip()
    return ", ".join(classifiers) or (short if short and "\n" not in short else "see below")


def section(title, texts):
    rule = "=" * 78
    body = "\n\n".join(f"--- {name} ---\n\n{text.strip()}" for name, text in texts)
    return f"{rule}\n{title}\n{rule}\n\n{body}\n"


def main(out):
    parts = ["LENS bundles the software below. Each part is under its own license, given in full.\n"]
    for dist in dependencies("laconic"):
        texts = license_files(dist)
        if not texts:
            print(f"::warning::{dist.name} {dist.version} ships no license file; only its license name is listed",
                  file=sys.stderr)
        parts.append(section(f"{dist.name} {dist.version} ({summary(dist)})", texts))
    python_license = os.path.join(os.path.dirname(os.__file__), "LICENSE.txt")  # Linux and macOS layout
    if not os.path.exists(python_license):
        python_license = os.path.join(sys.base_prefix, "LICENSE.txt")  # Windows layout
    with open(python_license, encoding="utf-8") as f:
        parts.append(section(f"Python {sys.version.split()[0]} (PSF-2.0)", [("LICENSE.txt", f.read())]))
    pyinstaller = md.distribution("pyinstaller")
    parts.append(section(f"PyInstaller {pyinstaller.version} bootloader (GPL-2.0 with the bootloader exception)",
                         license_files(pyinstaller)))
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(parts))


if __name__ == "__main__":
    main(sys.argv[1])
