/// Prime Zero unified execution context — merges Empire, Companion, and agent state.
///
/// This is the execution heart of Prime Zero: a rich context that orchestrators
/// can query and update to make intelligent, goal-aware decisions.
///
/// Contains:
/// - Empire mission and goal state
/// - Companion active tasks
/// - Agent mindset and persona
/// - Conversation history
/// - Available tools and providers
/// - Execution metrics and traces

use crate::offline::empire::Empire;
use crate::offline::mindset::Mindset;
use crate::companion::tasks::CompanionTaskList;
use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::Arc;

/// Unified execution context for Prime Zero.
#[derive(Debug, Clone)]
pub struct PrimeContext {
    /// Empire state: mission and goal tracking
    pub empire: Arc<tokio::sync::Mutex<Empire>>,
    /// Companion state: scheduled tasks
    pub companion: Arc<tokio::sync::Mutex<CompanionTaskList>>,
    /// Agent mindset and persona
    pub mindset: Arc<Mindset>,
    /// Conversation history
    pub history: Arc<tokio::sync::Mutex<Vec<(String, String)>>>, // (role, message)
    /// Execution trace: decisions, actions, outcomes
    pub trace: Arc<tokio::sync::Mutex<ExecutionTrace>>,
}

/// Tracks decisions, actions, and outcomes for observability.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExecutionTrace {
    pub session_id: String,
    pub decisions: Vec<Decision>,
    pub actions: Vec<Action>,
    pub metrics: ExecutionMetrics,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Decision {
    pub timestamp: String,
    pub reasoning: String,
    pub choice: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Action {
    pub timestamp: String,
    pub action_type: String,
    pub details: HashMap<String, String>,
    pub result: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ExecutionMetrics {
    pub total_cost_usd: f64,
    pub total_duration_ms: u64,
    pub actions_taken: u32,
    pub goals_completed: u32,
    pub tasks_executed: u32,
}

impl PrimeContext {
    /// Create a new unified context.
    pub fn new(
        empire: Empire,
        companion: CompanionTaskList,
        mindset: Mindset,
    ) -> Self {
        let session_id = uuid::Uuid::new_v4().to_string();
        Self {
            empire: Arc::new(tokio::sync::Mutex::new(empire)),
            companion: Arc::new(tokio::sync::Mutex::new(companion)),
            mindset: Arc::new(mindset),
            history: Arc::new(tokio::sync::Mutex::new(Vec::new())),
            trace: Arc::new(tokio::sync::Mutex::new(ExecutionTrace {
                session_id,
                ..Default::default()
            })),
        }
    }

    /// Get a snapshot of the current context as a formatted string.
    pub async fn to_formatted_string(&self) -> String {
        let empire = self.empire.lock().await;
        let companion = self.companion.lock().await;
        let trace = self.trace.lock().await;

        format!(
            "# Prime Zero Context\n\
             \n## Mission\n{}\n\n## Goals\n{}\n\n## Active Tasks\n{}\n\n## Mindset\n{}\n\n## Metrics\n{:?}",
            empire.mission,
            empire
                .goals
                .iter()
                .map(|g| format!("- [{}] {}: {}", g.status.label(), g.id, g.title))
                .collect::<Vec<_>>()
                .join("\n"),
            companion
                .tasks
                .iter()
                .filter(|t| t.enabled)
                .map(|t| format!("- {}: {} (every {}s)", t.name, t.description, t.interval_secs))
                .collect::<Vec<_>>()
                .join("\n"),
            self.mindset.to_prompt_section(),
            trace.metrics
        )
    }

    /// Add a message to conversation history.
    pub async fn add_message(&self, role: &str, content: &str) {
        let mut history = self.history.lock().await;
        history.push((role.to_string(), content.to_string()));
    }

    /// Get conversation history (last N messages).
    pub async fn get_history(&self, limit: usize) -> Vec<(String, String)> {
        let history = self.history.lock().await;
        history
            .iter()
            .rev()
            .take(limit)
            .cloned()
            .collect::<Vec<_>>()
            .into_iter()
            .rev()
            .collect()
    }

    /// Record a decision in the trace.
    pub async fn record_decision(&self, reasoning: &str, choice: &str) {
        let mut trace = self.trace.lock().await;
        trace.decisions.push(Decision {
            timestamp: chrono::Utc::now().to_rfc3339(),
            reasoning: reasoning.to_string(),
            choice: choice.to_string(),
        });
    }

    /// Record an action and its result.
    pub async fn record_action(
        &self,
        action_type: &str,
        details: HashMap<String, String>,
        result: &str,
    ) {
        let mut trace = self.trace.lock().await;
        trace.actions.push(Action {
            timestamp: chrono::Utc::now().to_rfc3339(),
            action_type: action_type.to_string(),
            details,
            result: result.to_string(),
        });
    }

    /// Update execution metrics.
    pub async fn update_metrics(
        &self,
        cost: f64,
        duration_ms: u64,
        goals_completed: u32,
        tasks_executed: u32,
    ) {
        let mut trace = self.trace.lock().await;
        trace.metrics.total_cost_usd += cost;
        trace.metrics.total_duration_ms += duration_ms;
        trace.metrics.actions_taken += 1;
        trace.metrics.goals_completed += goals_completed;
        trace.metrics.tasks_executed += tasks_executed;
    }

    /// Save context state to disk for persistence.
    pub async fn save(&self, workspace: &std::path::Path) -> Result<()> {
        self.empire.lock().await.save(workspace)?;
        self.companion.lock().await.save(workspace)?;
        self.mindset.save(workspace)?;
        Ok(())
    }

    /// Load context from disk.
    pub fn load(workspace: &std::path::Path) -> Self {
        let empire = Empire::load(workspace);
        let companion = CompanionTaskList::load(workspace);
        let mindset = Mindset::load(workspace);
        Self::new(empire, companion, mindset)
    }
}
