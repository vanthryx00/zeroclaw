//! Contract tests for repository facts documented in `CLAUDE.md`.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

const NEW_REPOSITORY_MAP_PATHS: &[&str] = &[
    "src/hardware/",
    "src/approval/",
    "src/auth/",
    "src/cost/",
    "src/cron/",
    "src/daemon/",
    "src/service/",
    "src/doctor/",
    "src/health/",
    "src/heartbeat/",
    "src/integrations/",
    "src/onboard/",
    "src/rag/",
    "src/skills/",
    "src/skillforge/",
    "src/tunnel/",
    "crates/robot-kit/",
    "python/zeroclaw_tools/",
    "dev/",
    "scripts/ci/",
    "fuzz/",
    "benches/",
];

const LANGUAGES: &[&str] = &["", "zh-CN", "ja", "ru", "fr", "vi"];

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn read_repository_file(path: impl AsRef<Path>) -> String {
    let path = repository_root().join(path);
    fs::read_to_string(&path)
        .unwrap_or_else(|error| panic!("failed to read {}: {error}", path.display()))
}

fn section<'a>(document: &'a str, heading: &str, next_heading: &str) -> &'a str {
    let start = document
        .find(heading)
        .unwrap_or_else(|| panic!("missing section heading: {heading}"));
    let remainder = &document[start + heading.len()..];
    let end = remainder
        .find(next_heading)
        .unwrap_or_else(|| panic!("missing next section heading: {next_heading}"));
    &remainder[..end]
}

fn code_spans(line: &str) -> Vec<&str> {
    line.split('`').skip(1).step_by(2).collect()
}

#[test]
fn expanded_repository_map_lists_unique_existing_paths() {
    let document = read_repository_file("CLAUDE.md");
    let map = section(
        &document,
        "## 4) Repository Map (High-Level)",
        "## 4.1 Documentation System Contract (Required)",
    );
    let documented_paths: Vec<&str> = map
        .lines()
        .filter(|line| line.starts_with("- `"))
        .filter_map(|line| code_spans(line).first().copied())
        .collect();
    let unique_paths: HashSet<&str> = documented_paths.iter().copied().collect();

    assert_eq!(
        documented_paths.len(),
        unique_paths.len(),
        "repository map contains duplicate path entries"
    );

    for path in &documented_paths {
        assert!(
            repository_root().join(path.trim_end_matches('/')).exists(),
            "documented repository path does not exist: {path}"
        );
    }

    for path in NEW_REPOSITORY_MAP_PATHS {
        assert!(
            unique_paths.contains(path),
            "new repository surface is absent from the map: {path}"
        );
    }
}

#[test]
fn sandbox_extension_point_matches_source_and_features() {
    let document = read_repository_file("CLAUDE.md");
    let security_traits = read_repository_file("src/security/traits.rs");
    let manifest = read_repository_file("Cargo.toml");

    assert!(
        document.contains("`src/security/traits.rs` (`Sandbox`)"),
        "Sandbox extension point is not documented"
    );
    assert!(
        security_traits.contains("pub trait Sandbox: Send + Sync"),
        "documented Sandbox trait is missing from its source file"
    );
    assert!(
        manifest
            .lines()
            .any(|line| line.starts_with("sandbox-landlock =")),
        "documented Landlock backend feature is missing"
    );
    assert!(
        manifest
            .lines()
            .any(|line| line.starts_with("sandbox-bubblewrap =")),
        "documented bubblewrap backend feature is missing"
    );
}

#[test]
fn workspace_and_python_companion_claims_match_manifests() {
    let document = read_repository_file("CLAUDE.md");
    let cargo_manifest = read_repository_file("Cargo.toml");
    let python_manifest = read_repository_file("python/pyproject.toml");

    for path in [
        "crates/robot-kit",
        "python/zeroclaw_tools",
        "python/pyproject.toml",
    ] {
        assert!(
            document.contains(&format!("`{path}`")),
            "workspace/package path is not documented: {path}"
        );
        assert!(
            repository_root().join(path).exists(),
            "documented workspace/package path does not exist: {path}"
        );
    }

    assert!(
        cargo_manifest.contains("members = [\".\", \"crates/robot-kit\"]"),
        "robot-kit is not a member of the Cargo workspace"
    );
    assert!(
        python_manifest.contains("name = \"zeroclaw-tools\""),
        "Python companion package metadata is missing"
    );
    assert!(
        python_manifest.contains("packages = [\"zeroclaw_tools\"]"),
        "Python companion package is not included in wheel builds"
    );
}

#[test]
fn multilingual_entry_points_cover_every_documented_language() {
    let document = read_repository_file("CLAUDE.md");
    let expected_readmes: Vec<String> = LANGUAGES
        .iter()
        .map(|language| match *language {
            "" => "README.md".to_owned(),
            language => format!("README.{language}.md"),
        })
        .collect();
    let expected_hubs: Vec<String> = expected_readmes
        .iter()
        .map(|readme| format!("docs/{readme}"))
        .collect();

    let readme_line = document
        .lines()
        .find(|line| line.starts_with("- root READMEs:"))
        .expect("missing canonical root README list");
    let hub_line = document
        .lines()
        .find(|line| line.starts_with("- docs hubs:"))
        .expect("missing canonical docs hub list");

    assert_eq!(code_spans(readme_line), expected_readmes);
    assert_eq!(code_spans(hub_line), expected_hubs);

    for path in expected_readmes.iter().chain(&expected_hubs) {
        assert!(
            repository_root().join(path).is_file(),
            "documented language entry point does not exist: {path}"
        );
    }

    assert_eq!(
        document.matches("EN/ZH/JA/RU/FR/VI").count(),
        4,
        "all navigation-parity rules must name the complete language set"
    );
}

#[test]
fn documented_ci_gate_inventory_exists() {
    const EXPECTED_GATES: &[&str] = &[
        "rust_quality_gate.sh",
        "rust_strict_delta_gate.sh",
        "docs_quality_gate.sh",
        "docs_links_gate.sh",
        "check_binary_size.sh",
        "detect_change_scope.sh",
    ];

    let document = read_repository_file("CLAUDE.md");
    let inventory_line = document
        .lines()
        .find(|line| line.contains("CI gate scripts live in"))
        .expect("missing CI gate script inventory");
    let spans = code_spans(inventory_line);

    assert_eq!(spans.first(), Some(&"scripts/ci/"));
    assert_eq!(&spans[1..], EXPECTED_GATES);

    for gate in EXPECTED_GATES {
        let path = repository_root().join("scripts/ci").join(gate);
        assert!(path.is_file(), "documented CI gate does not exist: {gate}");
        assert!(
            read_repository_file(path.strip_prefix(repository_root()).unwrap()).starts_with("#!/"),
            "documented CI gate is not a script: {gate}"
        );
    }
}

#[test]
fn skillforge_is_wired_only_into_the_binary() {
    let document = read_repository_file("CLAUDE.md");
    let main_source = read_repository_file("src/main.rs");
    let library_source = read_repository_file("src/lib.rs");
    let declares_skillforge = |line: &str| {
        matches!(
            line.trim(),
            "mod skillforge;" | "pub mod skillforge;" | "pub(crate) mod skillforge;"
        )
    };

    assert!(
        document.lines().any(|line| {
            line.starts_with("- `src/skillforge/`")
                && line.contains("binary-only")
                && line.contains("wired from `main.rs`, not `lib.rs`")
        }),
        "skillforge binary-only wiring is not documented"
    );
    assert!(main_source.lines().any(declares_skillforge));
    assert!(
        !library_source.lines().any(declares_skillforge),
        "skillforge must remain binary-only"
    );
}
