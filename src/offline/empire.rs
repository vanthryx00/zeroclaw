use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize, Default, PartialEq, Eq)]
pub enum GoalStatus {
    #[default]
    Pending,
    Active,
    Done,
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
}

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

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Empire {
    pub mission: String,
    pub goals: Vec<EmpireGoal>,
    pub session_count: u32,
    pub last_session: Option<String>,
}

impl Empire {
    pub fn load(_workspace: &Path) -> Self {
        Self::default()
    }

    pub fn save(&self, _workspace: &Path) -> Result<()> {
        Ok(())
    }

    pub fn begin_session(&mut self) {
        self.session_count += 1;
        self.last_session = Some(chrono::Utc::now().to_rfc3339());
    }

    pub fn to_context(&self) -> String {
        format!("Mission: {}\n", self.mission)
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

    pub fn is_complete(&self) -> bool {
        !self.goals.is_empty() && self.goals.iter().all(|g| g.status == GoalStatus::Done)
    }
}
