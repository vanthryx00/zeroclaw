/// Autonomous desktop companion: scheduled tasks, code execution, notifications.
///
/// The companion runs in the background and executes tasks from
/// `<workspace>/companion_tasks.toml` on configurable intervals. Each task
/// sends a prompt to the agent (backed by the same multi-provider fallback
/// chain as the Empire agent). Results are logged to `companion.log` and
/// surfaced via OS desktop notifications or terminal output.
///
/// See [`runner::run`] for the main entry point.
pub mod notifier;
pub mod runner;
pub mod tasks;
