use tokio::time::{interval, Duration};

pub async fn start(tx: tokio::sync::mpsc::Sender<String>) {
    let mut ticker = interval(Duration::from_secs(20));
    loop {
        ticker.tick().await;
        let _ = tx.send(r#"{"type":"ping"}"#.to_string()).await;
    }
}
