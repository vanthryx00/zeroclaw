/// Prime Zero — next-generation autonomous agent built on hybrid orchestration.
///
/// Prime Zero unifies the best of multiple agent systems:
/// - ZeroClaw's modular, trait-driven architecture
/// - Llama Prime Agent's advanced reasoning (when available)
/// - Empire's goal tracking and persistence
/// - Companion's autonomous task execution
/// - Multi-provider fallback for resilience
///
/// At its core: a pluggable orchestrator system that routes requests to the
/// best available backend, with unified context from Empire + Companion.
///
/// # Architecture
///
/// - `orchestrator.rs` — trait defining any orchestrator backend
/// - `native.rs` — ZeroClaw's native intelligent agent (default backend)
/// - `hybrid.rs` — router that selects the best orchestrator per request
/// - `context.rs` — unified execution context (Empire + Companion + agent state)
/// - `runner.rs` — main entry point for `zeroclaw prime` command

pub mod orchestrator;
pub mod native;
pub mod hybrid;
pub mod context;
pub mod runner;
pub mod agent_adapter;

pub use orchestrator::{Orchestrator, OrchestratorInput, OrchestratorTrace, OrchestratorAction};
pub use hybrid::HybridOrchestrator;
pub use context::PrimeContext;
pub use runner::run;
pub use agent_adapter::NativeAgentAdapter;
