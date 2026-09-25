/// Prime Zero runner — main entry point for the hybrid orchestration engine.
///
/// Entry point for `zeroclaw prime` command. Loads Empire + Companion + Mindset,
/// builds the hybrid orchestrator, and runs an interactive or batch session.

use anyhow::Result;
use std::io::{self, BufRead, Write};
use std::path::PathBuf;
use std::sync::Arc;
use tracing::info;

use crate::config::Config;
use crate::offline::empire::Empire;
use crate::offline::mindset::Mindset;
use crate::companion::tasks::CompanionTaskList;

use super::{
    context::PrimeContext, hybrid::HybridOrchestrator, native::NativeOrchestrator,
    orchestrator::{ExecutionConstraints, OrchestratorInput, ToolSchema},
};

/// Run Prime Zero in interactive or batch mode.
pub async fn run(
    base_config: Config,
    provider_override: Option<String>,
    model_override: Option<String>,
    mission_override: Option<String>,
    message: Option<String>,
    interactive: bool,
) -> Result<()> {
    let workspace = base_config.workspace_dir.clone();

    info!("Prime Zero starting — hybrid orchestration engine");

    // ── Load persistent state ────────────────────────────────────────
    let mut empire = Empire::load(&workspace);
    if let Some(m) = mission_override {
        empire.mission = m;
    }
    if empire.mission.is_empty() {
        empire.mission = "Complete Prime Zero mission".to_string();
    }
    empire.begin_session();
    empire.save(&workspace)?;

    let mindset = Mindset::load(&workspace);
    mindset.save(&workspace).unwrap_or_default();

    let companion = CompanionTaskList::load(&workspace);

    // ── Create unified context ───────────────────────────────────────
    let prime_context = PrimeContext::new(empire, companion, mindset);

    // ── Build hybrid orchestrator ────────────────────────────────────
    let mut hybrid = HybridOrchestrator::new();

    // Register the native orchestrator
    let native = Arc::new(NativeOrchestrator::with_config(
        base_config.clone(),
        prime_context.mindset.as_ref().clone(),
        prime_context.empire.lock().await.clone(),
    ));
    hybrid.register("native", native);

    // TODO: Register Llama Prime when integration is complete
    // hybrid.register("llama-prime", Arc::new(llama_prime::LlamaPrimeOrchestrator::new()));

    let hybrid = Arc::new(hybrid);
    let hybrid_trait: Arc<dyn super::orchestrator::Orchestrator> = hybrid.clone();

    println!("╔══════════════════════════════════════════════════════╗");
    println!("║        Prime Zero — Hybrid Orchestration Engine      ║");
    println!("╚══════════════════════════════════════════════════════╝");
    println!();
    println!("{}", format_context_summary(&prime_context).await);
    println!();

    // ── Single-shot mode ────────────────────────────────────────────
    if let Some(msg) = message {
        execute_turn(&hybrid_trait, &prime_context, &msg).await?;
        prime_context.save(&workspace).await?;
        return Ok(());
    }

    // ── Interactive loop ─────────────────────────────────────────────
    if interactive {
        interactive_loop(&hybrid_trait, &prime_context, &workspace).await?;
    }

    Ok(())
}

/// Execute a single turn with the hybrid orchestrator.
async fn execute_turn(
    orchestrator: &Arc<dyn super::orchestrator::Orchestrator>,
    context: &PrimeContext,
    user_input: &str,
) -> Result<()> {
    context.add_message("user", user_input).await;

    let empire_context = context.empire.lock().await.to_context();
    let companion_tasks = context
        .companion
        .lock()
        .await
        .tasks
        .iter()
        .filter(|t| t.enabled)
        .map(|t| format!("- {}: {}", t.name, t.description))
        .collect::<Vec<_>>()
        .join("\n");

    let history = context.get_history(5).await;

    let input = OrchestratorInput {
        user_prompt: user_input.to_string(),
        empire_context,
        companion_context: if companion_tasks.is_empty() {
            "No active companion tasks.".to_string()
        } else {
            format!("## Active Companion Tasks\n{}", companion_tasks)
        },
        mindset: context.mindset.to_prompt_section(),
        history: history.clone(),
        available_tools: vec![
            ToolSchema {
                name: "read_file".to_string(),
                description: "Read contents of a file".to_string(),
                parameters: serde_json::json!({"type": "object"}),
            },
            ToolSchema {
                name: "write_file".to_string(),
                description: "Write to a file".to_string(),
                parameters: serde_json::json!({"type": "object"}),
            },
            ToolSchema {
                name: "execute_command".to_string(),
                description: "Execute a shell command".to_string(),
                parameters: serde_json::json!({"type": "object"}),
            },
        ],
        constraints: ExecutionConstraints::default(),
    };

    match orchestrator.execute(input).await {
        Ok(trace) => {
            println!("\n{}\n", trace.final_response);
            context.add_message("assistant", &trace.final_response).await;

            // Update metrics
            context
                .update_metrics(
                    trace.total_cost_usd,
                    trace.total_duration_ms,
                    0,
                    0,
                )
                .await;
        }
        Err(e) => {
            eprintln!("Error: {}", e);
        }
    }

    Ok(())
}

/// Interactive REPL for Prime Zero.
async fn interactive_loop(
    orchestrator: &Arc<dyn super::orchestrator::Orchestrator>,
    context: &PrimeContext,
    workspace: &PathBuf,
) -> Result<()> {
    let stdin = io::stdin();
    let mut reader = stdin.lock();
    loop {
        print!("prime> ");
        io::stdout().flush()?;

        let mut line = String::new();
        if reader.read_line(&mut line)? == 0 {
            break;
        }

        let input = line.trim();
        if input.is_empty() {
            continue;
        }

        // Slash commands
        if let Some(rest) = input.strip_prefix('/') {
            let parts: Vec<&str> = rest.splitn(2, ' ').collect();
            match parts[0] {
                "quit" | "exit" | "q" => {
                    println!("Saving context and exiting.");
                    context.save(workspace).await?;
                    break;
                }
                "status" => {
                    println!("{}", format_context_summary(context).await);
                }
                "metrics" => {
                    let trace = context.trace.lock().await;
                    println!("Cost: ${:.2}", trace.metrics.total_cost_usd);
                    println!("Duration: {}ms", trace.metrics.total_duration_ms);
                    println!("Actions: {}", trace.metrics.actions_taken);
                    println!("Goals: {}", trace.metrics.goals_completed);
                    println!("Tasks: {}", trace.metrics.tasks_executed);
                }
                "help" => {
                    println!("/status     — show Empire + Companion status");
                    println!("/metrics    — show execution metrics");
                    println!("/quit       — save and exit");
                }
                _ => println!("Unknown command: /{}", parts[0]),
            }
        } else {
            // Agent turn
            execute_turn(orchestrator, context, input).await?;
            context.save(workspace).await?;
        }
    }

    Ok(())
}

/// Format a summary of the current Prime Zero context.
async fn format_context_summary(context: &PrimeContext) -> String {
    let empire = context.empire.lock().await;
    let companion = context.companion.lock().await;

    format!(
        "Mission: {}\n\
         Goals: {} total ({} done, {} active, {} pending)\n\
         Tasks: {} active",
        empire.mission,
        empire.goals.len(),
        empire.goals.iter().filter(|g| g.status == crate::offline::empire::GoalStatus::Done).count(),
        empire.goals.iter().filter(|g| g.status == crate::offline::empire::GoalStatus::Active).count(),
        empire.goals.iter().filter(|g| g.status == crate::offline::empire::GoalStatus::Pending).count(),
        companion.tasks.iter().filter(|t| t.enabled).count()
    )
}
