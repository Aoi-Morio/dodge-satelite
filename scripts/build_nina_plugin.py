"""Build a NINA 3.2 sequencer plugin plus a private, Qt-free Python engine.

No installation into a user's NINA profile, camera operation, or publication.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
NAME = "Dodge-Satelite-NINA-0.2.0-windows-x64"


def license_bundle(destination):
    destination.mkdir(parents=True, exist_ok=True)
    pending = ["numpy", "astropy", "skyfield", "sgp4", "pyinstaller"]
    seen, versions = set(), []
    while pending:
        name = pending.pop()
        dist = metadata.distribution(name)
        canonical = dist.metadata["Name"].lower().replace("_", "-")
        if canonical in seen:
            continue
        seen.add(canonical)
        versions.append(
            {
                "name": dist.metadata["Name"],
                "version": dist.version,
                "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
                "project_urls": dist.metadata.get_all("Project-URL") or [],
            }
        )
        for requirement in dist.requires or []:
            dependency = Requirement(requirement)
            if dependency.marker is None or dependency.marker.evaluate({"extra": ""}):
                pending.append(dependency.name)
        for relative in dist.files or []:
            path = Path(str(relative))
            if ".." in path.parts:
                continue
            if any(
                word in str(path).lower() for word in ("license", "copying", "notice", "copyright")
            ):
                source = Path(dist.locate_file(relative))
                if source.is_file() and source.suffix.lower() not in {".pyc", ".pyd", ".dll"}:
                    target = destination / dist.metadata["Name"] / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.exists():
        shutil.copy2(python_license, destination / "Python-LICENSE.txt")
    (destination / "dependencies.json").write_text(json.dumps(versions, indent=2), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dotnet", default="dotnet")
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("NINA plugin packages must be built on Windows x64.")
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT="1")
    subprocess.run(
        [
            args.dotnet,
            "build",
            "nina/DodgeSatelite.NINA/DodgeSatelite.NINA.csproj",
            "-c",
            "Release",
            "--nologo",
        ],
        cwd=ROOT,
        check=True,
        env=environment,
    )
    # Restrict dependency discovery to this runtime and Windows, not unrelated PATH tools.
    windows = Path(os.environ["SystemRoot"])
    environment["PATH"] = os.pathsep.join(
        [str(Path(sys.executable).parent), sys.base_prefix, str(windows / "System32"), str(windows)]
    )
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name",
        "dodge-satelite-engine",
        "--paths",
        "src",
        "--additional-hooks-dir",
        "scripts/hooks",
        "--collect-data",
        "dodge_satelite",
        "--collect-data",
        "skyfield",
        "--distpath",
        "build/nina-engine-dist",
        "--workpath",
        "build/nina-pyi",
        "--specpath",
        "build/nina-spec",
    ]
    for module in (
        "PySide6",
        "PyQt5",
        "PyQt6",
        "shiboken6",
        "matplotlib",
        "IPython",
        "tkinter",
        "pytest",
    ):
        command += ["--exclude-module", module]
    command += ["scripts/nina_engine.py"]
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    staged = ROOT / "build" / "nina-package"
    staged.mkdir(parents=True, exist_ok=True)
    compiled = ROOT / "nina/DodgeSatelite.NINA/bin/Release/net8.0-windows"
    for name in ("DodgeSatelite.NINA.dll", "DodgeSatelite.Gate.dll"):
        shutil.copy2(compiled / name, staged / name)
    engine = staged / "Engine"
    shutil.copytree(
        ROOT / "build/nina-engine-dist/dodge-satelite-engine", engine, dirs_exist_ok=True
    )
    if list(engine.rglob("Qt6*.dll")) or list(engine.rglob("PySide6")):
        raise RuntimeError("Unexpected Qt runtime in the headless engine.")
    license_bundle(staged / "LICENSES")
    shutil.copy2(ROOT / "LICENSE", staged / "LICENSE")
    for source, destination in (
        ("nina/README.md", "README.md"),
        ("nina/README.ja.md", "README.ja.md"),
        ("nina/THIRD_PARTY_NOTICES.md", "THIRD_PARTY_NOTICES.md"),
        ("nina/VALIDATION.md", "VALIDATION.md"),
        ("nina/REGISTRY_SUBMISSION.md", "REGISTRY_SUBMISSION.md"),
        ("nina/TRY_IT.ja.md", "TRY_IT.ja.md"),
        ("nina/REVIEW_REPORT.ja.md", "REVIEW_REPORT.ja.md"),
    ):
        shutil.copy2(ROOT / source, staged / destination)
    # Exercise the actual frozen bridge offline, including a Unicode-safe JSON protocol.
    from dodge_satelite.cli import demo_inputs

    config, _ = demo_inputs()
    fixture = ROOT / "src/dodge_satelite/data/demo.csv"
    request = {
        "schema_version": 1,
        "request_id": "frozen-plugin-smoke",
        "config": config.to_dict(),
        "catalog_path": str(fixture),
    }
    run = subprocess.run(
        [str(engine / "dodge-satelite-engine.exe"), "nina-bridge"],
        input=json.dumps(request).encode(),
        capture_output=True,
        timeout=60,
    )
    response = json.loads(run.stdout)
    if run.returncode != 0 or response.get("status") != "ok" or len(response["windows"]) != 2:
        raise RuntimeError(f"Frozen engine smoke test failed: {response}")
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    (staged / "BUILD-PROVENANCE.json").write_text(
        json.dumps(
            {
                "plugin_version": "0.2.0.0",
                "nina_sdk": "3.2.0.9001",
                "source_commit": sha,
                "python": sys.version,
                "protocol": 1,
                "qt_runtime": False,
                "validation": "Frozen offline engine smoke passed; see VALIDATION.md for host tests/limits.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (ROOT / "dist").mkdir(exist_ok=True)
    archive = Path(shutil.make_archive(str(ROOT / "dist" / NAME), "zip", root_dir=staged))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    Path(str(archive) + ".sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    manifest = {
        "Name": "dodge satelite",
        "Channel": "Beta",
        "Identifier": "ecb4f88d-f91a-4c0a-b7a5-a0eb028a3782",
        "Version": {"Major": 0, "Minor": 2, "Patch": 0, "Build": 0},
        "Author": "Morio Aoi",
        "License": "MIT",
        "LicenseURL": "https://github.com/Aoi-Morio/dodge-satelite/blob/main/LICENSE",
        "Repository": "https://github.com/Aoi-Morio/dodge-satelite",
        "MinimumApplicationVersion": {"Major": 3, "Minor": 2, "Patch": 0, "Build": 9001},
        "Descriptions": {
            "ShortDescription": "Experimental satellite-aware light exposures for Advanced Sequencer.",
            "LongDescription": "Uses NINA site, target and equipment. Waits for a catalog-predicted exposure window. Does not guarantee clean frames. AI-assisted development; human review required before official catalog submission.",
        },
        "Installer": {
            "URL": f"https://github.com/Aoi-Morio/dodge-satelite/releases/download/nina-v0.2.0/{archive.name}",
            "Type": "ARCHIVE",
            "ChecksumType": "SHA256",
            "Checksum": digest,
        },
        "Tags": ["Satellite", "Imaging", "Sequencer"],
    }
    (ROOT / "dist/Dodge-Satelite-NINA-0.2.0.manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Built NINA plugin + Qt-free engine: {archive}")


if __name__ == "__main__":
    main()
