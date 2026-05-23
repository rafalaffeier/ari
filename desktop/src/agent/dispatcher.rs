use serde::{Deserialize, Serialize};

#[derive(Debug, Deserialize)]
pub struct AgentCommand {
    pub action_id: String,
    pub tool: String,
    pub params: serde_json::Value,
}

#[derive(Debug, Serialize)]
pub struct AgentResult {
    pub action_id: String,
    pub status: String,
    pub result: serde_json::Value,
}

pub async fn dispatch(cmd: AgentCommand) -> AgentResult {
    match cmd.tool.as_str() {
        "open_file" => crate::tools::filesystem::open_file(cmd).await,
        _ => AgentResult {
            action_id: cmd.action_id,
            status: "failed".to_string(),
            result: serde_json::json!({"error": "unknown tool"}),
        }
    }
}
