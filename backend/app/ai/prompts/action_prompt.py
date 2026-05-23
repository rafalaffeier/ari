from app.tools.registry.registry import all_tools


def build_action_prompt(user_input: str, context: dict) -> str:
    tools_list = "\n".join(
        f"- {t.name} (scope: {t.scope}, risk: {t.risk_level}): {t.schema.get('description', 'no description')}"
        for t in all_tools()
    )

    workspace_context = ""
    if context.get("recent_messages"):
        workspace_context = "\n".join(
            f"[{m['role']}]: {m['content']}" for m in context["recent_messages"][-5:]
        )

    return f"""
Available tools:
{tools_list}

Recent conversation:
{workspace_context or "(none)"}

User request:
{user_input}

Respond ONLY with a JSON object.
""".strip()
