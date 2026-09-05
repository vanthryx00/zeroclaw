//! Contract tests for repository facts documented in `CLAUDE.md`.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

fn repository_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
}

fn read_repository_file(path: impl AsRef<Path>) -> String {
    let path = repository_root().join(path);
    fs::read_to_string(&path).unwrap_or_else(|error| {
        panic!("failed to read {}: {error}", path.display());
    })
}

fn section<'a>(document: &'a str, heading: &str, next_heading: &str) -> &'a str {
    let start = document
        .find(heading)
        .unwrap_or_else(|| panic!("missing section heading: {heading}"));
    let remainder = &document[start + heading.len()..];
    let end = remainder
        .find(next_heading)
        .unwrap_or_else(|| panic!("missing section heading: {next_heading}"));
    &remainder[..end]
}

fn documented_list_paths(section: &str) -> Vec<&str> {
    section
        .lines()
        .filter_map(|line| {
            let remainder = line.trim().strip_prefix("- `")?;
            let (path, _) = remainder.split_once('`')?;
            Some(path.trim_end_matches('/'))
        })
        .collect()
}

#[test]
fn extension_points_exist_and_declare_the_documented_traits() {
    let claude_md = read_repository_file("CLAUDE.md");
    let extension_points = section(
        &claude_md,
        "Key extension points:",
        "The repository is a Cargo workspace:",
    );
    let expected = [
        ("src/providers/traits.rs", "Provider"),
        ("src/channels/traits.rs", "Channel"),
        ("src/tools/traits.rs", "Tool"),
        ("src/memory/traits.rs", "Memory"),
        ("src/observability/traits.rs", "Observer"),
        ("src/runtime/traits.rs", "RuntimeAdapter"),
        ("src/peripherals/traits.rs", "Peripheral"),
        ("src/security/traits.rs", "Sandbox"),
    ];

    assert_eq!(
        documented_list_paths(extension_points),
        expected.iter().map(|(path, _)| *path).collect::<Vec<_>>(),
        "the documented extension-point list changed; update this contract test with it"
    );

    for (path, trait_name) in expected {
        let source = read_repository_file(path);
        let declaration = format!("pub trait {trait_name}");
        assert!(
            source.contains(declaration.as_str()),
            "{path} must declare the documented public {trait_name} trait"
        );
    }
}

#[test]
fn repository_map_contains_only_existing_unique_paths() {
    let claude_md = read_repository_file("CLAUDE.md");
    let repository_map = section(
        &claude_md,
        "## 4) Repository Map (High-Level)",
        "## 4.1 Documentation System Contract (Required)",
    );
    let paths = documented_list_paths(repository_map);
    let mut unique_paths = HashSet::new();

    assert!(!paths.is_empty(), "repository map must contain path entries");
    for path in paths {
        assert!(
            unique_paths.insert(path),
            "repository map contains the duplicate path `{path}`"
        );
        assert!(
            repository_root().join(path).exists(),
            "repository map references missing path `{path}`"
        );
    }
}

#[test]
fn workspace_and_companion_package_claims_match_manifests() {
    let root_manifest = read_repository_file("Cargo.toml");
    let robot_kit_manifest = read_repository_file("crates/robot-kit/Cargo.toml");
    let python_manifest = read_repository_file("python/pyproject.toml");

    assert!(
        root_manifest.contains("members = [\".\", \"crates/robot-kit\"]"),
        "Cargo workspace must contain the root crate and crates/robot-kit"
    );
    assert!(
        robot_kit_manifest.contains("name = \"zeroclaw-robot-kit\""),
        "crates/robot-kit must remain the documented robot-kit package"
    );
    assert!(
        python_manifest.contains("name = \"zeroclaw-tools\""),
        "python/ must contain the documented zeroclaw-tools package"
    );
}

#[test]
fn skillforge_is_wired_only_into_the_binary() {
    let main_source = read_repository_file("src/main.rs");
    let library_source = read_repository_file("src/lib.rs");

    assert!(
        main_source
            .lines()
            .any(|line| line.trim() == "mod skillforge;"),
        "src/main.rs must wire in the documented skillforge module"
    );
    assert!(
        !library_source
            .lines()
            .any(|line| line.trim() == "pub mod skillforge;" || line.trim() == "mod skillforge;"),
        "skillforge is documented as binary-only and must not be wired into src/lib.rs"
    );
}

#[test]
fn documented_features_and_ci_gates_are_present() {
    let root_manifest = read_repository_file("Cargo.toml");

    for feature in [
        "hardware",
        "rag-pdf",
        "sandbox-landlock",
        "sandbox-bubblewrap",
    ] {
        let feature_declaration = format!("{feature} =");
        assert!(
            root_manifest
                .lines()
                .any(|line| line.trim_start().starts_with(feature_declaration.as_str())),
            "Cargo.toml must define the documented `{feature}` feature"
        );
    }

    for path in [
        "dev/ci.sh",
        "scripts/ci/rust_quality_gate.sh",
        "scripts/ci/rust_strict_delta_gate.sh",
        "scripts/ci/docs_quality_gate.sh",
        "scripts/ci/docs_links_gate.sh",
        "scripts/ci/check_binary_size.sh",
        "scripts/ci/detect_change_scope.sh",
    ] {
        assert!(
            repository_root().join(path).is_file(),
            "documented CI entry point `{path}` must exist"
        );
    }
}

#[test]
fn documented_multilingual_entry_points_exist_for_every_language() {
    let claude_md = read_repository_file("CLAUDE.md");
    let docs_contract = section(
        &claude_md,
        "## 4.1 Documentation System Contract (Required)",
        "## 5) Risk Tiers by Path (Review Depth Contract)",
    );

    for path in [
        "README.md",
        "README.zh-CN.md",
        "README.ja.md",
        "README.ru.md",
        "README.fr.md",
        "README.vi.md",
        "docs/README.md",
        "docs/README.zh-CN.md",
        "docs/README.ja.md",
        "docs/README.ru.md",
        "docs/README.fr.md",
        "docs/README.vi.md",
    ] {
        let documented_path = format!("`{path}`");
        assert!(
            docs_contract.contains(documented_path.as_str()),
            "documentation contract must list `{path}`"
        );
        assert!(
            repository_root().join(path).is_file(),
            "documented multilingual entry point `{path}` must exist"
        );
    }
}
