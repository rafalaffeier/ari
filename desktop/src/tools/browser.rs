use std::process::Command;
use url::Url;

pub fn open_browser_url(raw_url: &str) -> Result<String, String> {
    let url = normalize_browser_url(raw_url)?;

    #[cfg(target_os = "macos")]
    let output = Command::new("open").arg(url.as_str()).output();

    #[cfg(target_os = "windows")]
    let output = Command::new("cmd")
        .args(["/C", "start", "", url.as_str()])
        .output();

    #[cfg(target_os = "linux")]
    let output = Command::new("xdg-open").arg(url.as_str()).output();

    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    let output: Result<std::process::Output, std::io::Error> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "open_browser_url is not supported on this platform",
    ));

    match output {
        Ok(output) if output.status.success() => Ok(url.to_string()),
        Ok(output) => Err(String::from_utf8_lossy(&output.stderr).trim().to_string()),
        Err(error) => Err(error.to_string()),
    }
}

fn normalize_browser_url(raw_url: &str) -> Result<Url, String> {
    let trimmed = raw_url.trim();
    if trimmed.is_empty() {
        return Err("url cannot be empty".to_string());
    }

    let candidate = if trimmed.contains("://") {
        trimmed.to_string()
    } else {
        format!("https://{trimmed}")
    };
    let parsed = Url::parse(&candidate).map_err(|_| "url must be valid".to_string())?;

    match parsed.scheme() {
        "http" | "https" => {}
        _ => return Err("only http and https urls can be opened".to_string()),
    }
    if parsed.host_str().is_none() {
        return Err("url must include a host".to_string());
    }
    Ok(parsed)
}

#[cfg(test)]
mod tests {
    use super::normalize_browser_url;

    #[test]
    fn accepts_https_url() {
        let url = normalize_browser_url("https://example.com/path").unwrap();
        assert_eq!(url.as_str(), "https://example.com/path");
    }

    #[test]
    fn adds_https_when_scheme_is_missing() {
        let url = normalize_browser_url("example.com").unwrap();
        assert_eq!(url.as_str(), "https://example.com/");
    }

    #[test]
    fn rejects_non_web_schemes() {
        assert!(normalize_browser_url("file:///etc/passwd").is_err());
        assert!(normalize_browser_url("javascript:alert(1)").is_err());
    }
}
