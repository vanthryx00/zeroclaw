use anyhow::Result;
use std::io::{self, BufRead, Write as IoWrite};
use std::path::PathBuf;

use crate::agent::agent::Agent;
use crate::agent::dispatcher::NativeToolDispatcher;
use crate::agent::memory_loader::DefaultMemoryLoader;
use crate::agent::prompt::SystemPromptBuilder;
use crate::config::{AgentConfig, Config, MemoryConfig, ReliabilityConfig};
use crate::memory;
use crate::observability;
use crate::providers;

use super::empire::{Empire, GoalStatus};
use super::mindset::{Mindset, MindsetSection};

/// Provider preference order for the offline Empire agent.
///
/// When the user passes `--provider auto` (or omits it), we try providers in
/// this order: Anthropic (Claude), Gemini, Ollama. The first one that has a
/// configured API key / reachable endpoint is used as primary; the rest become
/// fallback providers in `ReliabilityConfig::fallback_providers`.
const PROVIDER_CHAIN: &[&str] = &["anthropic", "gemini", "ollama"];

/// Entry point for `zeroclaw empire`.
///
/// Builds an offline-capable agent with:
/// - Multi-provider fallback: Anthropic → Gemini → Ollama
/// - Mindset persona injected at system-prompt level
/// - Empire goal context prepended to each turn
/// - SQLite memory so conversation survives process restarts
/// - Empire slash commands: /status, /goal, /done, /note, /mindset, /quit
pub async fn run(
    base_config: Config,
    provider_override: Option<String>,
    model_override: Option<String>,
    mission: Option<String>,
    message: Option<String>,
) -> Result<()> {
    let workspace = base_config.workspace_dir.clone();

    // ── Load or bootstrap persistent state ──────────────────────────
    let mindset = Mindset::load(&workspace);
    mindset.save(&workspace).unwrap_or_default();

    let mut empire = Empire::load(&workspace);
    if let Some(m) = mission {
        empire.mission = m;
    }
    if empire.mission.is_empty() {
        empire.mission = "Build and complete the Empire".to_string();
    }
    empire.begin_session();
    empire.save(&workspace)?;

    // ── Build effective config ───────────────────────────────────────
    let effective_config = build_empire_config(base_config, provider_override, model_override);

    // ── Build agent with mindset injected into the system prompt ────
    let mut agent = build_empire_agent(&effective_config, &mindset)?;

    println!("=== ZeroClaw Empire Agent ===");
    println!("{}", empire.status_summary());
    println!();
    println!("Commands: /status  /goal <title> | <desc>  /done <ID>  /note <ID> <text>");
    println!("          /active <ID>  /blocked <ID>  /mindset  /quit");
    println!();

    if empire.is_complete() {
        println!("All Empire goals are DONE. Empire is complete!");
    }

    // ── Single-shot mode ────────────────────────────────────────────
    if let Some(msg) = message {
        let context = empire.to_context();
        let enriched = format!("{context}\n{msg}");
        let response = agent.turn(&enriched).await?;
        println!("{response}");
        empire.save(&workspace)?;
        return Ok(());
    }

    // ── Interactive loop ─────────────────────────────────────────────
    let stdin = io::stdin();
    loop {
        print!("empire> ");
        io::stdout().flush()?;

        let mut line = String::new();
        if stdin.lock().read_line(&mut line)? == 0 {
            break; // EOF
        }
        let input = line.trim();
        if input.is_empty() {
            continue;
        }

        // ── Slash commands ──────────────────────────────────────────
        if let Some(rest) = input.strip_prefix('/') {
            let parts: Vec<&str> = rest.splitn(3, ' ').collect();
            match parts[0] {
                "quit" | "exit" | "q" => {
                    println!("Session saved. Empire progress persisted.");
                    break;
                }
                "status" => {
                    println!("{}", empire.status_summary());
                    continue;
                }
                "mindset" => {
                    println!("{}", mindset.to_prompt_section());
                    continue;
                }
                "goal" => {
                    // /goal <title> | <desc>  or  /goal <title>
                    if parts.len() < 2 {
                        println!("Usage: /goal <title> | <description>");
                        continue;
                    }
                    let raw = parts[1..].join(" ");
                    let (title, desc) = if let Some(sep) = raw.find(" | ") {
                        (&raw[..sep], raw[sep + 3..].trim())
                    } else {
                        (raw.as_str(), "")
                    };
                    let id = empire.add_goal(title.trim(), desc);
                    empire.save(&workspace)?;
                    println!("Goal {id} added: {title}");
                    continue;
                }
                "done" | "complete" => {
                    let id = parts.get(1).unwrap_or(&"").to_uppercase();
                    if empire.set_status(&id, GoalStatus::Done) {
                        empire.save(&workspace)?;
                        println!("Goal {id} marked DONE.");
                        if empire.is_complete() {
                            println!("All goals complete — Empire is finished!");
                        }
                    } else {
                        println!("Unknown goal ID: {id}");
                    }
                    continue;
                }
                "active" => {
                    let id = parts.get(1).unwrap_or(&"").to_uppercase();
                    if empire.set_status(&id, GoalStatus::Active) {
                        empire.save(&workspace)?;
                        println!("Goal {id} marked ACTIVE.");
                    } else {
                        println!("Unknown goal ID: {id}");
                    }
                    continue;
                }
                "blocked" => {
                    let id = parts.get(1).unwrap_or(&"").to_uppercase();
                    if empire.set_status(&id, GoalStatus::Blocked) {
                        empire.save(&workspace)?;
                        println!("Goal {id} marked BLOCKED.");
                    } else {
                        println!("Unknown goal ID: {id}");
                    }
                    continue;
                }
                "note" => {
                    if parts.len() < 3 {
                        println!("Usage: /note <ID> <text>");
                        continue;
                    }
                    let id = parts[1].to_uppercase();
                    let note = parts[2];
                    if empire.add_note(&id, note) {
                        empire.save(&workspace)?;
                        println!("Note added to {id}.");
                    } else {
                        println!("Unknown goal ID: {id}");
                    }
                    continue;
                }
                "help" => {
                    println!("/status          — show Empire goal summary");
                    println!("/goal <t> | <d>  — add a new goal");
                    println!("/done <ID>        — mark goal done");
                    println!("/active <ID>      — mark goal active");
                    println!("/blocked <ID>     — mark goal blocked");
                    println!("/note <ID> <text> — append note to goal");
                    println!("/mindset          — show current mindset");
                    println!("/quit             — exit and save");
                    continue;
                }
                other => {
                    println!("Unknown command: /{other}. Type /help for commands.");
                    continue;
                }
            }
        }

        // ── Agent turn — prepend empire context ─────────────────────
        let context = empire.to_context();
        let enriched = format!("{context}\nUser: {input}");

        match agent.turn(&enriched).await {
            Ok(response) => {
                println!("\n{response}\n");
                empire.save(&workspace)?;
            }
            Err(e) => {
                eprintln!("Error: {e}");
            }
        }
    }

    Ok(())
}

/// Build a Config tuned for the offline Empire agent.
///
/// - Sets provider fallback chain: primary → remaining in PROVIDER_CHAIN
/// - Enables SQLite memory with auto-save
/// - Disables features not needed for offline operation
pub fn build_empire_config(
    mut config: Config,
    provider_override: Option<String>,
    model_override: Option<String>,
) -> Config {
    let primary = provider_override
        .or_else(|| config.default_provider.clone())
        .unwrap_or_else(|| "anthropic".to_string());

    config.default_provider = Some(primary.clone());

    if let Some(m) = model_override {
        config.default_model = Some(m);
    } else if config.default_model.is_none() {
        config.default_model = Some(match primary.as_str() {
            "gemini" => "gemini-2.0-flash".to_string(),
            "ollama" => "llama3.2".to_string(),
            _ => "claude-sonnet-4-20250514".to_string(),
        });
    }

    // Build fallback chain from remaining providers in the canonical order.
    let fallbacks: Vec<String> = PROVIDER_CHAIN
        .iter()
        .filter(|&&p| p != primary.as_str())
        .map(|&p| p.to_string())
        .collect();

    config.reliability = ReliabilityConfig {
        provider_retries: 2,
        fallback_providers: fallbacks,
        ..ReliabilityConfig::default()
    };

    // Persistent SQLite memory with auto-save.
    config.memory = MemoryConfig {
        backend: "sqlite".to_string(),
        auto_save: true,
        ..MemoryConfig::default()
    };

    config
}

/// Construct an Agent with the MindsetSection prepended to the system prompt.
pub fn build_empire_agent(config: &Config, mindset: &Mindset) -> Result<Agent> {
    let observer: std::sync::Arc<dyn observability::Observer> =
        std::sync::Arc::from(observability::create_observer(&config.observability));
    let runtime: std::sync::Arc<dyn crate::runtime::RuntimeAdapter> =
        std::sync::Arc::from(crate::runtime::create_runtime(&config.runtime)?);
    let security = std::sync::Arc::new(crate::security::SecurityPolicy::from_config(
        &config.autonomy,
        &config.workspace_dir,
    ));

    let memory: std::sync::Arc<dyn memory::Memory> =
        std::sync::Arc::from(memory::create_memory_with_storage_and_routes(
        &config.memory,
        &config.embedding_routes,
        Some(&config.storage.provider.config),
        &config.workspace_dir,
        config.api_key.as_deref(),
    )?);

    let tools = crate::tools::all_tools_with_runtime(
        std::sync::Arc::new(config.clone()),
        &security,
        runtime,
        memory.clone(),
        None,
        None,
        &config.browser,
        &config.http_request,
        &config.workspace_dir,
        &config.agents,
        config.api_key.as_deref(),
        config,
    );

    let provider_name = config
        .default_provider
        .as_deref()
        .unwrap_or("anthropic");
    let model_name = config
        .default_model
        .as_deref()
        .unwrap_or("claude-sonnet-4-20250514")
        .to_string();

    let provider: Box<dyn providers::Provider> = providers::create_routed_provider(
        provider_name,
        config.api_key.as_deref(),
        config.api_url.as_deref(),
        &config.reliability,
        &config.model_routes,
        &model_name,
    )?;

    let use_native = provider.supports_native_tools();
    let tool_dispatcher: Box<dyn crate::agent::dispatcher::ToolDispatcher> = if use_native {
        Box::new(NativeToolDispatcher)
    } else {
        Box::new(crate::agent::dispatcher::XmlToolDispatcher)
    };

    // Mindset is the first section so it anchors the entire system prompt.
    let prompt_builder = SystemPromptBuilder::with_defaults_preceded_by(Box::new(MindsetSection {
        mindset: mindset.clone(),
    }));

    let agent_cfg = AgentConfig {
        max_history_messages: config.agent.max_history_messages,
        max_tool_iterations: config.agent.max_tool_iterations,
        parallel_tools: config.agent.parallel_tools,
        ..AgentConfig::default()
    };

    Agent::builder()
        .provider(provider)
        .tools(tools)
        .memory(memory)
        .observer(observer)
        .tool_dispatcher(tool_dispatcher)
        .memory_loader(Box::new(DefaultMemoryLoader::new(
            5,
            config.memory.min_relevance_score,
        )))
        .prompt_builder(prompt_builder)
        .config(agent_cfg)
        .model_name(model_name)
        .temperature(config.default_temperature)
        .workspace_dir(config.workspace_dir.clone())
        .identity_config(config.identity.clone())
        .skills(crate::skills::load_skills_with_config(
            &config.workspace_dir,
            config,
        ))
        .skills_prompt_mode(config.skills.prompt_injection_mode)
        .auto_save(true)
        .build()
}

/// Workspace path for empire state files (exposed for `zeroclaw empire status`).
pub fn empire_path(workspace: &PathBuf) -> PathBuf {
    workspace.join("empire.toml")
}
