use std::fs;
use std::fs::OpenOptions;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager, RunEvent, State, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const API_HEALTH_URL: &str = "http://127.0.0.1:8765/health";
const UI_PORT: u16 = 3847;
const UI_HEALTH_URL: &str = "http://127.0.0.1:3847";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(90);

struct SidecarState {
    api_child: Mutex<Option<CommandChild>>,
    ui_child: Mutex<Option<Child>>,
}

impl SidecarState {
    fn new() -> Self {
        Self {
            api_child: Mutex::new(None),
            ui_child: Mutex::new(None),
        }
    }
}

fn resource_path(app: &AppHandle, relative: &str) -> Result<PathBuf, String> {
    app.path()
        .resource_dir()
        .map_err(|error| error.to_string())
        .map(|dir| dir.join(relative))
}

fn wait_for_url(url: &str, timeout: Duration) -> Result<(), String> {
    let started = Instant::now();
    while started.elapsed() < timeout {
        match ureq::get(url).call() {
            Ok(response) if response.status() >= 200 && response.status() < 400 => return Ok(()),
            _ => thread::sleep(Duration::from_millis(400)),
        }
    }
    Err(format!("Timed out waiting for {url}"))
}

fn spawn_api_sidecar(app: &AppHandle, state: &State<SidecarState>) -> Result<(), String> {
    let mut sidecar = app
        .shell()
        .sidecar("redcap-api")
        .map_err(|error| error.to_string())?;

    if let Ok(metadata_path) = resource_path(app, "build-metadata.json") {
        if let Ok(contents) = fs::read_to_string(metadata_path) {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(&contents) {
                if let Some(expiry_date) = value.get("app_expiry_date").and_then(|v| v.as_str()) {
                    sidecar = sidecar.env("APP_EXPIRY_DATE", expiry_date);
                }
            }
        }
    }

    let (mut rx, child) = sidecar
        .env("APP_MODE", "desktop")
        .env("REDCAP_SSL_VERIFY", "false")
        .spawn()
        .map_err(|error| error.to_string())?;

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            if matches!(event, CommandEvent::Terminated(_)) {
                break;
            }
        }
    });

    *state.api_child.lock().unwrap() = Some(child);
    Ok(())
}

fn spawn_ui_server(app: &AppHandle, state: &State<SidecarState>) -> Result<(), String> {
    let ui_dir = resource_path(app, "resources/ui")?;
    let node_binary = resource_path(app, "resources/node/node")?;
    let server_script = ui_dir.join("server.js");

    if !node_binary.is_file() {
        return Err(format!("Bundled Node.js binary not found at {}", node_binary.display()));
    }
    if !server_script.is_file() {
        return Err(format!("Next.js server not found at {}", server_script.display()));
    }

    // Keep UI sidecar logs so packaged failures are diagnosable.
    let (ui_stdout, ui_stderr) = match app.path().app_log_dir() {
        Ok(log_dir) => {
            let _ = fs::create_dir_all(&log_dir);
            let stdout = OpenOptions::new()
                .create(true)
                .append(true)
                .open(log_dir.join("ui-stdout.log"))
                .ok()
                .map(Stdio::from);
            let stderr = OpenOptions::new()
                .create(true)
                .append(true)
                .open(log_dir.join("ui-stderr.log"))
                .ok()
                .map(Stdio::from);
            (
                stdout.unwrap_or_else(Stdio::null),
                stderr.unwrap_or_else(Stdio::null),
            )
        }
        Err(_) => (Stdio::null(), Stdio::null()),
    };

    let child = Command::new(node_binary)
        .arg(server_script)
        .current_dir(&ui_dir)
        .env("PORT", UI_PORT.to_string())
        .env("HOSTNAME", "127.0.0.1")
        .env("NODE_ENV", "production")
        .env("BACKEND_ORIGIN", "http://127.0.0.1:8765")
        .env("NEXT_PUBLIC_APP_MODE", "desktop")
        .stdout(ui_stdout)
        .stderr(ui_stderr)
        .spawn()
        .map_err(|error| format!("Failed to start UI server: {error}"))?;

    *state.ui_child.lock().unwrap() = Some(child);
    Ok(())
}

fn open_main_window(app: &AppHandle) -> Result<(), String> {
    if app.get_webview_window("main").is_some() {
        return Ok(());
    }

    WebviewWindowBuilder::new(
        app,
        "main",
        WebviewUrl::External(
            format!("http://127.0.0.1:{UI_PORT}/jobs")
                .parse()
                .map_err(|error| format!("Invalid app URL: {error}"))?,
        ),
    )
    .title("REDCap Batch Locking")
    .inner_size(1440.0, 900.0)
    .min_inner_size(1100.0, 720.0)
    .build()
    .map_err(|error| error.to_string())?;

    Ok(())
}

fn startup_services(app: &AppHandle, state: &State<SidecarState>) -> Result<(), String> {
    spawn_api_sidecar(app, state)?;
    wait_for_url(API_HEALTH_URL, STARTUP_TIMEOUT)?;

    spawn_ui_server(app, state)?;
    wait_for_url(&format!("http://127.0.0.1:{UI_PORT}/jobs"), STARTUP_TIMEOUT)?;

    open_main_window(app)
}

fn stop_sidecars(state: &SidecarState) {
    if let Some(mut child) = state.ui_child.lock().unwrap().take() {
        let _ = child.kill();
    }

    if let Some(child) = state.api_child.lock().unwrap().take() {
        let _ = child.kill();
    }
}

fn main() {
    if let Err(error) = run_app() {
        eprintln!("REDCap Batch Locking exited with error: {error}");
        std::process::exit(1);
    }
}

fn run_app() -> Result<(), Box<dyn std::error::Error>> {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(SidecarState::new())
        .setup(|app| {
            let handle = app.handle().clone();
            let state = app.state::<SidecarState>();

            if cfg!(debug_assertions) {
                // Development: expect `./scripts/dev-desktop.sh` to provide services.
                open_main_window(&handle).map_err(|error| {
                    std::io::Error::new(std::io::ErrorKind::Other, error)
                })?;
                return Ok(());
            }

            startup_services(&handle, &state).map_err(|error| {
                eprintln!("Startup failed: {error}");
                if let Ok(log_dir) = handle.path().app_log_dir() {
                    let _ = fs::create_dir_all(&log_dir);
                    let _ = fs::write(log_dir.join("startup-error.txt"), &error);
                }
                std::io::Error::new(std::io::ErrorKind::Other, error)
            })?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .map_err(|error| {
            eprintln!("Failed to start REDCap Batch Locking: {error}");
            error
        })?
        .run(|app_handle, event| {
            if matches!(event, RunEvent::Exit) {
                if let Some(state) = app_handle.try_state::<SidecarState>() {
                    stop_sidecars(&state);
                }
            }
        });
    Ok(())
}
