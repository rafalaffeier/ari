"""
AI Orchestrator — the main entry point for processing user messages.

Flow:
  user input
  → build prompt
  → call OpenAI
  → parse response
  → validate intent + params + confidence
  → return ActionIntent or clarification request
"""
from dataclasses import dataclass
from typing import Optional

from app.ai.clients.openai_client import complete
from app.ai.parsers.action_parser import ActionIntent, parse
from app.ai.parsers.validation_parser import validate_intent
from app.ai.prompts.action_prompt import build_action_prompt
from app.ai.prompts.system_prompt import SYSTEM_PROMPT
from app.ai.validators.schema_validator import validate_params
from app.ai.validators.confidence_validator import is_confident_enough
from app.tools.registry.registry import get_latest


@dataclass
class OrchestratorResult:
    intent:       ActionIntent
    valid:        bool
    errors:       list[str]
    needs_clarification: bool
    risk_level:   str = "low"


async def process(user_input: str, context: dict = {}) -> OrchestratorResult:
    """
    Main pipeline. Returns an OrchestratorResult.
    Callers decide whether to create an action or ask for clarification.
    """

    # 1. Build prompt + call AI (with one repair attempt on failure)
    prompt = build_action_prompt(user_input, context)
    raw = await _call_with_retry(prompt)

    # 2. Parse
    try:
        intent = parse(raw)
    except ValueError as e:
        return OrchestratorResult(
            intent=ActionIntent("parse_error", "unknown", 0.0, {}, raw),
            valid=False,
            errors=[str(e)],
            needs_clarification=True,
        )

    # 3. Handle clarification signals
    if intent.tool in ("unknown", "clarify"):
        return OrchestratorResult(
            intent=intent, valid=False,
            errors=[], needs_clarification=True,
        )

    # 4. Validate tool exists + confidence + schema
    errors = validate_intent(intent)

    tool = get_latest(intent.tool)
    risk = tool.risk_level if tool else "low"

    if not is_confident_enough(intent.confidence, risk):
        errors.append(
            f"Confidence {intent.confidence:.2f} below threshold for {risk}-risk tool"
        )

    param_errors = validate_params(intent.tool, intent.params)
    errors.extend(param_errors)

    return OrchestratorResult(
        intent=intent,
        valid=len(errors) == 0,
        errors=errors,
        needs_clarification=len(errors) > 0,
        risk_level=risk,
    )


async def _call_with_retry(prompt: str) -> str:
    """Call AI, retry once with a repair instruction if output is unusable."""
    raw = await complete(prompt)
    try:
        from app.ai.parsers.action_parser import parse
        parse(raw)
        return raw
    except ValueError:
        repair_prompt = (
            f"Your previous response was not valid JSON.\n"
            f"Original output: {raw}\n\n"
            f"Try again. Respond ONLY with a valid JSON object."
        )
        return await complete(repair_prompt)
