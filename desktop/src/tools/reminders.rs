use std::process::Command;

use chrono::{Datelike, NaiveDateTime, Timelike};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CreatedReminder {
    pub list: String,
    pub title: String,
    pub due: String,
    pub reminder_id: Option<String>,
}

pub fn list_reminder_lists() -> Result<Vec<String>, String> {
    #[cfg(target_os = "macos")]
    let output = Command::new("osascript")
        .args(["-e", r#"tell application "Reminders" to get name of lists"#])
        .output();

    #[cfg(not(target_os = "macos"))]
    let output: Result<std::process::Output, std::io::Error> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "list_reminder_lists is currently supported on macOS only",
    ));

    match output {
        Ok(output) if output.status.success() => {
            let stdout = String::from_utf8_lossy(&output.stdout);
            Ok(parse_list_names(&stdout))
        }
        Ok(output) => Err(String::from_utf8_lossy(&output.stderr).trim().to_string()),
        Err(error) => Err(error.to_string()),
    }
}

pub fn create_reminder(list: &str, title: &str, due: &str) -> Result<CreatedReminder, String> {
    let list = validate_required("list", list)?;
    let title = validate_required("title", title)?;
    let due_dt = parse_local_datetime(due)?;

    #[cfg(target_os = "macos")]
    let output = Command::new("osascript")
        .args(["-e", &build_create_reminder_script(&list, &title, due_dt)])
        .output();

    #[cfg(not(target_os = "macos"))]
    let output: Result<std::process::Output, std::io::Error> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "create_reminder is currently supported on macOS only",
    ));

    match output {
        Ok(output) if output.status.success() => {
            let reminder_id = String::from_utf8_lossy(&output.stdout).trim().to_string();
            Ok(CreatedReminder {
                list,
                title,
                due: due_dt.format("%Y-%m-%dT%H:%M:%S").to_string(),
                reminder_id: (!reminder_id.is_empty()).then_some(reminder_id),
            })
        }
        Ok(output) => Err(String::from_utf8_lossy(&output.stderr).trim().to_string()),
        Err(error) => Err(error.to_string()),
    }
}

fn parse_list_names(output: &str) -> Vec<String> {
    output
        .trim()
        .split(',')
        .map(str::trim)
        .filter(|name| !name.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn validate_required(field: &str, value: &str) -> Result<String, String> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return Err(format!("{field} cannot be empty"));
    }
    Ok(trimmed.to_string())
}

fn parse_local_datetime(value: &str) -> Result<NaiveDateTime, String> {
    let trimmed = value.trim();
    NaiveDateTime::parse_from_str(trimmed, "%Y-%m-%dT%H:%M:%S")
        .or_else(|_| NaiveDateTime::parse_from_str(trimmed, "%Y-%m-%dT%H:%M"))
        .map_err(|_| "datetime must use YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS".to_string())
}

fn build_create_reminder_script(list: &str, title: &str, due: NaiveDateTime) -> String {
    format!(
        r#"set theDueDate to current date
set year of theDueDate to {due_year}
set month of theDueDate to {due_month}
set day of theDueDate to {due_day}
set time of theDueDate to (({due_hour} * hours) + ({due_minute} * minutes) + {due_second})
tell application "Reminders"
  if not (exists list "{list}") then error "Reminder list not found: {list}"
  tell list "{list}"
    set createdReminder to make new reminder with properties {{name:"{title}", due date:theDueDate}}
    return id of createdReminder
  end tell
end tell"#,
        due_year = due.year(),
        due_month = applescript_month(due.month()),
        due_day = due.day(),
        due_hour = due.hour(),
        due_minute = due.minute(),
        due_second = due.second(),
        list = escape_applescript_string(list),
        title = escape_applescript_string(title),
    )
}

fn applescript_month(month: u32) -> &'static str {
    match month {
        1 => "January",
        2 => "February",
        3 => "March",
        4 => "April",
        5 => "May",
        6 => "June",
        7 => "July",
        8 => "August",
        9 => "September",
        10 => "October",
        11 => "November",
        12 => "December",
        _ => "January",
    }
}

fn escape_applescript_string(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\r', " ")
        .replace('\n', " ")
}

#[cfg(test)]
mod tests {
    use super::{
        build_create_reminder_script, escape_applescript_string, parse_list_names,
        parse_local_datetime,
    };

    #[test]
    fn parses_reminder_lists() {
        assert_eq!(
            parse_list_names("Reminders, Work, Personal\n"),
            vec!["Reminders", "Work", "Personal"]
        );
    }

    #[test]
    fn escapes_reminder_script_strings() {
        assert_eq!(
            escape_applescript_string("Work \"Now\"\nBackslash \\"),
            "Work \\\"Now\\\" Backslash \\\\"
        );
    }

    #[test]
    fn builds_reminder_script_with_due_date() {
        let due = parse_local_datetime("2026-05-14T09:15").unwrap();
        let script = build_create_reminder_script("Tasks", "Call client", due);
        assert!(script.contains("set month of theDueDate to May"));
        assert!(script.contains("set time of theDueDate to ((9 * hours) + (15 * minutes) + 0)"));
        assert!(script.contains("tell list \"Tasks\""));
        assert!(script.contains("name:\"Call client\""));
    }
}
