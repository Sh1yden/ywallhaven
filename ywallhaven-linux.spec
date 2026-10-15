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

# The PyInstaller bootloader exports LD_LIBRARY_PATH pointing at the
# bundle, and the externally launched Flet view client (~/.flet) would
# resolve these older copies instead of the system ones, dying with
# "undefined symbol" errors. Our process never loads them (no
# gi/tkinter/webview anywhere in app/), so drop the whole desktop/GUI
# closure: GTK stack, X11/XCB, dbus/systemd and their helpers.
# Kept on purpose: image codecs (Pillow runtime), freetype/fontconfig,
# ssl/crypto, compression, icu/sqlite, libstdc++.
GUI_LIB_PREFIXES = (
    "libgtk-3",
    "libgdk",
    "libglib-2.0",
    "libgobject-2.0",
    "libgio-2.0",
    "libgmodule",
    "libcairo",
    "libpango",
    "libatk",
    "libatspi",
    "libharfbuzz",
    "libfribidi",
    "libpixman",
    "libepoxy",
    "libglycin",
    "libcloudproviders",
    "libdatrie",
    "libthai",
    "libtinysparql",
    "libsecret",
    "libjson-glib",
    "libgraphite2",
    "libX",
    "libxcb",
    "libxkb",
    "libdbus-1",
    "libsystemd",
    "libtss2",
    "libseccomp",
    "libmount",
    "libblkid",
    "libgcrypt",
    "libgpg-error",
)
a.binaries = [
    entry
    for entry in a.binaries
    if not entry[0].startswith(GUI_LIB_PREFIXES)
]
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
