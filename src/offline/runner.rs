use anyhow::Result;
use crate::config::Config;

pub async fn run(
    _config: Config,
    _provider: Option<String>,
    _model: Option<String>,
    _mission: Option<String>,
    message: Option<String>,
) -> Result<()> {
    if let Some(m) = message {
        println!("{}", m);
    }
    Ok(())
}

pub fn build_empire_config(config: Config, _provider: Option<String>, _model: Option<String>) -> Config {
    config
}

pub async fn build_empire_agent(
    _config: &Config,
    _mindset: &super::mindset::Mindset,
) -> Result<crate::agent::agent::Agent> {
    crate::agent::agent::Agent::from_config(_config)
}
