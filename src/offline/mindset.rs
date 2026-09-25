use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Mindset {
    pub name: String,
    pub persona: String,
    pub goals: Vec<String>,
    pub constraints: Vec<String>,
    pub tone: String,
}

impl Mindset {
    pub fn load(_workspace: &Path) -> Self {
        Self {
            name: "Agent".to_string(),
            persona: "Autonomous agent".to_string(),
            goals: vec![],
            constraints: vec![],
            tone: "professional".to_string(),
        }
    }

    pub fn save(&self, _workspace: &Path) -> Result<()> {
        Ok(())
    }

    pub fn to_prompt_section(&self) -> String {
        format!("# Mindset: {}\n{}\n", self.name, self.persona)
    }
}

pub struct MindsetSection {
    pub mindset: Mindset,
}

impl crate::agent::prompt::PromptSection for MindsetSection {
    fn name(&self) -> &str {
        "mindset"
    }

    fn build(&self, _ctx: &crate::agent::prompt::PromptContext<'_>) -> anyhow::Result<String> {
        Ok(self.mindset.to_prompt_section())
    }
}
