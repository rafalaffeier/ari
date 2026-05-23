use tokio_tungstenite::connect_async;

pub async fn connect(
    backend_url: &str,
    agent_token: &str,
) -> Result<(), tokio_tungstenite::tungstenite::Error> {
    let url = format!("{}/ws/agent?token={}", backend_url, agent_token);
    let (_ws_stream, _) = connect_async(url.as_str()).await?;
    println!("Agent connected to {}", backend_url);
    // TODO: split into read/write halves and start dispatcher
    Ok(())
}
