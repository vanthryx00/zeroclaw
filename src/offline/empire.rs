use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::Path;

/// Lifecycle state of a single Empire goal.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "lowercase")]
pub enum GoalStatus {
    /// Not yet started.
    #[default]
    Pending,
    /// Currently being worked on.
    Active,
    /// Completed successfully.
    Done,
    /// Blocked; needs human input or a dependency.
    Blocked,
}

impl GoalStatus {
    pub fn label(&self) -> &str {
        match self {
            Self::Pending => "PENDING",
            Self::Active => "ACTIVE",
            Self::Done => "DONE",
            Self::Blocked => "BLOCKED",
        }
    }

    pub fn from_str_loose(s: &str) -> Option<Self> {
        match s.to_ascii_lowercase().as_str() {
            "pending" => Some(Self::Pending),
            "active" => Some(Self::Active),
            "done" | "complete" | "completed" => Some(Self::Done),
            "blocked" => Some(Self::Blocked),
            _ => None,
        }
    }
}

/// A single tracked goal inside the Empire.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EmpireGoal {
    pub id: String,
    pub title: String,
    pub description: String,
    pub status: GoalStatus,
    pub created_at: String,
    pub updated_at: String,
    pub notes: Vec<String>,
}

/// Persistent Empire state — mission + goal list + session bookkeeping.
///
/// Loaded from `<workspace>/empire.toml`. All mutating operations should be
/// followed by `save()` so progress survives process exit.
#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Empire {
    /// One-line mission statement that drives all goals.
    pub mission: String,
    pub goals: Vec<EmpireGoal>,
    pub session_count: u32,
    pub last_session: Option<String>,
}

impl Empire {
    /// Load from `<workspace>/empire.toml`, returning an empty Empire on missing/invalid file.
    pub fn load(workspace: &Path) -> Self {
        let path = workspace.join("empire.toml");
        std::fs::read_to_string(&path)
            .ok()
            .and_then(|data| toml::from_str(&data).ok())
            .unwrap_or_default()
    }

    /// Persist to `<workspace>/empire.toml`.
    pub fn save(&self, workspace: &Path) -> Result<()> {
        let path = workspace.join("empire.toml");
        std::fs::write(path, toml::to_string_pretty(self)?)?;
        Ok(())
    }

    /// Increment session counter and timestamp.
    pub fn begin_session(&mut self) {
        self.session_count += 1;
        self.last_session = Some(chrono::Utc::now().to_rfc3339());
    }

    /// One-line progress summary for terminal display.
    pub fn status_summary(&self) -> String {
        let total = self.goals.len();
        let done = self.goals.iter().filter(|g| g.status == GoalStatus::Done).count();
        let active = self.goals.iter().filter(|g| g.status == GoalStatus::Active).count();
        let blocked = self.goals.iter().filter(|g| g.status == GoalStatus::Blocked).count();
        let pending = total - done - active - blocked;

        let mut out = format!("Empire: {}\n", self.mission);
        out.push_str(&format!(
            "Goals: {total} total | {done} done | {active} active | {pending} pending | {blocked} blocked\n"
        ));
        out.push_str(&format!("Sessions: {}\n", self.session_count));
        if let Some(last) = &self.last_session {
            out.push_str(&format!("Last session: {last}\n"));
        }

        if !self.goals.is_empty() {
            out.push('\n');
            for g in &self.goals {
                out.push_str(&format!(
                    "  [{}] {} — {}: {}\n",
                    g.status.label(),
                    g.id,
                    g.title,
                    g.description
                ));
                for note in &g.notes {
                    out.push_str(&format!("    note: {note}\n"));
                }
            }
        }
        out
    }

    /// Context block injected at the start of each agent turn.
    pub fn to_context(&self) -> String {
        let mut ctx = format!("## Empire Mission: {}\n\n", self.mission);
        if self.goals.is_empty() {
            ctx.push_str("No goals defined yet. Ask the user what they want to accomplish.\n\n");
            return ctx;
        }
        ctx.push_str("### Current Goals\n");
        for g in &self.goals {
            ctx.push_str(&format!(
                "- [{}] {} ({}): {}\n",
                g.status.label(),
                g.id,
                g.title,
                g.description
            ));
        }
        ctx.push('\n');
        ctx
    }

    /// Add a new goal and return its generated ID.
    pub fn add_goal(&mut self, title: &str, description: &str) -> String {
        let id = format!("G{:03}", self.goals.len() + 1);
        let now = chrono::Utc::now().to_rfc3339();
        self.goals.push(EmpireGoal {
            id: id.clone(),
            title: title.to_string(),
            description: description.to_string(),
            status: GoalStatus::Pending,
            created_at: now.clone(),
            updated_at: now,
            notes: Vec::new(),
        });
        id
    }

    /// Set a goal's status by ID. Returns false if the ID is unknown.
    pub fn set_status(&mut self, id: &str, status: GoalStatus) -> bool {
        if let Some(g) = self.goals.iter_mut().find(|g| g.id == id) {
            g.status = status;
            g.updated_at = chrono::Utc::now().to_rfc3339();
            true
        } else {
            false
        }
    }

    /// Append a text note to a goal. Returns false if the ID is unknown.
    pub fn add_note(&mut self, id: &str, note: &str) -> bool {
        if let Some(g) = self.goals.iter_mut().find(|g| g.id == id) {
            g.notes.push(note.to_string());
            g.updated_at = chrono::Utc::now().to_rfc3339();
            true
        } else {
            false
        }
    }

    /// Returns true if every goal is Done.
    pub fn is_complete(&self) -> bool {
        !self.goals.is_empty() && self.goals.iter().all(|g| g.status == GoalStatus::Done)
    }
}
