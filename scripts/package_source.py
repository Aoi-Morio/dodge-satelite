"""Package the reviewable source tree (no Git history, caches or build output)."""

import hashlib
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    listing = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT
    )
    paths = sorted(set(listing.decode("utf-8").strip("\0").split("\0")))
    output = ROOT / "dist" / "Dodge-Satelite-0.2.0-source.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative in paths:
            path = ROOT / relative
            if path.is_file():
                archive.write(path, f"dodge-satelite/{relative}")
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{checksum}  {output.name}\n", encoding="ascii")
    print(output)


if __name__ == "__main__":
    main()
