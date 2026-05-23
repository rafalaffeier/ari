use std::process::Command;

pub fn call_phone_number(raw_number: &str) -> Result<String, String> {
    let number = normalize_phone_number(raw_number)?;
    let url = format!("tel:{number}");

    #[cfg(target_os = "macos")]
    let output = Command::new("open").arg(&url).output();

    #[cfg(target_os = "windows")]
    let output = Command::new("cmd").args(["/C", "start", "", &url]).output();

    #[cfg(target_os = "linux")]
    let output = Command::new("xdg-open").arg(&url).output();

    #[cfg(not(any(target_os = "macos", target_os = "windows", target_os = "linux")))]
    let output: Result<std::process::Output, std::io::Error> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "phone calls are not supported on this platform",
    ));

    match output {
        Ok(output) if output.status.success() => Ok(number),
        Ok(output) => Err(String::from_utf8_lossy(&output.stderr).trim().to_string()),
        Err(error) => Err(error.to_string()),
    }
}

fn normalize_phone_number(raw_number: &str) -> Result<String, String> {
    let trimmed = raw_number.trim();
    if trimmed.is_empty() {
        return Err("phone number cannot be empty".to_string());
    }
    let mut normalized = String::new();
    for (index, ch) in trimmed.chars().enumerate() {
        if ch.is_ascii_digit() {
            normalized.push(ch);
        } else if ch == '+' && index == 0 {
            normalized.push(ch);
        } else if matches!(ch, ' ' | '-' | '(' | ')' | '.') {
            continue;
        } else {
            return Err("phone number contains unsupported characters".to_string());
        }
    }
    let digits = normalized.chars().filter(|ch| ch.is_ascii_digit()).count();
    if digits < 5 {
        return Err("phone number is too short".to_string());
    }
    Ok(normalized)
}

#[cfg(test)]
mod tests {
    use super::normalize_phone_number;

    #[test]
    fn normalizes_phone_number() {
        assert_eq!(
            normalize_phone_number("+34 600-111-222").unwrap(),
            "+34600111222"
        );
    }

    #[test]
    fn rejects_unsafe_phone_number() {
        assert!(normalize_phone_number("tel:+34600111222").is_err());
        assert!(normalize_phone_number("123").is_err());
    }
}
