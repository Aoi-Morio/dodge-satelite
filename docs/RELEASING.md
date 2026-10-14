# Release procedure / 公開手順

External publication must wait for the project owner's explicit approval.
Local building, testing and packaging do not create a GitHub repository or release.

## Prepare locally

1. Review README/limitations, MIT attribution, dependency notices and the exact
   contents being published. Exclude personal observing profiles, cached live
   catalogs, credentials, `.venv`, build intermediates and machine-specific paths.
2. In a clean 64-bit Windows Python 3.12 environment:

   ```powershell
   python -m pip install -e ".[dev]" -c constraints-windows-py312.txt
   python -m ruff check .
   python -m ruff format --check .
   python -m pytest -q
   python -m build
   python scripts/build_windows.py
   ```

3. Confirm both executables work after moving the **entire extracted folder** to
   a different directory. Run offline demo, profile load/save and CSV export.
   Test on a separate clean Windows 11 x64 machine with no Python installation.
   The developer machine's frozen-app smoke test alone is not that clean-machine test.
4. Inspect `LICENSES/`, `installed-dependencies.json`, Python/Qt notices and exact
   matching Qt/PySide source availability. Preserve replacement/relinking rights.
   Package corresponding third-party source or arrange compliant source availability
   with the release assets before distributing binaries. Source distribution must
   include all original project code and the license.
5. Inspect SHA-256 files. Mark this as an experimental v0.2.0 and disclose unsigned
   binaries, no on-sky accuracy validation and catalog coverage limitations.

## After approval: GitHub

Choose an owner and repository name, then use GitHub's UI or `gh` to create the
repository. The commands below are instructions, not actions taken by this app:

```powershell
git add .
git commit -m "Release dodge satelite v0.2.0"
git branch -M main
# Only after approval; replace OWNER with the actual GitHub account:
gh repo create OWNER/dodge-satelite --public --source . --remote origin
git push -u origin main
```

Check the Windows and Ubuntu test matrix and the Windows build job. Download and
retest the artifact produced by that exact commit. The workflow uses read-only
repository permissions and uploads Actions artifacts; it does not create a
Release or publish packages automatically.

After the checks pass, approve the exact release assets and then tag/publish:

```powershell
git tag -a v0.2.0 -m "dodge satelite v0.2.0"
git push origin v0.2.0
gh release create v0.2.0 --draft --title "dodge satelite v0.2.0" --notes-file docs/RELEASE_NOTES.md
gh release upload v0.2.0 dist/Dodge-Satelite-0.2.0-windows-x64.zip dist/Dodge-Satelite-0.2.0-windows-x64.zip.sha256
```

Attach the source archive, required third-party source/compliance materials and
the validation record. Review the draft in GitHub before publishing. Do not use
`--clobber` to silently replace already published artifacts. PyPI publication,
code signing and installers are separate future release decisions.

日本語: 公開前にユーザーが所有者・公開先・内容を確認します。承認後にリポジトリを
作成し、CIの結果を確認してからタグと下書きReleaseを作ります。最終的な公開は
下書きの内容、ライセンス資料、未検証事項を確認した後に行います。
