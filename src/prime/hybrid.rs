//! Prime Zero hybrid orchestrator — intelligently routes between multiple backends.
//!
//! The HybridOrchestrator is the secret sauce: it dispatches requests to the best
//! available orchestrator based on task type, cost, latency, and availability.
//!
//! Routing strategy:
//! 1. Classify the request (simple query, complex reasoning, task automation, etc.)
//! 2. Check which backends are ready (Llama Prime available? Ollama up? API key valid?)
//! 3. Route to the optimal orchestrator (minimize cost, maximize quality/speed)
//! 4. Fall back gracefully if the primary is unavailable
//! 5. Collect metrics on what worked best for learning
//!
//! This allows seamless integration of Llama Prime, other frameworks, and ZeroClaw's
//! native engine without requiring code rewrites.

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;
use tracing::{debug, info};

use super::orchestrator::{Orchestrator, OrchestratorInput, OrchestratorTrace};

/// Task classification — determines which orchestrator is best suited.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum TaskType {
    /// Simple Q&A or lookup (use fastest/cheapest backend)
    SimpleQuery,
    /// Multi-step reasoning with tool use (use most capable backend)
    ComplexReasoning,
    /// Autonomous task execution (use reliable, goal-aware backend)
    TaskExecution,
    /// Real-time interaction requiring speed (use low-latency backend)
    RealtimeInteraction,
    /// Specialized domain (use best-fit orchestrator)
    Specialized { domain: String },
}

impl TaskType {
    /// Classify a prompt into a task type.
    pub fn from_prompt(prompt: &str) -> Self {
        let lower = prompt.to_lowercase();

        if lower.contains("execute") || lower.contains("task") || lower.contains("run") {
            Self::TaskExecution
        } else if lower.contains("reasoning")
            || lower.contains("analyze")
            || lower.contains("think")
            || prompt.len() > 500
        {
            Self::ComplexReasoning
        } else if lower.contains("quick") || lower.contains("fast") {
            Self::RealtimeInteraction
        } else {
            Self::SimpleQuery
        }
    }
}

/// Orchestrator selection preference.
#[derive(Debug, Clone)]
pub enum SelectionCriteria {
    /// Minimize cost
    Cheapest,
    /// Maximize quality/reasoning
    BestQuality,
    /// Minimize latency
    Fastest,
    /// Use a specific orchestrator by name
    Specific(String),
    /// Intelligent routing (default)
    Auto,
}

/// Hybrid orchestrator that coordinates multiple backends.
#[derive(Debug)]
pub struct HybridOrchestrator {
    /// Available orchestrators by name
    orchestrators: HashMap<String, Arc<dyn Orchestrator>>,
    /// Routing strategy
    selection: SelectionCriteria,
    /// Performance metrics (for learning which backend works best)
    metrics: Arc<tokio::sync::Mutex<OrchestrationMetrics>>,
}

/// Tracks performance of each orchestrator over time.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OrchestrationMetrics {
    pub calls_by_orchestrator: HashMap<String, u32>,
    pub success_by_orchestrator: HashMap<String, u32>,
    pub avg_cost_by_orchestrator: HashMap<String, f64>,
    pub avg_latency_by_orchestrator: HashMap<String, u64>, // ms
}

impl HybridOrchestrator {
    pub fn new() -> Self {
        Self {
            orchestrators: HashMap::new(),
            selection: SelectionCriteria::Auto,
            metrics: Arc::new(tokio::sync::Mutex::new(OrchestrationMetrics::default())),
        }
    }

    /// Register an orchestrator backend
    pub fn register(&mut self, name: &str, orchestrator: Arc<dyn Orchestrator>) {
        info!("Registering orchestrator: {}", name);
        self.orchestrators.insert(name.to_string(), orchestrator);
    }

    /// Set the selection strategy
    pub fn with_selection(mut self, criteria: SelectionCriteria) -> Self {
        self.selection = criteria;
        self
    }

    /// Find the best orchestrator for a given task
    async fn select_orchestrator(
        &self,
        input: &OrchestratorInput,
    ) -> Result<Arc<dyn Orchestrator>> {
        let task_type = TaskType::from_prompt(&input.user_prompt);
        debug!("Task type: {:?}", task_type);

        let mut candidates: Vec<(String, Arc<dyn Orchestrator>)> = Vec::new();

        for (name, orch) in &self.orchestrators {
            if orch.is_ready().await {
                candidates.push((name.clone(), orch.clone()));
            }
        }

        if candidates.is_empty() {
            anyhow::bail!("No orchestrators ready");
        }

        let selected = match &self.selection {
            SelectionCriteria::Specific(name) => candidates
                .into_iter()
                .find(|(n, _)| n == name)
                .ok_or_else(|| anyhow::anyhow!("Orchestrator {} not available", name))?,
            SelectionCriteria::Cheapest => {
                let mut best = None;
                let mut min_cost = f64::MAX;
                for (name, orch) in &candidates {
                    if let Ok(cost) = orch.estimate_cost(input).await {
                        if cost < min_cost {
                            min_cost = cost;
                            best = Some((name.clone(), orch.clone()));
                        }
                    }
                }
                best.ok_or_else(|| anyhow::anyhow!("Could not estimate costs"))?
            }
            SelectionCriteria::BestQuality => {
                // Prefer Llama Prime if available, otherwise native
                if let Some(found) = candidates
                    .iter()
                    .find(|(n, _)| n.contains("llama") || n.contains("prime"))
                {
                    (found.0.clone(), found.1.clone())
                } else if let Some(found) = candidates.iter().find(|(n, _)| n.contains("native")) {
                    (found.0.clone(), found.1.clone())
                } else {
                    anyhow::bail!("No quality orchestrators available")
                }
            }
            SelectionCriteria::Fastest => {
                // For now, prefer native (local/fast)
                if let Some(found) = candidates
                    .iter()
                    .find(|(n, _)| n.contains("native") || n.contains("ollama"))
                {
                    (found.0.clone(), found.1.clone())
                } else if let Some(found) = candidates.first() {
                    (found.0.clone(), found.1.clone())
                } else {
                    anyhow::bail!("No fast orchestrators available")
                }
            }
            SelectionCriteria::Auto => {
                // Intelligent routing based on task type
                match task_type {
                    TaskType::SimpleQuery => {
                        // Use cheapest
                        let mut best = None;
                        let mut min_cost = f64::MAX;
                        for (name, orch) in &candidates {
                            if let Ok(cost) = orch.estimate_cost(input).await {
                                if cost < min_cost {
                                    min_cost = cost;
                                    best = Some((name.clone(), orch.clone()));
                                }
                            }
                        }
                        best.unwrap_or_else(|| candidates.first().unwrap().clone())
                    }
                    TaskType::ComplexReasoning => {
                        // Use best quality (Llama Prime preferred)
                        if let Some(found) = candidates
                            .iter()
                            .find(|(n, _)| n.contains("llama") || n.contains("prime"))
                        {
                            (found.0.clone(), found.1.clone())
                        } else if let Some(found) =
                            candidates.iter().find(|(n, _)| n.contains("native"))
                        {
                            (found.0.clone(), found.1.clone())
                        } else {
                            candidates.first().unwrap().clone()
                        }
                    }
                    TaskType::TaskExecution => {
                        // Use native (goal-aware, Empire-integrated)
                        if let Some(found) = candidates.iter().find(|(n, _)| n.contains("native")) {
                            (found.0.clone(), found.1.clone())
                        } else {
                            candidates.first().unwrap().clone()
                        }
                    }
                    TaskType::RealtimeInteraction => {
                        // Use fastest (native/ollama)
                        if let Some(found) = candidates
                            .iter()
                            .find(|(n, _)| n.contains("native") || n.contains("ollama"))
                        {
                            (found.0.clone(), found.1.clone())
                        } else {
                            candidates.first().unwrap().clone()
                        }
                    }
                    TaskType::Specialized { domain: _ } => candidates.first().unwrap().clone(),
                }
            }
        };

        info!("Selected orchestrator: {}", selected.0);
        Ok(selected.1)
    }

    /// Get current metrics
    pub async fn metrics(&self) -> OrchestrationMetrics {
        self.metrics.lock().await.clone()
    }
}

#[async_trait::async_trait]
impl Orchestrator for HybridOrchestrator {
    fn name(&self) -> &str {
        "prime-zero-hybrid"
    }

    async fn execute(&self, input: OrchestratorInput) -> Result<OrchestratorTrace> {
        let selected = self.select_orchestrator(&input).await?;
        let mut trace = selected.execute(input).await?;

        // Update metrics
        let mut metrics = self.metrics.lock().await;
        let orch_name = selected.name();
        *metrics
            .calls_by_orchestrator
            .entry(orch_name.to_string())
            .or_insert(0) += 1;
        if trace.actions.iter().all(|a| a.success) {
            *metrics
                .success_by_orchestrator
                .entry(orch_name.to_string())
                .or_insert(0) += 1;
        }

        trace.orchestrator_name = self.name().to_string();
        Ok(trace)
    }

    async fn estimate_cost(&self, input: &OrchestratorInput) -> Result<f64> {
        self.select_orchestrator(input)
            .await?
            .estimate_cost(input)
            .await
    }

    async fn is_ready(&self) -> bool {
        for orch in self.orchestrators.values() {
            if orch.is_ready().await {
                return true;
            }
        }
        false
    }
}

impl Default for HybridOrchestrator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::prime::orchestrator::{
        ActionOutcome, ExecutionConstraints, OrchestratorAction, OrchestratorInput,
    };

    #[derive(Debug)]
    struct EchoOrchestrator;

    #[async_trait::async_trait]
    impl Orchestrator for EchoOrchestrator {
        fn name(&self) -> &str {
            "echo"
        }

        async fn execute(&self, input: OrchestratorInput) -> Result<OrchestratorTrace> {
            let response = format!("echo: {}", input.user_prompt);
            Ok(OrchestratorTrace {
                orchestrator_name: self.name().to_string(),
                actions: vec![ActionOutcome {
                    action: OrchestratorAction::Conclude {
                        response: response.clone(),
                    },
                    success: true,
                    output: response.clone(),
                    cost_usd: None,
                    duration_ms: 0,
                }],
                input,
                final_response: response,
                total_cost_usd: 0.0,
                total_duration_ms: 0,
                iterations: 1,
            })
        }
    }

    fn input(prompt: &str) -> OrchestratorInput {
        OrchestratorInput {
            user_prompt: prompt.into(),
            empire_context: String::new(),
            companion_context: String::new(),
            mindset: String::new(),
            history: vec![],
            available_tools: vec![],
            constraints: ExecutionConstraints::default(),
        }
    }

    #[tokio::test]
    async fn hybrid_without_backends_errors() {
        let hybrid = HybridOrchestrator::new();
        assert!(hybrid.execute(input("hello")).await.is_err());
    }

    #[tokio::test]
    async fn hybrid_routes_to_registered_backend_and_records_metrics() {
        let mut hybrid = HybridOrchestrator::new();
        hybrid.register("echo", Arc::new(EchoOrchestrator));

        let trace = hybrid.execute(input("hello")).await.unwrap();
        assert_eq!(trace.final_response, "echo: hello");

        let metrics = hybrid.metrics().await;
        assert_eq!(metrics.calls_by_orchestrator.get("echo"), Some(&1));
        assert_eq!(metrics.success_by_orchestrator.get("echo"), Some(&1));
    }

    #[test]
    fn task_type_classifies_prompts() {
        assert_eq!(
            TaskType::from_prompt("run the tests"),
            TaskType::TaskExecution
        );
        assert_eq!(
            TaskType::from_prompt("analyze this"),
            TaskType::ComplexReasoning
        );
        assert_eq!(
            TaskType::from_prompt("quick answer"),
            TaskType::RealtimeInteraction
        );
        assert_eq!(TaskType::from_prompt("hello"), TaskType::SimpleQuery);
    }
}
