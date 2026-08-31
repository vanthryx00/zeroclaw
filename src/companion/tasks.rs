use anyhow::Result;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::path::Path;

/// A single autonomous task the companion executes on a recurring schedule.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompanionTask {
    /// Human-readable name shown in notifications and logs.
    pub name: String,
    /// Short description of what this task does.
    pub description: String,
    /// The prompt sent to the agent when this task fires.
    pub prompt: String,
    /// How often to run, in seconds. 0 = run once at companion start.
    #[serde(default = "default_interval")]
    pub interval_secs: u64,
    /// RFC 3339 timestamp of last execution (None = never run).
    #[serde(default)]
    pub last_run: Option<String>,
    /// Whether this task participates in the schedule.
    #[serde(default = "default_enabled")]
    pub enabled: bool,
}

fn default_interval() -> u64 {
    3600
}

fn default_enabled() -> bool {
    true
}

impl CompanionTask {
    /// Returns true if this task is due to run now.
    pub fn is_due(&self) -> bool {
        if !self.enabled {
            return false;
        }
        if self.interval_secs == 0 {
            return self.last_run.is_none();
        }
        match &self.last_run {
            None => true,
            Some(ts) => {
                let Ok(last) = ts.parse::<DateTime<Utc>>() else {
                    return true;
                };
                let elapsed = Utc::now().signed_duration_since(last).num_seconds();
                elapsed >= self.interval_secs as i64
            }
        }
    }

    /// Mark as just executed.
    pub fn mark_run(&mut self) {
        self.last_run = Some(Utc::now().to_rfc3339());
    }

    /// Seconds until next scheduled run (0 if due now).
    pub fn secs_until_due(&self) -> u64 {
        if self.is_due() {
            return 0;
        }
        let Some(ts) = &self.last_run else { return 0 };
        let Ok(last) = ts.parse::<DateTime<Utc>>() else { return 0 };
        let elapsed = Utc::now().signed_duration_since(last).num_seconds().max(0) as u64;
        self.interval_secs.saturating_sub(elapsed)
    }
}

/// Companion task list persisted to `<workspace>/companion_tasks.toml`.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CompanionTaskList {
    pub tasks: Vec<CompanionTask>,
}

impl CompanionTaskList {
    pub fn load(workspace: &Path) -> Self {
        let path = workspace.join("companion_tasks.toml");
        std::fs::read_to_string(&path)
            .ok()
            .and_then(|data| toml::from_str(&data).ok())
            .unwrap_or_else(Self::defaults)
    }

    pub fn save(&self, workspace: &Path) -> Result<()> {
        let path = workspace.join("companion_tasks.toml");
        std::fs::write(path, toml::to_string_pretty(self)?)?;
        Ok(())
    }

    /// Collect indices of all tasks that are due right now.
    pub fn due_indices(&self) -> Vec<usize> {
        self.tasks
            .iter()
            .enumerate()
            .filter(|(_, t)| t.is_due())
            .map(|(i, _)| i)
            .collect()
    }

    /// Minimum seconds until the next task is due (for sleep scheduling).
    pub fn secs_until_next(&self) -> u64 {
        self.tasks
            .iter()
            .filter(|t| t.enabled)
            .map(|t| t.secs_until_due())
            .min()
            .unwrap_or(60)
            .max(5)
    }

    /// Default starter task list written on first run.
    fn defaults() -> Self {
        Self {
            tasks: vec![
                CompanionTask {
                    name: "Morning Briefing".to_string(),
                    description: "Daily summary of Empire goals and outstanding work".to_string(),
                    prompt: concat!(
                        "Generate a concise morning briefing: summarize active Empire goals, ",
                        "list the top 3 things to accomplish today, and flag any blocked items. ",
                        "Keep it under 200 words."
                    )
                    .to_string(),
                    interval_secs: 86400, // 24 h
                    last_run: None,
                    enabled: true,
                },
                CompanionTask {
                    name: "Code Health Check".to_string(),
                    description: "Run lint and tests, report failures".to_string(),
                    prompt: concat!(
                        "Run `cargo check` in the current workspace and report any errors or ",
                        "warnings. If everything is clean, say so briefly."
                    )
                    .to_string(),
                    interval_secs: 3600, // 1 h
                    last_run: None,
                    enabled: true,
                },
                CompanionTask {
                    name: "Progress Note".to_string(),
                    description: "Remind about unfinished Empire goals every 6 hours".to_string(),
                    prompt: concat!(
                        "Review the Empire goals. Identify any goal that has been Active for ",
                        "more than one session without progress. Suggest one concrete next action ",
                        "for the most overdue goal."
                    )
                    .to_string(),
                    interval_secs: 21600, // 6 h
                    last_run: None,
                    enabled: true,
                },
            ],
        }
    }
}
