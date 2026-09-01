#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
TAURI_DIR="$ROOT_DIR/desktop/src-tauri"
BINARIES_DIR="$TAURI_DIR/binaries"
RESOURCES_DIR="$TAURI_DIR/resources"
UI_DIR="$RESOURCES_DIR/ui"
NODE_DIR="$RESOURCES_DIR/node"
APP_EXPIRY_DATE="${APP_EXPIRY_DATE:-2027-02-28}"
NODE_VERSION="${NODE_VERSION:-20.18.0}"

log() {
  printf '==> %s\n' "$*"
}

resolve_target_triple() {
  if [[ -n "${TAURI_TARGET:-}" ]]; then
    echo "$TAURI_TARGET"
    return
  fi

  local os python_arch
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  python_arch="$(python - <<'PY'
import platform
print(platform.machine())
PY
)"

  if [[ "$(uname -m)" != "$python_arch" ]]; then
    echo "WARNING: Python architecture (${python_arch}) differs from host ($(uname -m))." >&2
    echo "WARNING: Use a native Python virtualenv when building Apple Silicon installers." >&2
  fi

  case "${os}-${python_arch}" in
    darwin-arm64) echo "aarch64-apple-darwin" ;;
    darwin-x86_64) echo "x86_64-apple-darwin" ;;
    linux-x86_64) echo "x86_64-unknown-linux-gnu" ;;
    linux-aarch64 | linux-arm64) echo "aarch64-unknown-linux-gnu" ;;
    mingw*-x86_64 | msys*-x86_64) echo "x86_64-pc-windows-msvc" ;;
    *)
      echo "Unsupported build host: ${os}-${python_arch}" >&2
      exit 1
      ;;
  esac
}

resolve_node_arch() {
  local target arch
  target="${TAURI_TARGET:-$(rustc --print host-tuple 2>/dev/null || uname -m)}"
  case "$target" in
    *aarch64* | *arm64*) echo "arm64" ;;
    *x86_64*) echo "x64" ;;
    *)
      arch="$(uname -m)"
      case "$arch" in
        arm64 | aarch64) echo "arm64" ;;
        x86_64 | amd64) echo "x64" ;;
        *)
          echo "Unsupported CPU architecture for bundled Node.js: $target" >&2
          exit 1
          ;;
      esac
      ;;
  esac
}

resolve_node_os() {
  local os
  os="$(uname -s | tr '[:upper:]' '[:lower:]')"
  case "$os" in
    darwin) echo "darwin" ;;
    linux) echo "linux" ;;
    mingw* | msys* | cygwin*) echo "win" ;;
    *)
      echo "Unsupported OS for bundled Node.js: $os" >&2
      exit 1
      ;;
  esac
}

build_api_sidecar() {
  log "Building Python API sidecar with PyInstaller"
  cd "$BACKEND_DIR"

  if [[ ! -d ".venv" ]]; then
    echo "Missing backend/.venv. Create it and install requirements before building." >&2
    exit 1
  fi

  # shellcheck disable=SC1091
  source .venv/bin/activate
  python -m pip install --quiet pyinstaller
  pyinstaller redcap-api.spec --noconfirm --clean

  local target_triple sidecar_name
  target_triple="$(resolve_target_triple)"
  sidecar_name="redcap-api-${target_triple}"
  mkdir -p "$BINARIES_DIR"
  cp "dist/redcap-api" "$BINARIES_DIR/$sidecar_name"
  chmod +x "$BINARIES_DIR/$sidecar_name"

  local built_arch
  built_arch="$(file -b "dist/redcap-api" | awk '{print $NF}')"
  case "$sidecar_name" in
    *aarch64-apple-darwin)
      if [[ "$built_arch" != "arm64" ]]; then
        echo "Built API sidecar is ${built_arch}, but ${sidecar_name} requires arm64." >&2
        echo "Recreate backend/.venv with native arm64 Python, or build with:" >&2
        echo "  TAURI_TARGET=x86_64-apple-darwin npm run build" >&2
        exit 1
      fi
      ;;
    *x86_64-apple-darwin)
      if [[ "$built_arch" != "x86_64" ]]; then
        echo "Built API sidecar is ${built_arch}, but ${sidecar_name} requires x86_64." >&2
        exit 1
      fi
      ;;
  esac

  log "API sidecar written to $BINARIES_DIR/$sidecar_name (${built_arch})"
}

build_frontend_bundle() {
  log "Building Next.js standalone UI bundle"
  cd "$FRONTEND_DIR"

  if [[ ! -d node_modules ]]; then
    npm install
  fi

  export NEXT_PUBLIC_APP_MODE=desktop
  export NEXT_PUBLIC_BACKEND_ORIGIN="http://127.0.0.1:8765"
  export BACKEND_ORIGIN="http://127.0.0.1:8765"
  npm run build

  rm -rf "$UI_DIR"
  mkdir -p "$UI_DIR"
  cp -R .next/standalone/. "$UI_DIR/"
  mkdir -p "$UI_DIR/.next"
  cp -R .next/static "$UI_DIR/.next/static"
  if [[ -d public ]]; then
    cp -R public "$UI_DIR/public"
  fi

  log "UI bundle written to $UI_DIR"
}

download_node_runtime() {
  local node_os node_arch archive_name extract_dir download_url node_binary
  node_os="$(resolve_node_os)"
  node_arch="$(resolve_node_arch)"

  if [[ "$node_os" == "win" ]]; then
    archive_name="node-v${NODE_VERSION}-win-${node_arch}.zip"
    download_url="https://nodejs.org/dist/v${NODE_VERSION}/${archive_name}"
    node_binary="node.exe"
  else
    archive_name="node-v${NODE_VERSION}-${node_os}-${node_arch}.tar.gz"
    download_url="https://nodejs.org/dist/v${NODE_VERSION}/${archive_name}"
    node_binary="bin/node"
  fi

  local cache_dir="$ROOT_DIR/.desktop-build-cache"
  local archive_path="$cache_dir/$archive_name"
  mkdir -p "$cache_dir" "$NODE_DIR"

  if [[ ! -f "$archive_path" ]]; then
    log "Downloading Node.js ${NODE_VERSION} (${node_os}/${node_arch})"
    curl -fsSL "$download_url" -o "$archive_path"
  else
    log "Using cached Node.js archive $archive_path"
  fi

  rm -rf "$NODE_DIR"/*
  extract_dir="$(mktemp -d)"
  if [[ "$archive_name" == *.zip ]]; then
    unzip -q "$archive_path" -d "$extract_dir"
  else
    tar -xzf "$archive_path" -C "$extract_dir"
  fi

  cp "$extract_dir"/node-v${NODE_VERSION}-*/"$node_binary" "$NODE_DIR/node"
  chmod +x "$NODE_DIR/node"
  rm -rf "$extract_dir"
  log "Node runtime written to $NODE_DIR/node"
}

write_build_metadata() {
  cat >"$TAURI_DIR/build-metadata.json" <<EOF
{
  "app_expiry_date": "${APP_EXPIRY_DATE}",
  "backend_origin": "http://127.0.0.1:8765",
  "frontend_origin": "http://127.0.0.1:3847",
  "node_version": "${NODE_VERSION}"
}
EOF
}

main() {
  build_api_sidecar
  build_frontend_bundle
  download_node_runtime
  write_build_metadata
  log "Desktop build artifacts are ready for Tauri packaging"
}

main "$@"
