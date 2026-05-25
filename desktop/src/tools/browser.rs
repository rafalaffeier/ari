use std::process::Command;
use url::Url;

pub fn open_browser_url(raw_url: &str) -> Result<String, String> {
    let url = normalize_browser_url(raw_url)?;
    open_url_with_system_handler(&url)?;
    Ok(url.to_string())
}

pub fn open_auth_url(raw_url: &str) -> Result<String, String> {
    let url = normalize_browser_url(raw_url)?;

    #[cfg(target_os = "macos")]
    if open_chrome_app_window(&url).is_ok() {
        return Ok(url.to_string());
    }

    open_url_with_system_handler(&url)?;
    Ok(url.to_string())
}

pub fn close_auth_callback_window(port: u16) {
    #[cfg(target_os = "macos")]
    {
        let callback_127 = format!("http://127.0.0.1:{port}/ari/google/callback");
        let callback_localhost = format!("http://localhost:{port}/ari/google/callback");
        let script = format!(
            r#"on closeMatchingChromeTab(prefixOne, prefixTwo)
  tell application "Google Chrome"
    repeat with browserWindow in windows
      repeat with browserTab in tabs of browserWindow
        set tabUrl to URL of browserTab
        if tabUrl starts with prefixOne or tabUrl starts with prefixTwo then
          close browserTab
          return true
        end if
      end repeat
    end repeat
  end tell
  return false
end closeMatchingChromeTab

on closeMatchingSafariTab(prefixOne, prefixTwo)
  tell application "Safari"
    repeat with browserWindow in windows
      repeat with browserTab in tabs of browserWindow
        set tabUrl to URL of browserTab
        if tabUrl starts with prefixOne or tabUrl starts with prefixTwo then
          close browserTab
          return true
        end if
      end repeat
    end repeat
  end tell
  return false
end closeMatchingSafariTab

try
  if closeMatchingChromeTab("{}", "{}") then return
end try

try
  if closeMatchingSafariTab("{}", "{}") then return
end try
"#,
            callback_127, callback_localhost, callback_127, callback_localhost
        );
        let _ = Command::new("osascript").arg("-e").arg(script).output();
    }
}

fn open_url_with_system_handler(url: &Url) -> Result<(), String> {
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
        Ok(output) if output.status.success() => Ok(()),
        Ok(output) => Err(String::from_utf8_lossy(&output.stderr).trim().to_string()),
        Err(error) => Err(error.to_string()),
    }
}

#[cfg(target_os = "macos")]
fn open_chrome_app_window(url: &Url) -> Result<(), String> {
    let app_arg = format!("--app={}", url.as_str());
    let output = Command::new("open")
        .args(["-na", "Google Chrome", "--args", &app_arg])
        .output();
    match output {
        Ok(output) if output.status.success() => Ok(()),
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
