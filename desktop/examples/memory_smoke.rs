use ai_assistant_desktop_lib::memory::client::MemoryClient;
use std::time::{SystemTime, UNIX_EPOCH};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let backend_url = std::env::var("AI_ASSISTANT_BACKEND_URL")
        .unwrap_or_else(|_| "http://127.0.0.1:8000".into());
    let suffix = SystemTime::now().duration_since(UNIX_EPOCH)?.as_secs();
    let email = format!("desktop-smoke-{suffix}@example.com");
    let password = "secret12345";
    let day = "2026-05-11";
    let text = format!("Desktop Rust memory smoke passed at {suffix}.");

    let auth_client = MemoryClient::for_backend(backend_url.clone())?;
    let auth = auth_client.register(&email, password).await?;
    let workspace_id = auth
        .default_workspace_id
        .ok_or("register response did not include default_workspace_id")?;

    let client = MemoryClient::new(backend_url, auth.access_token, workspace_id)?;
    let write = client
        .append_journal_entry(
            day,
            "tasks",
            &text,
            Some("2026-05-11T20:00:00Z".to_string()),
        )
        .await?;
    println!("WRITE {} {}", write.workspace_id, write.date);

    let overview = client.read_journal_overview(day).await?;
    let tasks = overview
        .sections
        .get("tasks")
        .and_then(|value| value.as_array())
        .ok_or("overview did not include tasks array")?;
    if !tasks
        .iter()
        .any(|value| value.as_str().is_some_and(|line| line.contains(&text)))
    {
        return Err("written task was not present in overview".into());
    }
    println!("OVERVIEW {} tasks={}", overview.date, tasks.len());

    let results = client
        .search_memory("Desktop Rust memory smoke", Some(10))
        .await?;
    if results.is_empty() {
        return Err("search returned no desktop smoke result".into());
    }
    println!("SEARCH results={}", results.len());
    println!("DESKTOP_MEMORY_SMOKE_OK");

    Ok(())
}
