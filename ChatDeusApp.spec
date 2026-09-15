# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules

azure_datas, azure_binaries, azure_hidden = collect_all("azure.cognitiveservices.speech")
hiddenimports = list(azure_hidden)
hiddenimports += collect_submodules("twitchio")
hiddenimports += collect_submodules("obswebsocket")
hiddenimports += collect_submodules("websocket")
hiddenimports += collect_submodules("edge_tts")

a = Analysis(
    ["chatdeus_app.py"],
    pathex=[],
    binaries=azure_binaries,
    datas=azure_datas + [
        ("templates", "templates"),
        ("static", "static"),
        ("LICENSE", "."),
        ("NOTICE.md", "."),
        ("VERSION", "."),
    ],
    hiddenimports=hiddenimports,
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False, optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name="ChatDeusApp", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True, upx_exclude=[], runtime_tmpdir=None,
    console=False, disable_windowed_traceback=False, argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
)
