use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::path::Path;

use crate::agent::prompt::{PromptContext, PromptSection};

/// Persistent agent persona: name, goals, constraints, and tone.
///
/// Loaded from `<workspace>/mindset.toml` at session start. When no file
/// exists, the default Empire persona is used and written to disk.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Mindset {
    /// Display name for this agent identity.
    pub name: String,
    /// Freeform persona description injected into every system prompt.
    pub persona: String,
    /// High-level strategic goals that guide agent behavior.
    pub goals: Vec<String>,
    /// Hard constraints the agent must never violate.
    pub constraints: Vec<String>,
    /// Communication style descriptor (e.g. "strategic, direct, focused").
    pub tone: String,
}

impl Default for Mindset {
    fn default() -> Self {
        Self {
            name: "Empire Agent".to_string(),
            persona: concat!(
                "You are an autonomous agent building the Empire — a complete, ",
                "working system that delivers value across multiple domains. ",
                "You think strategically, execute with precision, and track ",
                "progress toward defined goals. You are persistent, methodical, ",
                "and resourceful. You read and write files, hold long conversations, ",
                "and always move toward completing the mission."
            )
            .to_string(),
            goals: vec![
                "Understand the full scope of the Empire project".to_string(),
                "Break down goals into concrete, actionable tasks".to_string(),
                "Execute tasks efficiently using all available tools".to_string(),
                "Save progress and maintain continuity across sessions".to_string(),
                "Finish Empire".to_string(),
            ],
            constraints: vec![
                "Never expose secrets or API keys".to_string(),
                "Fail fast and explicitly on unsafe or ambiguous operations".to_string(),
                "Stay focused on Empire goals; reject scope creep".to_string(),
            ],
            tone: "strategic, direct, focused".to_string(),
        }
    }
}

impl Mindset {
    /// Load from `<workspace>/mindset.toml`, falling back to default.
    pub fn load(workspace: &Path) -> Self {
        let path = workspace.join("mindset.toml");
        std::fs::read_to_string(&path)
            .ok()
            .and_then(|data| toml::from_str(&data).ok())
            .unwrap_or_default()
    }

    /// Persist to `<workspace>/mindset.toml`.
    pub fn save(&self, workspace: &Path) -> Result<()> {
        let path = workspace.join("mindset.toml");
        std::fs::write(path, toml::to_string_pretty(self)?)?;
        Ok(())
    }

    /// Render to a markdown section suitable for system prompt injection.
    pub fn to_prompt_section(&self) -> String {
        let mut out = format!("## Agent Identity: {}\n\n{}\n\n", self.name, self.persona);

        if !self.goals.is_empty() {
            out.push_str("## Core Goals\n");
            for g in &self.goals {
                out.push_str(&format!("- {g}\n"));
            }
            out.push('\n');
        }

        if !self.constraints.is_empty() {
            out.push_str("## Constraints\n");
            for c in &self.constraints {
                out.push_str(&format!("- {c}\n"));
            }
            out.push('\n');
        }

        out.push_str(&format!("Tone: {}\n", self.tone));
        out
    }
}

/// Injects the mindset as the first section in the system prompt.
pub struct MindsetSection {
    pub mindset: Mindset,
}

impl PromptSection for MindsetSection {
    fn name(&self) -> &str {
        "mindset"
    }

    fn build(&self, _ctx: &PromptContext<'_>) -> anyhow::Result<String> {
        Ok(self.mindset.to_prompt_section())
    }
}
