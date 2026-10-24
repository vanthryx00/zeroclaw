//! Prime Zero — next-generation autonomous agent built on hybrid orchestration.
//!
//! Prime Zero unifies the best of multiple agent systems:
//! - MegaZero's modular, trait-driven architecture
//! - Empire's goal tracking and persistence
//! - Companion's autonomous task execution
//! - Multi-provider fallback for resilience
//!
//! At its core: a pluggable orchestrator system that routes requests to the
//! best available backend, with unified context from Empire + Companion.
//!
//! # Architecture
//!
//! - `orchestrator.rs` — trait defining any orchestrator backend
//! - `native.rs` — MegaZero's native intelligent agent (default backend)
//! - `hybrid.rs` — router that selects the best orchestrator per request
//! - `context.rs` — unified execution context (Empire + Companion + agent state)
//! - `runner.rs` — main entry point for `mega_zero prime` command

pub mod context;
pub mod hybrid;
pub mod native;
pub mod orchestrator;
pub mod runner;
