# REDCap Batch Locking

Desktop application for batch locking and unlocking REDCap forms.

## Architecture

- **Tauri shell** (`desktop/`) — native macOS app window
- **FastAPI sidecar** (`backend/`) — local API on `127.0.0.1:8765`, SQLite storage
- **Next.js UI** (`frontend/`) — local UI on `127.0.0.1:3847`

## Development

```bash
./scripts/dev-desktop.sh
```

Or manually:

```bash
# Terminal 1 — API
cd backend
source .venv/bin/activate
APP_MODE=desktop python scripts/run_desktop.py

# Terminal 2 — UI
cd frontend
npm run dev
```

Then open `http://127.0.0.1:3847/jobs`, or run the Tauri shell from `desktop/`.

## Build installer (Intel Mac)

```bash
cd desktop
npm run build:intel-mac
```

The DMG is written under `desktop/dist/` (or the Cargo target bundle path used by Tauri).

See `desktop/README.md` for more desktop packaging notes.

## Data

Desktop data (SQLite DB, reports) lives under the OS app support directory, e.g.:

`~/Library/Application Support/REDCap Batch Locking/`
