//! Prime Zero hybrid orchestrator trait — multiple reasoning backends can implement this.
//!
//! An Orchestrator is the core decision-making engine. Different implementations
//! (Llama Prime, native ZeroClaw, other frameworks) all implement this trait, allowing
//! them to be mixed and matched based on task type, availability, or performance needs.
//!
//! Each orchestrator:
//! - Receives a unified context (Empire goals, Companion tasks, user input, agent state)
//! - Produces a sequence of structured actions (tool calls, decisions, reflections)
//! - Reports outcomes (success/failure, reasoning trace, cost)
//!
//! ZeroClaw's trait system wraps the orchestrator output and routes to tools/providers.

use anyhow::Result;
use serde::{Deserialize, Serialize};
use std::fmt::Debug;

/// Structured input to any orchestrator: unified context from Empire + Companion + agent state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrchestratorInput {
    /// User's direct request or turn prompt.
    pub user_prompt: String,
    /// Current Empire mission + goal state (from offline::empire).
    pub empire_context: String,
    /// Companion task context (active tasks, recent completions).
    pub companion_context: String,
    /// Agent's current mindset/persona (from offline::mindset).
    pub mindset: String,
    /// Conversation history (last N messages for context window).
    pub history: Vec<(String, String)>, // (role, content)
    /// Available tools and their schemas (from src/tools).
    pub available_tools: Vec<ToolSchema>,
    /// Execution constraints (timeout, max_iterations, cost_limit, etc.).
    pub constraints: ExecutionConstraints,
}

/// Tool schema exposed to the orchestrator (name, description, params).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ToolSchema {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value, // JSON schema
}

/// Execution constraints that bound the orchestrator's behavior.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionConstraints {
    pub max_iterations: u32,
    pub timeout_secs: u64,
    pub max_cost_usd: Option<f64>,
    pub require_approval: bool,
    pub parallel_tools: bool,
}

impl Default for ExecutionConstraints {
    fn default() -> Self {
        Self {
            max_iterations: 10,
            timeout_secs: 300,
            max_cost_usd: None,
            require_approval: false,
            parallel_tools: true,
        }
    }
}

/// A single action the orchestrator decides to take.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum OrchestratorAction {
    /// Call a tool with parameters.
    ToolCall {
        tool_name: String,
        parameters: serde_json::Value,
    },
    /// Issue a reflection or reasoning step (no execution).
    Reflect { reasoning: String },
    /// Ask for human approval before proceeding.
    RequestApproval { message: String },
    /// Conclude the turn with a response.
    Conclude { response: String },
    /// Delegate to a sub-strategy (e.g., for complex multi-step reasoning).
    Delegate { strategy: String, input: String },
}

/// Outcome of executing an orchestrator's action.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ActionOutcome {
    pub action: OrchestratorAction,
    pub success: bool,
    pub output: String,
    pub cost_usd: Option<f64>,
    pub duration_ms: u64,
}

/// Full orchestrator execution trace: inputs, sequence of actions, outcomes, final response.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrchestratorTrace {
    pub orchestrator_name: String,
    pub input: OrchestratorInput,
    pub actions: Vec<ActionOutcome>,
    pub final_response: String,
    pub total_cost_usd: f64,
    pub total_duration_ms: u64,
    pub iterations: u32,
}

/// Core trait: any orchestrator backend implements this.
///
/// Implementations might be:
/// - `LlamaPrimeOrchestrator` — uses Llama Prime Agent's reasoning loop
/// - `NativeOrchestrator` — uses ZeroClaw's native agentic loop
/// - `HybridOrchestrator` — routes between multiple backends
/// - `StrategyOrchestrator` — uses pluggable reasoning strategies
#[async_trait::async_trait]
pub trait Orchestrator: Send + Sync + Debug {
    /// Name of this orchestrator (for tracing and logging).
    fn name(&self) -> &str;

    /// Execute one full turn: input → sequence of actions → final response.
    /// Returns a trace of the execution for observability and learning.
    async fn execute(&self, input: OrchestratorInput) -> Result<OrchestratorTrace>;

    /// Optional: check if this orchestrator is ready to handle a request.
    /// (e.g., Llama Prime might check if its model API is reachable)
    async fn is_ready(&self) -> bool {
        true
    }

    /// Optional: estimate cost before execution (for budget-conscious routing).
    async fn estimate_cost(&self, _input: &OrchestratorInput) -> Result<f64> {
        Ok(0.0)
    }
}
