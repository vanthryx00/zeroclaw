use anyhow::Result;
use crate::config::Config;

pub async fn run(
    _config: Config,
    _provider: Option<String>,
    _model: Option<String>,
    _interval: Option<u64>,
    _once: bool,
) -> Result<()> {
    Ok(())
}
