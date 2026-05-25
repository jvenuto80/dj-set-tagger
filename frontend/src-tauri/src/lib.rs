use std::sync::Mutex;
use tauri::{Manager, RunEvent, State};
use tauri_plugin_shell::ShellExt;

/// Holds the Python backend child process so we can kill it on exit.
struct BackendProcess(Mutex<Option<tauri_plugin_shell::process::CommandChild>>);

/// Tauri command: check if the Python backend is reachable.
#[tauri::command]
async fn backend_health() -> Result<String, String> {
    let client = reqwest::Client::new();
    match client
        .get("http://127.0.0.1:5050/api/health")
        .timeout(std::time::Duration::from_secs(3))
        .send()
        .await
    {
        Ok(resp) => {
            let text = resp.text().await.unwrap_or_default();
            Ok(text)
        }
        Err(e) => Err(format!("Backend not reachable: {}", e)),
    }
}

/// Tauri command: get the backend base URL (for frontend API config).
#[tauri::command]
fn backend_url() -> String {
    "http://127.0.0.1:5050".to_string()
}

/// Try to cleanly shut the backend down. Strategy:
///   1. POST /api/ai/unload so Ollama frees the model from RAM/VRAM.
///   2. Send SIGTERM to the launcher process group (catches uvicorn + workers).
///   3. Wait briefly; if still alive, fall back to SIGKILL of the group.
/// This runs synchronously because Tauri's Exit event is fired on the main
/// thread and we don't want the app to terminate before cleanup finishes.
fn shutdown_backend(bp: &BackendProcess) {
    let child = match bp.0.lock().unwrap().take() {
        Some(c) => c,
        None => return,
    };

    log::info!("Shutting down backend (pid {})...", child.pid());

    // 1. Best-effort: tell Ollama to unload our model immediately.
    //    We use a short timeout because the model unload happens in-process
    //    on the python side and we don't want to block app exit.
    let _ = std::thread::spawn(|| {
        if let Ok(client) = reqwest::blocking::Client::builder()
            .timeout(std::time::Duration::from_secs(2))
            .build()
        {
            let _ = client
                .post("http://127.0.0.1:5050/api/ai/unload")
                .send();
        }
    })
    .join();

    let pid = child.pid() as i32;

    // 2. SIGTERM the whole process group so uvicorn (a child of run.py) dies too.
    #[cfg(unix)]
    {
        // Negative PID targets the entire process group.
        unsafe {
            libc::kill(-pid, libc::SIGTERM);
            // Also signal the leader directly, in case it isn't a group leader.
            libc::kill(pid, libc::SIGTERM);
        }

        // Give python a moment to clean up uvicorn gracefully.
        for _ in 0..20 {
            std::thread::sleep(std::time::Duration::from_millis(100));
            // ESRCH == "no such process" => already dead.
            if unsafe { libc::kill(pid, 0) } != 0 {
                log::info!("Backend exited cleanly after SIGTERM");
                return;
            }
        }

        // 3. Still alive — force kill the group.
        log::warn!("Backend did not exit after 2s, sending SIGKILL");
        unsafe {
            libc::kill(-pid, libc::SIGKILL);
            libc::kill(pid, libc::SIGKILL);
        }
    }

    #[cfg(not(unix))]
    {
        let _ = child.kill();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendProcess(Mutex::new(None)))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_os::init())
        .plugin(
            tauri_plugin_log::Builder::default()
                .level(log::LevelFilter::Info)
                .build(),
        )
        .invoke_handler(tauri::generate_handler![backend_health, backend_url])
        .setup(|app| {
            let handle = app.handle().clone();

            // Spawn the Python backend as a sidecar process
            let shell = handle.shell();

            // In development, run from the project directory
            let cmd = if cfg!(debug_assertions) {
                // Dev mode: run uvicorn from the project root (parent of frontend/)
                let project_root = std::env::current_dir()
                    .unwrap_or_default()
                    .parent()
                    .unwrap_or(&std::path::PathBuf::from(".."))
                    .to_path_buf();

                log::info!("Dev mode: starting backend from {:?}", project_root);

                shell
                    .command("python3")
                    .args([
                        "-m", "uvicorn",
                        "backend.main:app",
                        "--host", "0.0.0.0",
                        "--port", "5050",
                        "--reload",
                    ])
                    .current_dir(project_root)
            } else {
                // Production: run the bundled run.py from resources
                let resource_dir = handle
                    .path()
                    .resource_dir()
                    .unwrap_or_else(|_| std::path::PathBuf::from("."));
                let backend_dir = resource_dir.join("resources");
                let run_script = backend_dir.join("run.py");

                log::info!("Production: starting backend via {:?}", run_script);

                shell
                    .command("python3")
                    .args([run_script.to_str().unwrap_or("run.py")])
                    .env("PORT", "5050")
                    .env("SETLIST_NATIVE", "1")
                    .current_dir(backend_dir)
            };

            match cmd.spawn() {
                Ok((mut rx, child)) => {
                    // Store child process for cleanup on exit
                    let bp: State<BackendProcess> = app.state();
                    *bp.0.lock().unwrap() = Some(child);

                    // Log backend stdout/stderr in background
                    tauri::async_runtime::spawn(async move {
                        use tauri_plugin_shell::process::CommandEvent;
                        while let Some(event) = rx.recv().await {
                            match event {
                                CommandEvent::Stdout(line) => {
                                    log::info!("[backend] {}", String::from_utf8_lossy(&line));
                                }
                                CommandEvent::Stderr(line) => {
                                    log::warn!("[backend] {}", String::from_utf8_lossy(&line));
                                }
                                CommandEvent::Terminated(payload) => {
                                    log::error!(
                                        "Backend terminated (code: {:?}, signal: {:?})",
                                        payload.code,
                                        payload.signal
                                    );
                                    break;
                                }
                                _ => {}
                            }
                        }
                    });
                }
                Err(e) => {
                    log::error!("Failed to start Python backend: {}", e);
                    // Don't panic — the app can still show UI with an error state
                }
            }

            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                // Run cleanup as soon as the user closes the window so the
                // backend is gone by the time the process actually exits.
                let bp: State<BackendProcess> = window.state();
                shutdown_backend(&bp);
            }
        })
        .build(tauri::generate_context!())
        .expect("error while running SetList")
        .run(|app_handle, event| {
            // Final safety net: also fire on Exit in case CloseRequested didn't.
            if let RunEvent::Exit = event {
                let bp: State<BackendProcess> = app_handle.state();
                shutdown_backend(&bp);
            }
        });
}

