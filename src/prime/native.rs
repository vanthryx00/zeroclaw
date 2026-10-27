//! Native Prime Zero orchestrator — ZeroClaw's agent loop behind the `Orchestrator` trait.
//!
//! Holds a single long-lived [`Agent`] (built once by the runner with the mindset
//! injected into its system prompt, SQLite memory, and the provider fallback chain),
//! so conversation history and tool state persist across turns. Each turn is
//! enriched with the current Empire goals and Companion task context.

use crate::agent::agent::Agent;
use anyhow::Result;
use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::info;

use super::orchestrator::{
    ActionOutcome, Orchestrator, OrchestratorAction, OrchestratorInput, OrchestratorTrace,
};

pub struct NativeOrchestrator {
    agent: Arc<Mutex<Agent>>,
    provider: String,
}

impl NativeOrchestrator {
    pub fn new(agent: Agent, provider: impl Into<String>) -> Self {
        Self {
            agent: Arc::new(Mutex::new(agent)),
            provider: provider.into(),
        }
    }
}

impl std::fmt::Debug for NativeOrchestrator {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("NativeOrchestrator")
            .field("provider", &self.provider)
            .finish_non_exhaustive()
    }
}

/// Build the per-turn prompt: Empire goals + Companion tasks + user request.
///
/// The mindset is not repeated here — it already anchors the agent's system prompt.
pub fn enrich_prompt(input: &OrchestratorInput) -> String {
    format!(
        "{}\n\n{}\n\nUser Request:\n{}",
        input.empire_context, input.companion_context, input.user_prompt
    )
}

#[async_trait::async_trait]
impl Orchestrator for NativeOrchestrator {
    fn name(&self) -> &str {
        "prime-zero-native"
    }

    async fn execute(&self, input: OrchestratorInput) -> Result<OrchestratorTrace> {
        info!("NativeOrchestrator starting execution");
        let start = std::time::Instant::now();

        let response = self.agent.lock().await.turn(&enrich_prompt(&input)).await?;
        let duration_ms = u64::try_from(start.elapsed().as_millis()).unwrap_or(u64::MAX);

        Ok(OrchestratorTrace {
            orchestrator_name: self.name().to_string(),
            input,
            actions: vec![ActionOutcome {
                action: OrchestratorAction::Conclude {
                    response: response.clone(),
                },
                success: true,
                output: response.clone(),
                cost_usd: None,
                duration_ms,
            }],
            final_response: response,
            total_cost_usd: 0.0,
            total_duration_ms: duration_ms,
            iterations: 1,
        })
    }

    async fn estimate_cost(&self, _input: &OrchestratorInput) -> Result<f64> {
        // Rough per-request estimate by primary provider.
        Ok(match self.provider.as_str() {
            "gemini" => 0.001,
            "ollama" => 0.0,
            _ => 0.005,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::prime::orchestrator::ExecutionConstraints;

    #[test]
    fn enrich_prompt_includes_goals_tasks_and_request() {
        let input = OrchestratorInput {
            user_prompt: "ship v1".into(),
            empire_context: "## Empire".into(),
            companion_context: "## Tasks".into(),
            mindset: "MINDSET".into(),
            history: vec![],
            available_tools: vec![],
            constraints: ExecutionConstraints::default(),
        };
        let p = enrich_prompt(&input);
        assert!(p.contains("## Empire"));
        assert!(p.contains("## Tasks"));
        assert!(p.ends_with("ship v1"));
        assert!(!p.contains("MINDSET"));
    }
}
