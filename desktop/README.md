# REDCap Batch Locking — Desktop App

Installable Mac/Windows desktop app: one icon to open, no Docker, PostgreSQL, Redis, Celery, Python, or Node required **for end users**.

## End users

After your team builds an installer:

| Platform | Installer | Install |
| --- | --- | --- |
| macOS | `.dmg` in `desktop/src-tauri/target/release/bundle/dmg/` | Open DMG → drag app to Applications |
| Windows | `.msi` in `desktop/src-tauri/target/release/bundle/msi/` | Run installer |

Then launch **REDCap Batch Locking** from Applications / Start Menu like any other app.

- No login screen (local desktop session)
- Data stored locally (macOS: `~/Library/Application Support/REDCap Batch Locking/`)
- App stops working after `APP_EXPIRY_DATE` until an updated installer is installed

---

## Developers: build an installer

### Prerequisites

| Tool | Purpose |
| --- | --- |
| **Python 3.12+** (native arch) | PyInstaller API sidecar |
| **Node.js 20+** | Next.js UI bundle |
| **Rust + Cargo** | Tauri shell + `.dmg` / `.msi` |
| **Xcode CLT** (macOS) | Tauri bundling |

> **Apple Silicon:** use a native **arm64** Python venv (`python3 -c "import platform; print(platform.machine())"` → `arm64`).  
> If your venv is x86_64 (Rosetta), build an Intel Mac app instead: `npm run build:intel-mac`.

### One-time setup

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd ../frontend
npm install

# Desktop shell
cd ../desktop
npm install
```

### Build Mac installer

```bash
cd desktop
npm run build
```

Output: `dist/REDCap Batch Locking_0.1.0_x64.dmg` (also `.app` under `src-tauri/target/.../bundle/macos/`)

Intel Mac (Rosetta / x86_64 Python):

```bash
cd desktop
npm run build:intel-mac
```

### Build artifacts only (no `.dmg`)

Useful for debugging sidecars:

```bash
./scripts/build-desktop-artifacts.sh
```

Creates:

- `desktop/src-tauri/binaries/redcap-api-<target-triple>` — bundled FastAPI + SQLite
- `desktop/src-tauri/resources/ui/` — Next.js standalone server
- `desktop/src-tauri/resources/node/node` — bundled Node runtime

### Local development (no installer)

```bash
./scripts/dev-desktop.sh
```

Opens the UI at http://localhost:3847 (browser or `cd desktop && npm run dev` for the Tauri window).

---

## Architecture

```
┌─────────────────────────────────────┐
│  Tauri native window (.app)         │
│  loads http://127.0.0.1:3000/app    │
└──────────────┬──────────────────────┘
               │ starts on launch
     ┌─────────┴──────────┐
     ▼                    ▼
┌─────────────┐    ┌──────────────────┐
│ redcap-api  │    │ node server.js   │
│ PyInstaller │    │ Next standalone  │
│ :8765       │    │ :3000            │
└──────┬──────┘    └──────────────────┘
       │
       ▼
  SQLite (local app data dir)
  In-process background worker
```

---

## Configuration

| Variable | Default | Set at |
| --- | --- | --- |
| `APP_EXPIRY_DATE` | `2027-02-28` | Build time (`build-desktop-artifacts.sh`) |
| `APP_DATA_DIR` | OS app-support folder | Runtime (automatic) |

To change expiry for a release:

```bash
APP_EXPIRY_DATE=2028-06-30 npm run build
```

---

## Troubleshooting

**Build fails: “API sidecar is x86_64 but requires arm64”**  
Recreate `backend/.venv` with native arm64 Python, or use `npm run build:intel-mac`.

**Build fails: `cargo metadata` not found**  
Install Rust: https://rustup.rs

**App window is blank**  
Check logs in `~/Library/Logs/uk.ac.oxford.redcap.batchlocking/` (macOS).

**Gatekeeper blocks the app (unsigned build)**  
Right-click → Open, or sign/notarize for production distribution.
