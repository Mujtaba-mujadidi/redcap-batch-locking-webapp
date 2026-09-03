# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

backend_root = Path(SPECPATH)

datas = [
    (str(backend_root / "alembic"), "alembic"),
    (str(backend_root / "alembic.ini"), "."),
    (str(backend_root / "app" / "templates"), "app/templates"),
    (str(backend_root / "app" / "static"), "app/static"),
]

hiddenimports = [
    "app.main",
    "app.models",
    "app.models.audit",
    "app.models.enums",
    "app.models.job",
    "app.models.mapping",
    "app.models.redcap",
    "app.models.redcap_api_key_cache",
    "app.models.session",
    "app.models.setting",
    "app.models.user",
    "app.services.job_queue",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "passlib.handlers.bcrypt",
]

a = Analysis(
    [str(backend_root / "scripts" / "run_desktop.py")],
    pathex=[str(backend_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.datas,
    [],
    name="redcap-api",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
