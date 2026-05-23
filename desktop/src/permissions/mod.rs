use std::path::{Component, PathBuf};

pub fn has_permission(permission_key: &str) -> bool {
    // TODO: check against local permission store
    matches!(
        permission_key,
        "filesystem.read"
            | "filesystem.write"
            | "browser.open"
            | "calendar.read"
            | "calendar.write"
            | "reminders.read"
            | "reminders.write"
    )
}

pub fn validate_local_memory_root(path: String) -> Result<PathBuf, String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("local_memory_root cannot be empty".to_string());
    }

    let root = PathBuf::from(trimmed);
    if !root.is_absolute() {
        return Err("local_memory_root must be an absolute path".to_string());
    }

    if root
        .components()
        .any(|component| matches!(component, Component::ParentDir))
    {
        return Err("local_memory_root cannot contain parent directory segments".to_string());
    }

    Ok(root)
}

#[cfg(test)]
mod tests {
    use super::validate_local_memory_root;
    use std::path::PathBuf;

    #[test]
    fn accepts_absolute_memory_root() {
        assert_eq!(
            validate_local_memory_root("/tmp/ai-assistant-memory".to_string()).unwrap(),
            PathBuf::from("/tmp/ai-assistant-memory")
        );
    }

    #[test]
    fn rejects_empty_memory_root() {
        assert!(validate_local_memory_root(" ".to_string()).is_err());
    }

    #[test]
    fn rejects_relative_memory_root() {
        assert!(validate_local_memory_root("memory".to_string()).is_err());
    }

    #[test]
    fn rejects_parent_segments() {
        assert!(validate_local_memory_root("/tmp/../secret".to_string()).is_err());
    }
}
