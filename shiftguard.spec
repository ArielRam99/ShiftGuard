from PyInstaller.utils.hooks import collect_submodules


hidden_imports = collect_submodules("sklearn")

analysis = Analysis(
    ["run_shiftguard.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("shiftguard/schema.sql", "shiftguard"),
        ("shiftguard/static", "shiftguard/static"),
        ("shiftguard/templates", "shiftguard/templates"),
        ("sample_data", "sample_data"),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="ShiftGuard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

collection = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ShiftGuard",
)