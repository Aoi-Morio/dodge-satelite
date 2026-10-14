"""Collect Astropy runtime without importing test/plot-only optional packages.

Astropy 8's visualization import can raise pytest's Skipped (a BaseException)
during the stock hook's all-submodule scan when matplotlib is absent.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata


def runtime_module(name):
    return (
        ".tests" not in name
        and not name.endswith("conftest")
        and not name.startswith("astropy.visualization")
    )


hiddenimports = collect_submodules("astropy", filter=runtime_module)
hiddenimports.append("numpy.lib.recfunctions")
excludedimports = ["astropy.visualization", "astropy.conftest"]
datas = collect_data_files("astropy", excludes=["**/tests/**"])
datas += copy_metadata("astropy") + copy_metadata("numpy")
# Unit parsers also access their generated Python tables through file paths.
datas += collect_data_files(
    "astropy", include_py_files=True, includes=["**/*_lextab.py", "**/*_parsetab.py"]
)
