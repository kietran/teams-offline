# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "packaging" / "launcher.py")],
    pathex=[str(root / "backend")],
    binaries=[],
    datas=[(str(root / "frontend" / "dist"), "frontend_dist")],
    hiddenimports=[
        "uvicorn.logging", "uvicorn.loops.asyncio", "uvicorn.protocols.http.h11_impl",
        "playwright.async_api",
    ],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[], noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True, name="Teams Offline Archive",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=True, console=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas, strip=False, upx=True,
    upx_exclude=[], name="Teams Offline Archive",
)
