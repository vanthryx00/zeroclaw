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

    pub fn is_complete(&self) -> bool {
        !self.goals.is_empty() && self.goals.iter().all(|g| g.status == GoalStatus::Done)
    }
}
