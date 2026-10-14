"""Build a replaceable-library Windows folder, smoke-test it, then zip it.

Run on Windows with the project's development dependencies installed.
Never publishes, uploads or creates a GitHub release.
"""

import json
import os
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def collect_licenses(destination):
    destination.mkdir(parents=True, exist_ok=True)
    manifest = []
    for dist in metadata.distributions():
        name = dist.metadata.get("Name", "unknown")
        if name == "dodge-satelite":
            continue
        manifest.append(
            {
                "name": name,
                "version": dist.version,
                "license_expression": dist.metadata.get("License-Expression"),
                "home_page": dist.metadata.get("Home-page"),
                "project_urls": dist.metadata.get_all("Project-URL") or [],
            }
        )
        for relative in dist.files or []:
            path = Path(str(relative))
            if any(part == ".." for part in path.parts):
                continue
            if any(
                word in str(path).lower() for word in ("license", "copying", "copyright", "notice")
            ):
                source = Path(dist.locate_file(relative))
                if source.is_file() and source.suffix.lower() not in {".pyc", ".pyd", ".dll"}:
                    target = destination / name / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, destination / "Python-LICENSE.txt")
    shutil.copytree(ROOT / "licenses", destination / "additional", dirs_exist_ok=True)
    (destination / "installed-dependencies.json").write_text(
        json.dumps(sorted(manifest, key=lambda x: x["name"].lower()), indent=2), encoding="utf-8"
    )


def main():
    if sys.platform != "win32":
        raise SystemExit("Windows builds must be created on Windows.")
    os.chdir(ROOT)
    spec = ROOT / "build" / "DodgeSatelite.spec"
    spec.parent.mkdir(exist_ok=True)
    spec.write_text(
        """from PyInstaller.utils.hooks import collect_data_files
from pathlib import Path
root = Path(SPECPATH).parent
datas = collect_data_files('dodge_satelite') + collect_data_files('skyfield')
a = Analysis([str(root / 'scripts' / 'launcher.py')], pathex=[str(root / 'src')],
             binaries=[], datas=datas, hookspath=[str(root / 'scripts' / 'hooks')],
             hiddenimports=['dodge_satelite.gui'],
             excludes=['PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets',
                       'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtPdf',
                       'tkinter', 'IPython', 'matplotlib', 'pytest',
                       'astropy.visualization', 'astropy.conftest'])
# Qt's generic plugin collection can pull in unused PDF/virtual-keyboard/QML
# runtimes. This Widgets application requires only these shared Qt libraries.
qt_libraries = {'qt6core.dll', 'qt6gui.dll', 'qt6widgets.dll', 'qt6network.dll',
                'qt6opengl.dll', 'qt6svg.dll'}
def required_binary(entry):
    name = Path(entry[0]).name.lower()
    if name in {'qpdf.dll', 'qtvirtualkeyboardplugin.dll'}:
        return False
    return not (name.startswith('qt6') and name.endswith('.dll') and name not in qt_libraries)
a.binaries = [entry for entry in a.binaries if required_binary(entry)]
pyz = PYZ(a.pure)
cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name='dodge-satelite', console=True)
gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Dodge-Satelite-GUI', console=False)
COLLECT(cli, gui, a.binaries, a.datas, name='Dodge-Satelite')
""",
        encoding="utf-8",
    )
    # Do not collect same-named DLLs from unrelated tools (e.g. Poppler's ICU)
    # that happen to be on the developer machine's PATH. Qt uses Windows ICU.
    windows = Path(os.environ["SystemRoot"])
    build_env = dict(os.environ)
    build_env["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), sys.base_prefix, str(windows / "System32"), str(windows)]
    )
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec)],
        check=True,
        env=build_env,
    )
    bundle = ROOT / "dist" / "Dodge-Satelite"
    for name in (
        "README.md",
        "README.ja.md",
        "LICENSE",
        "THIRD_PARTY_NOTICES.md",
        "CHANGELOG.md",
        "constraints-windows-py312.txt",
    ):
        shutil.copy2(ROOT / name, bundle / name)
    shutil.copytree(ROOT / "examples", bundle / "examples", dirs_exist_ok=True)
    shutil.copytree(ROOT / "docs", bundle / "docs", dirs_exist_ok=True)
    collect_licenses(bundle / "LICENSES")
    subprocess.run([str(bundle / "dodge-satelite.exe"), "--version"], check=True, timeout=60)
    demo_out = ROOT / "build" / "frozen-demo"
    subprocess.run(
        [str(bundle / "dodge-satelite.exe"), "demo", "--out", str(demo_out)],
        check=True,
        timeout=120,
    )
    report = json.loads((demo_out / "report.json").read_text(encoding="utf-8"))
    if report["summary"]["transit_count"] != 1 or report["summary"]["exposure_count"] == 0:
        raise RuntimeError("Frozen demo did not produce the expected crossing and schedule.")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    subprocess.run(
        [str(bundle / "Dodge-Satelite-GUI.exe"), "--smoke-test"], env=env, check=True, timeout=60
    )
    archive = shutil.make_archive(
        str(ROOT / "dist" / "Dodge-Satelite-0.2.0-windows-x64"),
        "zip",
        root_dir=bundle.parent,
        base_dir=bundle.name,
    )
    import hashlib

    checksum = hashlib.sha256(Path(archive).read_bytes()).hexdigest()
    Path(archive + ".sha256").write_text(f"{checksum}  {Path(archive).name}\n", encoding="ascii")
    print(f"Built and smoke-tested: {archive}")


if __name__ == "__main__":
    main()
