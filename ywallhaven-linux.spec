# -*- mode: python ; coding: utf-8 -*-
# Linux onedir spec: produces dist/ywallhaven/ for AppImage packaging.
# (Onefile is avoided: a 300MB+ Flet bundle unpacking to /tmp on every
# start is slow; the AppImage squashfs already gives users one file.)


a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[('docs/assets/icon.png', 'docs/assets'), ('themes', 'themes')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ywallhaven',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ywallhaven',
)
