use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CompanionTask {
    pub name: String,
    pub description: String,
    pub prompt: String,
    pub interval_secs: u64,
    pub enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct CompanionTaskList {
    pub tasks: Vec<CompanionTask>,
}

impl CompanionTaskList {
    pub fn load(_workspace: &std::path::Path) -> Self {
        Self::default()
    }

    pub fn save(&self, _workspace: &std::path::Path) -> anyhow::Result<()> {
        Ok(())
    }
}
