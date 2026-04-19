# PyInstaller spec for LPBF Serializer.
# Build with: uv run pyinstaller packaging/lpbf-serializer.spec

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
project_root = Path(SPECPATH).parent
src_entry = str(project_root / "src" / "lpbf_serializer" / "__main__.py")

hidden_imports = []
hidden_imports += collect_submodules("pyvista")
hidden_imports += collect_submodules("pyvistaqt")
hidden_imports += collect_submodules("vtkmodules")
hidden_imports += collect_submodules("trimesh")
hidden_imports += collect_submodules("reportlab")

datas = []
datas += collect_data_files("pyvista")
datas += collect_data_files("vtkmodules")
datas += collect_data_files("trimesh")
datas += collect_data_files("reportlab")

a = Analysis(
    [src_entry],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "IPython", "jupyter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="LPBFSerializer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="LPBFSerializer",
)
