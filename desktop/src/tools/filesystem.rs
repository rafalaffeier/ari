use crate::agent::dispatcher::{AgentCommand, AgentResult};
use std::env;
use std::path::{Path, PathBuf};
use std::process::Command;

pub async fn open_file(cmd: AgentCommand) -> AgentResult {
    let raw_path = cmd.params["path"].as_str().unwrap_or("");
    let policy = match FilePermissionPolicy::from_env() {
        Ok(policy) => policy,
        Err(error) => {
            return AgentResult {
                action_id: cmd.action_id,
                status: "failed".to_string(),
                result: serde_json::json!({"error": error}),
            };
        }
    };

    let path = match policy.validate_existing_path(raw_path) {
        Ok(path) => path,
        Err(error) => {
            return AgentResult {
                action_id: cmd.action_id,
                status: "failed".to_string(),
                result: serde_json::json!({"error": error}),
            };
        }
    };

    let path_arg = path.to_string_lossy().to_string();

    #[cfg(target_os = "macos")]
    let output = Command::new("open").arg(&path).output();

    #[cfg(target_os = "windows")]
    let output = Command::new("explorer").arg(&path).output();

    #[cfg(target_os = "linux")]
    let output = Command::new("xdg-open").arg(&path).output();

    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    let output: Result<std::process::Output, std::io::Error> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "open_file is not supported on this platform",
    ));

    match output {
        Ok(_) => AgentResult {
            action_id: cmd.action_id,
            status: "done".to_string(),
            result: serde_json::json!({"path": path_arg}),
        },
        Err(error) => AgentResult {
            action_id: cmd.action_id,
            status: "failed".to_string(),
            result: serde_json::json!({"error": error.to_string()}),
        },
    }
}

#[derive(Debug, Clone)]
pub struct FilePermissionPolicy {
    allowed_roots: Vec<PathBuf>,
}

impl FilePermissionPolicy {
    pub fn from_env() -> Result<Self, String> {
        let raw = env::var_os("AI_ASSISTANT_ALLOWED_PATHS").ok_or_else(|| {
            "AI_ASSISTANT_ALLOWED_PATHS must be set before filesystem tools can run".to_string()
        })?;
        Self::new(env::split_paths(&raw).collect())
    }

    pub fn new(allowed_roots: Vec<PathBuf>) -> Result<Self, String> {
        if allowed_roots.is_empty() {
            return Err("at least one allowed filesystem root is required".to_string());
        }

        let mut canonical_roots = Vec::new();
        for root in allowed_roots {
            if !root.is_absolute() {
                return Err("allowed filesystem roots must be absolute paths".to_string());
            }
            let canonical = root.canonicalize().map_err(|error| {
                format!("failed to resolve allowed root {}: {error}", root.display())
            })?;
            if !canonical.is_dir() {
                return Err(format!(
                    "allowed root is not a directory: {}",
                    canonical.display()
                ));
            }
            canonical_roots.push(canonical);
        }

        Ok(Self {
            allowed_roots: canonical_roots,
        })
    }

    pub fn validate_existing_path(&self, path: impl AsRef<Path>) -> Result<PathBuf, String> {
        let path = path.as_ref();
        if path.as_os_str().is_empty() {
            return Err("path cannot be empty".to_string());
        }
        if !path.is_absolute() {
            return Err("path must be absolute".to_string());
        }

        let canonical = path
            .canonicalize()
            .map_err(|error| format!("failed to resolve path {}: {error}", path.display()))?;
        if self
            .allowed_roots
            .iter()
            .any(|root| canonical == *root || canonical.starts_with(root))
        {
            Ok(canonical)
        } else {
            Err("path not allowed".to_string())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::FilePermissionPolicy;
    use std::fs;
    use std::path::{Path, PathBuf};
    use std::time::{SystemTime, UNIX_EPOCH};

    fn test_root() -> PathBuf {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("ai-assistant-fs-policy-{suffix}"));
        fs::create_dir_all(root.join("allowed")).unwrap();
        fs::create_dir_all(root.join("blocked")).unwrap();
        fs::write(root.join("allowed/file.txt"), "ok").unwrap();
        fs::write(root.join("blocked/file.txt"), "no").unwrap();
        root
    }

    fn policy(root: &Path) -> FilePermissionPolicy {
        FilePermissionPolicy::new(vec![root.join("allowed")]).unwrap()
    }

    #[test]
    fn accepts_file_inside_allowed_root() {
        let root = test_root();
        let path = policy(&root)
            .validate_existing_path(root.join("allowed/file.txt"))
            .unwrap();
        assert!(path.ends_with("allowed/file.txt"));
    }

    #[test]
    fn rejects_empty_path() {
        let root = test_root();
        assert!(policy(&root).validate_existing_path("").is_err());
    }

    #[test]
    fn rejects_relative_path() {
        let root = test_root();
        assert!(policy(&root).validate_existing_path("allowed/file.txt").is_err());
    }

    #[test]
    fn rejects_path_outside_allowed_root() {
        let root = test_root();
        assert!(policy(&root)
            .validate_existing_path(root.join("blocked/file.txt"))
            .is_err());
    }

    #[test]
    fn rejects_parent_segment_escape() {
        let root = test_root();
        assert!(policy(&root)
            .validate_existing_path(root.join("allowed/../blocked/file.txt"))
            .is_err());
    }

    #[test]
    fn rejects_missing_file() {
        let root = test_root();
        assert!(policy(&root)
            .validate_existing_path(root.join("allowed/missing.txt"))
            .is_err());
    }
}
