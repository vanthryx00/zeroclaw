/// Offline-capable Empire agent: persistent mindset, goal tracking, multi-provider fallback.
///
/// The offline module provides:
/// - [`mindset`] — agent persona loaded from `<workspace>/mindset.toml`
/// - [`empire`]  — goal tracker persisted to `<workspace>/empire.toml`
/// - [`runner`]  — interactive agent loop wiring mindset + empire + provider chain
pub mod empire;
pub mod mindset;
pub mod runner;
