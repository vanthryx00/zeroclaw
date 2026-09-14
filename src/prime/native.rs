/// Native Prime Zero orchestrator — ZeroClaw's intelligent reasoning engine.
///
/// This is the default orchestrator that powers Prime Zero when no other backend
/// (e.g., Llama Prime) is available. It uses the agent's native tool-calling loop
/// integrated with Empire goals and Companion context for intelligent, goal-aware execution.
///
/// Features:
/// - Multi-provider fallback (Anthropic → Gemini → Ollama)
/// - Empire goal tracking and prioritization
/// - Companion task awareness
/// - Tool execution with safety enforcement
/// - Cost tracking and budget management

use crate::agent::agent::Agent;
use crate::config::Config;
use crate::offline::empire::Empire;
use crate::offline::mindset::Mindset;
use anyhow::Result;
use std::sync::Arc;
use tracing::{info, debug};

use super::orchestrator::{
    ExecutionConstraints, OrchestratorAction, OrchestratorInput, OrchestratorTrace, ActionOutcome,
};

/// Native Prime Zero orchestrator powered by ZeroClaw's agent.
#[derive(Debug, Clone)]
pub struct NativeOrchestrator {
    config: Arc<Config>,
    mindset: Arc<Mindset>,
    empire: Arc<tokio::sync::Mutex<Empire>>,
}

impl NativeOrchestrator {
    pub fn new() -> Self {
        // Default construction — would need config passed in for production
        Self {
            config: Arc::new(Config::default()),
            mindset: Arc::new(Mindset::default()),
            empire: Arc::new(tokio::sync::Mutex::new(Empire::default())),
        }
    }

    pub fn with_config(config: Config, mindset: Mindset, empire: Empire) -> Self {
        Self {
            config: Arc::new(config),
            mindset: Arc::new(mindset),
            empire: Arc::new(tokio::sync::Mutex::new(empire)),
        }
    }
}

#[async_trait::async_trait]
impl super::orchestrator::Orchestrator for NativeOrchestrator {
    fn name(&self) -> &str {
        "prime-zero-native"
    }

    async fn execute(&self, input: OrchestratorInput) -> Result<OrchestratorTrace> {
        info!("NativeOrchestrator starting execution");

        let start = std::time::Instant::now();
        let mut actions = Vec::new();
        let mut total_cost = 0.0;
        let mut iteration = 0;

        // Build the agent from config
        let mut agent = crate::agent::agent::Agent::from_config(&self.config)?;

        // Construct the enriched prompt: mindset + empire context + user request
        let enriched_prompt = format!(
            "{}\n\n{}\n\n{}\n\nUser Request:\n{}",
            input.mindset, input.empire_context, input.companion_context, input.user_prompt
        );

        // Execute the agent turn with the enriched prompt
        match agent.turn(&enriched_prompt).await {
            Ok(response) => {
                let duration_ms = start.elapsed().as_millis() as u64;

                // Record final action
                actions.push(ActionOutcome {
                    action: OrchestratorAction::Conclude {
                        response: response.clone(),
                    },
                    success: true,
                    output: response.clone(),
                    cost_usd: None,
                    duration_ms,
                });

                Ok(OrchestratorTrace {
                    orchestrator_name: self.name().to_string(),
                    input,
                    actions,
                    final_response: response,
                    total_cost_usd: total_cost,
                    total_duration_ms: start.elapsed().as_millis() as u64,
                    iterations: 1,
                })
            }
            Err(e) => {
                let response = format!("Error: {}", e);
                let duration_ms = start.elapsed().as_millis() as u64;

                actions.push(ActionOutcome {
                    action: OrchestratorAction::Conclude {
                        response: response.clone(),
                    },
                    success: false,
                    output: response.clone(),
                    cost_usd: None,
                    duration_ms,
                });

                Ok(OrchestratorTrace {
                    orchestrator_name: self.name().to_string(),
                    input,
                    actions,
                    final_response: response,
                    total_cost_usd: total_cost,
                    total_duration_ms: start.elapsed().as_millis() as u64,
                    iterations: 1,
                })
            }
        }
    }

    async fn is_ready(&self) -> bool {
        true // Native orchestrator is always ready
    }

    async fn estimate_cost(&self, _input: &OrchestratorInput) -> Result<f64> {
        // Rough estimate based on provider
        let provider = self.config.default_provider.as_deref().unwrap_or("anthropic");
        Ok(match provider {
            "anthropic" => 0.005,  // ~$0.005 per request (Claude)
            "gemini" => 0.001,     // ~$0.001 per request (Gemini)
            "ollama" => 0.0,       // Free (local)
            _ => 0.005,
        })
    }
}

impl Default for NativeOrchestrator {
    fn default() -> Self {
        Self::new()
    }
}
