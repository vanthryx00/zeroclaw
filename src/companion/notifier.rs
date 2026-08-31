/// Cross-platform desktop/terminal notifications — no external crate.
///
/// Attempts OS-level notification via `notify-send` (Linux/freedesktop) or
/// `osascript` (macOS). Falls back to a terminal print on error or unknown OS.
pub struct Notifier {
    app_name: String,
}

impl Notifier {
    pub fn new(app_name: impl Into<String>) -> Self {
        Self {
            app_name: app_name.into(),
        }
    }

    /// Send a notification. Always succeeds — falls back to terminal on OS error.
    pub fn send(&self, title: &str, body: &str) {
        let sent = self.try_os_notify(title, body);
        if !sent {
            println!("[{}] {}: {}", self.app_name, title, body);
        }
    }

    /// Attempt OS-level notification. Returns true on success.
    fn try_os_notify(&self, title: &str, body: &str) -> bool {
        #[cfg(target_os = "linux")]
        {
            std::process::Command::new("notify-send")
                .arg("--app-name")
                .arg(&self.app_name)
                .arg(title)
                .arg(body)
                .status()
                .map(|s| s.success())
                .unwrap_or(false)
        }

        #[cfg(target_os = "macos")]
        {
            let script = format!(
                "display notification {:?} with title {:?} subtitle {:?}",
                body, self.app_name, title
            );
            std::process::Command::new("osascript")
                .arg("-e")
                .arg(&script)
                .status()
                .map(|s| s.success())
                .unwrap_or(false)
        }

        #[cfg(target_os = "windows")]
        {
            // PowerShell toast notification via BurntToast or basic MessageBox fallback.
            let script = format!(
                "[void][System.Reflection.Assembly]::LoadWithPartialName('System.Windows.Forms'); \
                 [System.Windows.Forms.MessageBox]::Show({:?}, {:?})",
                body, title
            );
            std::process::Command::new("powershell")
                .args(["-NoProfile", "-Command", &script])
                .status()
                .map(|s| s.success())
                .unwrap_or(false)
        }

        #[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
        {
            false
        }
    }
}
