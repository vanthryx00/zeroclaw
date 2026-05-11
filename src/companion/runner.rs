use anyhow::Result;
use std::path::PathBuf;
use tokio::time::{sleep, Duration};
use tracing::{info, warn};

use crate::config::Config;
use crate::offline::empire::Empire;
use crate::offline::mindset::Mindset;
use crate::offline::runner::{build_empire_agent, build_empire_config};

use super::notifier::Notifier;
use super::tasks::CompanionTaskList;

/// Entry point for `zeroclaw companion`.
///
/// Runs an autonomous background loop:
/// 1. Boot: load mindset, empire, and task list from disk.
/// 2. Loop: execute all due tasks by sending their prompts to the agent.
/// 3. Sleep until the next task is due, then repeat.
/// 4. On SIGINT/SIGTERM: flush state and exit cleanly.
pub async fn run(
    base_config: Config,
    provider_override: Option<String>,
    model_override: Option<String>,
    interval_override: Option<u64>,
    once: bool,
) -> Result<()> {
    let workspace = base_config.workspace_dir.clone();
    let notifier = Notifier::new("ZeroClaw");

    // ── Load persistent state ────────────────────────────────────────
    let mindset = Mindset::load(&workspace);
    mindset.save(&workspace).unwrap_or_default();

    let mut empire = Empire::load(&workspace);
    if empire.mission.is_empty() {
        empire.mission = "Build and complete the Empire".to_string();
    }
    empire.begin_session();
    empire.save(&workspace)?;

    let mut tasks = CompanionTaskList::load(&workspace);
    tasks.save(&workspace)?;

    // ── Build agent config ───────────────────────────────────────────
    let config = build_empire_config(base_config, provider_override, model_override);

    info!("ZeroClaw Companion started — {} tasks loaded", tasks.tasks.len());
    notifier.send(
        "ZeroClaw Companion",
        &format!("Started. {} tasks loaded. Mission: {}", tasks.tasks.len(), empire.mission),
    );

    // ── Main loop ────────────────────────────────────────────────────
    loop {
        let due = tasks.due_indices();

        if !due.is_empty() {
            info!("{} task(s) due", due.len());

            // Build a fresh agent for this execution wave.
            let agent_result = build_empire_agent(&config, &mindset);
            match agent_result {
                Err(e) => {
                    warn!("Failed to build agent: {e}");
                    notifier.send("ZeroClaw Companion", &format!("Agent build failed: {e}"));
                }
                Ok(mut agent) => {
                    for idx in &due {
                        let task = &tasks.tasks[*idx];
                        let task_name = task.name.clone();
                        let prompt = format!(
                            "{}\n\nTask: {}\n\n{}",
                            empire.to_context(),
                            task.name,
                            task.prompt
                        );

                        info!("Running task: {task_name}");
                        notifier.send("ZeroClaw Companion", &format!("Running: {task_name}"));

                        match agent.turn(&prompt).await {
                            Ok(response) => {
                                info!("Task '{task_name}' complete");
                                log_task_result(&workspace, &task_name, &response);
                                notifier.send(&task_name, &truncate_for_notify(&response));
                            }
                            Err(e) => {
                                warn!("Task '{task_name}' failed: {e}");
                                notifier.send(&task_name, &format!("Error: {e}"));
                            }
                        }
                    }

                    // Mark tasks as run after the wave.
                    for idx in due {
                        tasks.tasks[idx].mark_run();
                    }
                    tasks.save(&workspace)?;
                }
            }
        }

        if once {
            info!("--once mode: exiting after first run");
            break;
        }

        let sleep_secs = interval_override.unwrap_or_else(|| tasks.secs_until_next());
        info!("Sleeping {}s until next task", sleep_secs);

        // Wait for sleep OR ctrl-c — whichever comes first.
        tokio::select! {
            _ = sleep(Duration::from_secs(sleep_secs)) => {}
            _ = tokio::signal::ctrl_c() => {
                info!("Companion interrupted — shutting down");
                notifier.send("ZeroClaw Companion", "Shutting down.");
                break;
            }
        }
    }

    Ok(())
}


/// Append task output to `<workspace>/companion.log`.
fn log_task_result(workspace: &PathBuf, task_name: &str, response: &str) {
    let path = workspace.join("companion.log");
    let entry = format!(
        "[{}] Task: {}\n{}\n---\n",
        chrono::Utc::now().to_rfc3339(),
        task_name,
        response
    );
    if let Err(e) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .and_then(|mut f| {
            use std::io::Write;
            f.write_all(entry.as_bytes())
        })
    {
        warn!("Failed to write companion.log: {e}");
    }
}

/// Trim a response to fit in an OS notification (~200 chars).
fn truncate_for_notify(s: &str) -> String {
    let s = s.trim();
    if s.len() <= 200 {
        s.to_string()
    } else {
        format!("{}…", &s[..197])
    }
}

