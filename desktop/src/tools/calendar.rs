use std::process::Command;

use chrono::{Datelike, NaiveDateTime, Timelike};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CreatedCalendarEvent {
    pub calendar: String,
    pub title: String,
    pub start: String,
    pub end: String,
    pub event_id: Option<String>,
}

pub fn list_calendars() -> Result<Vec<String>, String> {
    #[cfg(target_os = "macos")]
    let output = Command::new("osascript")
        .args([
            "-e",
            r#"tell application "Calendar" to get name of calendars"#,
        ])
        .output();

    #[cfg(not(target_os = "macos"))]
    let output: Result<std::process::Output, std::io::Error> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "list_calendars is currently supported on macOS only",
    ));

    match output {
        Ok(output) if output.status.success() => {
            let stdout = String::from_utf8_lossy(&output.stdout);
            Ok(parse_calendar_names(&stdout))
        }
        Ok(output) => Err(String::from_utf8_lossy(&output.stderr).trim().to_string()),
        Err(error) => Err(error.to_string()),
    }
}

pub fn create_calendar_event(
    calendar: &str,
    title: &str,
    start: &str,
    end: &str,
) -> Result<CreatedCalendarEvent, String> {
    let calendar = validate_required("calendar", calendar)?;
    let title = validate_required("title", title)?;
    let start_dt = parse_local_datetime(start)?;
    let end_dt = parse_local_datetime(end)?;

    if end_dt <= start_dt {
        return Err("event end must be after event start".to_string());
    }

    #[cfg(target_os = "macos")]
    let output = Command::new("osascript")
        .args(["-e", &build_create_event_script(&calendar, &title, start_dt, end_dt)])
        .output();

    #[cfg(not(target_os = "macos"))]
    let output: Result<std::process::Output, std::io::Error> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "create_calendar_event is currently supported on macOS only",
    ));

    match output {
        Ok(output) if output.status.success() => {
            let event_id = String::from_utf8_lossy(&output.stdout).trim().to_string();
            Ok(CreatedCalendarEvent {
                calendar,
                title,
                start: start_dt.format("%Y-%m-%dT%H:%M:%S").to_string(),
                end: end_dt.format("%Y-%m-%dT%H:%M:%S").to_string(),
                event_id: (!event_id.is_empty()).then_some(event_id),
            })
        }
        Ok(output) => Err(String::from_utf8_lossy(&output.stderr).trim().to_string()),
        Err(error) => Err(error.to_string()),
    }
}

fn parse_calendar_names(output: &str) -> Vec<String> {
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

fn build_create_event_script(
    calendar: &str,
    title: &str,
    start: NaiveDateTime,
    end: NaiveDateTime,
) -> String {
    format!(
        r#"set theStartDate to current date
set year of theStartDate to {start_year}
set month of theStartDate to {start_month}
set day of theStartDate to {start_day}
set time of theStartDate to (({start_hour} * hours) + ({start_minute} * minutes) + {start_second})
set theEndDate to current date
set year of theEndDate to {end_year}
set month of theEndDate to {end_month}
set day of theEndDate to {end_day}
set time of theEndDate to (({end_hour} * hours) + ({end_minute} * minutes) + {end_second})
tell application "Calendar"
  if not (exists calendar "{calendar}") then error "Calendar not found: {calendar}"
  tell calendar "{calendar}"
    set createdEvent to make new event with properties {{summary:"{title}", start date:theStartDate, end date:theEndDate}}
    return uid of createdEvent
  end tell
end tell"#,
        start_year = start.year(),
        start_month = applescript_month(start.month()),
        start_day = start.day(),
        start_hour = start.hour(),
        start_minute = start.minute(),
        start_second = start.second(),
        end_year = end.year(),
        end_month = applescript_month(end.month()),
        end_day = end.day(),
        end_hour = end.hour(),
        end_minute = end.minute(),
        end_second = end.second(),
        calendar = escape_applescript_string(calendar),
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
        build_create_event_script, escape_applescript_string, parse_calendar_names,
        parse_local_datetime,
    };

    #[test]
    fn parses_osascript_calendar_list() {
        assert_eq!(
            parse_calendar_names("Home, Work, Family\n"),
            vec!["Home", "Work", "Family"]
        );
    }

    #[test]
    fn ignores_empty_names() {
        assert_eq!(parse_calendar_names("Home, , Work"), vec!["Home", "Work"]);
    }

    #[test]
    fn escapes_applescript_strings() {
        assert_eq!(
            escape_applescript_string("Work \"Personal\"\nBackslash \\"),
            "Work \\\"Personal\\\" Backslash \\\\"
        );
    }

    #[test]
    fn builds_create_event_script_with_dates() {
        let start = parse_local_datetime("2026-05-14T10:30").unwrap();
        let end = parse_local_datetime("2026-05-14T11:00:00").unwrap();
        let script = build_create_event_script("Work", "Meeting", start, end);
        assert!(script.contains("set month of theStartDate to May"));
        assert!(script.contains("set time of theStartDate to ((10 * hours) + (30 * minutes) + 0)"));
        assert!(script.contains("tell calendar \"Work\""));
        assert!(script.contains("summary:\"Meeting\""));
    }
}
