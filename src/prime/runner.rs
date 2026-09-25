//! Prime Zero runner — main entry point for the hybrid orchestration engine.
//!
//! Entry point for `zeroclaw prime` command. Loads Empire + Companion + Mindset,
//! builds the hybrid orchestrator, and runs an interactive or batch session.

use anyhow::Result;
use std::io::{self, BufRead, Write};
use std::path::Path;
use std::sync::Arc;
use tracing::info;

use crate::companion::tasks::CompanionTaskList;
use crate::config::Config;
use crate::offline::empire::{Empire, GoalStatus};
use crate::offline::mindset::Mindset;

use super::{
    context::PrimeContext,
    hybrid::HybridOrchestrator,
    native::NativeOrchestrator,
    orchestrator::{ExecutionConstraints, OrchestratorInput},
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

    // Provider fallback chain (Anthropic → Gemini → Ollama) + SQLite memory,
    // shared with `zeroclaw empire`.
    let config =
        crate::offline::runner::build_empire_config(base_config, provider_override, model_override);
    let provider = config
        .default_provider
        .clone()
        .unwrap_or_else(|| "anthropic".to_string());
    let agent = crate::offline::runner::build_empire_agent(&config, &mindset)?;

    // ── Create unified context ───────────────────────────────────────
    let prime_context = PrimeContext::new(empire, companion, mindset);

    // ── Build hybrid orchestrator ────────────────────────────────────
    let mut hybrid = HybridOrchestrator::new();

    // Register the native orchestrator
    hybrid.register("native", Arc::new(NativeOrchestrator::new(agent, provider)));

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
        if !interactive {
            return Ok(());
        }
    }

    // ── Interactive loop (default; `-m` + `-i` continues after the message) ──
    interactive_loop(&hybrid_trait, &prime_context, &workspace).await?;

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
        // The native agent carries its own registered tool set.
        available_tools: Vec::new(),
        constraints: ExecutionConstraints::default(),
    };

    // Providers don't report token usage through the Agent yet, so fall back to
    // the backend's per-request estimate when the trace carries no cost.
    let estimated_cost = orchestrator.estimate_cost(&input).await.unwrap_or(0.0);

    match orchestrator.execute(input).await {
        Ok(trace) => {
            println!("\n{}\n", trace.final_response);
            context
                .add_message("assistant", &trace.final_response)
                .await;

            let cost = if trace.total_cost_usd > 0.0 {
                trace.total_cost_usd
            } else {
                estimated_cost
            };
            context
                .update_metrics(cost, trace.total_duration_ms, 0, 0)
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
    workspace: &Path,
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
                    println!("Est. cost: ${:.4}", trace.metrics.total_cost_usd);
                    println!("Duration: {}ms", trace.metrics.total_duration_ms);
                    println!("Actions: {}", trace.metrics.actions_taken);
                    println!("Goals: {}", trace.metrics.goals_completed);
                    println!("Tasks: {}", trace.metrics.tasks_executed);
                }
                "help" => {
                    println!("/status           — show Empire + Companion status");
                    println!("/metrics          — show execution metrics");
                    println!("/goal <t> | <d>   — add a new goal");
                    println!("/done <ID>        — mark goal done");
                    println!("/active <ID>      — mark goal active");
                    println!("/blocked <ID>     — mark goal blocked");
                    println!("/note <ID> <text> — append note to goal");
                    println!("/quit             — save and exit");
                }
                cmd => {
                    let args = parts.get(1).copied().unwrap_or("");
                    let outcome = {
                        let mut empire = context.empire.lock().await;
                        apply_goal_command(&mut empire, cmd, args)
                    };
                    match outcome {
                        Some(GoalCommandOutcome { message, completed }) => {
                            if completed {
                                context.update_metrics(0.0, 0, 1, 0).await;
                            }
                            context.save(workspace).await?;
                            println!("{message}");
                        }
                        None => println!("Unknown command: /{cmd}. Type /help for commands."),
                    }
                }
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
        empire
            .goals
            .iter()
            .filter(|g| g.status == GoalStatus::Done)
            .count(),
        empire
            .goals
            .iter()
            .filter(|g| g.status == GoalStatus::Active)
            .count(),
        empire
            .goals
            .iter()
            .filter(|g| g.status == GoalStatus::Pending)
            .count(),
        companion.tasks.iter().filter(|t| t.enabled).count()
    )
}

/// Result of an Empire goal slash command.
#[derive(Debug, PartialEq, Eq)]
struct GoalCommandOutcome {
    message: String,
    /// True when a goal transitioned to Done.
    completed: bool,
}

/// Apply an Empire goal command (`goal`, `done`, `active`, `blocked`, `note`).
///
/// Returns `None` for commands this function does not handle.
fn apply_goal_command(empire: &mut Empire, cmd: &str, args: &str) -> Option<GoalCommandOutcome> {
    let args = args.trim();
    let reply = |message: String| {
        Some(GoalCommandOutcome {
            message,
            completed: false,
        })
    };
    match cmd {
        "goal" => {
            if args.is_empty() {
                return reply("Usage: /goal <title> | <description>".into());
            }
            let (title, desc) = match args.split_once(" | ") {
                Some((t, d)) => (t.trim(), d.trim()),
                None => (args, ""),
            };
            let id = empire.add_goal(title, desc);
            reply(format!("Goal {id} added: {title}"))
        }
        "done" | "complete" | "active" | "blocked" => {
            let id = args.split_whitespace().next().unwrap_or("").to_uppercase();
            let status = match cmd {
                "active" => GoalStatus::Active,
                "blocked" => GoalStatus::Blocked,
                _ => GoalStatus::Done,
            };
            let done = status == GoalStatus::Done;
            let label = match cmd {
                "active" => "ACTIVE",
                "blocked" => "BLOCKED",
                _ => "DONE",
            };
            if !empire.set_status(&id, status) {
                return reply(format!("Unknown goal ID: {id}"));
            }
            let mut message = format!("Goal {id} marked {label}.");
            if done && empire.is_complete() {
                message.push_str("\nAll goals complete — Empire is finished!");
            }
            Some(GoalCommandOutcome {
                message,
                completed: done,
            })
        }
        "note" => {
            let Some((id, text)) = args.split_once(char::is_whitespace) else {
                return reply("Usage: /note <ID> <text>".into());
            };
            let id = id.to_uppercase();
            if empire.add_note(&id, text.trim()) {
                reply(format!("Note added to {id}."))
            } else {
                reply(format!("Unknown goal ID: {id}"))
            }
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn goal_commands_add_update_and_complete_goals() {
        let mut empire = Empire::default();
        let added = apply_goal_command(&mut empire, "goal", "Ship v1 | first release").unwrap();
        assert!(!added.completed);
        let id = empire.goals[0].id.clone();
        assert_eq!(empire.goals[0].title, "Ship v1");

        let noted = apply_goal_command(
            &mut empire,
            "note",
            &format!("{} halfway", id.to_lowercase()),
        );
        assert_eq!(noted.unwrap().message, format!("Note added to {id}."));

        let active = apply_goal_command(&mut empire, "active", &id).unwrap();
        assert!(!active.completed);
        assert_eq!(empire.goals[0].status, GoalStatus::Active);

        let done = apply_goal_command(&mut empire, "done", &id).unwrap();
        assert!(done.completed);
        assert_eq!(empire.goals[0].status, GoalStatus::Done);
    }

    #[test]
    fn goal_commands_reject_unknown_ids_and_bad_usage() {
        let mut empire = Empire::default();
        let unknown = apply_goal_command(&mut empire, "done", "G999").unwrap();
        assert!(!unknown.completed);
        assert!(unknown.message.starts_with("Unknown goal ID"));
        assert!(apply_goal_command(&mut empire, "goal", "  ")
            .unwrap()
            .message
            .starts_with("Usage"));
        assert!(apply_goal_command(&mut empire, "note", "G1")
            .unwrap()
            .message
            .starts_with("Usage"));
        assert!(apply_goal_command(&mut empire, "bogus", "").is_none());
        assert!(empire.goals.is_empty());
    }
}
