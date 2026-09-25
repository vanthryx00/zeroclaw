/// Adapter that wraps ZeroClaw's native Agent in the Orchestrator trait.
/// Allows native Agent to be registered as a backend in HybridOrchestrator.

use crate::agent::Agent;
use super::orchestrator::{
    ActionOutcome, Orchestrator, OrchestratorAction, OrchestratorInput, OrchestratorTrace,
};
use anyhow::Result;
use std::sync::Arc;
use tokio::sync::Mutex;

pub struct NativeAgentAdapter {
    agent: Arc<Mutex<Agent>>,
}

impl NativeAgentAdapter {
    pub fn new(agent: Agent) -> Self {
        Self {
            agent: Arc::new(Mutex::new(agent)),
        }
    }

    pub fn with_arc(agent: Arc<Mutex<Agent>>) -> Self {
        Self { agent }
    }
}

impl std::fmt::Debug for NativeAgentAdapter {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("NativeAgentAdapter").finish()
    }
}

#[async_trait::async_trait]
impl Orchestrator for NativeAgentAdapter {
    fn name(&self) -> &str {
        "native-adapter"
    }

    async fn execute(&self, input: OrchestratorInput) -> Result<OrchestratorTrace> {
        let mut agent = self.agent.lock().await;

        let start = std::time::Instant::now();

        // Execute turn with the native agent
        let response = agent.turn(&input.user_prompt).await?;

        let duration_ms = start.elapsed().as_millis() as u64;

        // Build trace
        let action = OrchestratorAction::Conclude {
            response: response.clone(),
        };
        let outcome = ActionOutcome {
            action,
            success: true,
            output: response.clone(),
            cost_usd: None,
            duration_ms,
        };

        let trace = OrchestratorTrace {
            orchestrator_name: self.name().to_string(),
            input,
            actions: vec![outcome],
            final_response: response,
            total_cost_usd: 0.0,
            total_duration_ms: duration_ms,
            iterations: 1,
        };

        Ok(trace)
    }
}
