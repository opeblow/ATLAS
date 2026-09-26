"""Amazon Bedrock tool-use loop using the Converse API.

Flow (mirrors the spec's AgentCore orchestration):
  turn 1 -> model sees the six ATLAS tools, returns toolUse blocks or a final
            answer; every requested tool is executed and its results fed back;
  turn 2 -> model drafts the spoken reply from the tool output.

Boto3 is imported lazily so the package still boots on machines without AWS
credentials (the driver falls back to the rule-based router).
"""

from __future__ import annotations

from orchestrator import executor
from orchestrator.tools_spec import TOOLS_SPEC

DEFAULT_MODEL = "amazon.nova-micro-v1:0"  # cheap + fast for structured drafting


class BedrockUnavailable(RuntimeError):
    """Raised when boto3 or the Bedrock endpoint cannot be reached."""


def _client():
    try:
        import boto3

        return boto3.client("bedrock-runtime", region_name="us-east-1")
    except Exception as exc:  # no boto3, bad creds, etc.
        raise BedrockUnavailable(str(exc)) from exc


def think(
    utterance: str,
    user_id: str = "u_demo",
    model: str = DEFAULT_MODEL,
    session: executor.SessionMemory | None = None,
) -> dict:
    """Drive a single utterance through Bedrock; returns an answer object.

    Never raises for tool failures — the model is asked to gloss over them.
    Any Bedrock-side failure (no creds, quota, bad params) surfaces as
    BedrockUnavailable so the driver can fall back to the local router.
    """
    memory = session or executor.SessionMemory()
    client = _client()  # may raise BedrockUnavailable -> driver falls back

    # Bedrock tool use plugs into the same input/output format as the MCP tools
    # but executes against REST directly; both stream identical audit rows.
    messages = [{"role": "user", "content": [{"text": utterance}]}]

    def _converse(msgs) -> dict:
        try:
            return client.converse(
                modelId=model,
                messages=msgs,
                toolConfig={"tools": TOOLS_SPEC},
                inferenceConfig={"maxTokens": 700, "temperature": 0.2},
            )
        except Exception as exc:
            raise BedrockUnavailable(str(exc)) from exc

    resp = _converse(messages)
    content = resp["output"]["message"]["content"]

    if resp.get("stopReason") == "tool_use":

        def _exec(tu_block: dict) -> dict:
            name = tu_block["name"]
            args = tu_block.get("input", {}) or {}
            if isinstance(args.get("user_id"), str) and not args["user_id"]:
                args["user_id"] = user_id
            if "user_id" not in args:
                args["user_id"] = user_id
            return executor.execute_tool(name, args, memory)

        tool_results = [
            {
                "toolResult": {
                    "toolUseId": b["toolUseId"],
                    "content": [{"json": _exec(b)}],
                }
            }
            for b in content
            if b.get("toolUse")
        ]
        messages.append({"role": "assistant", "content": content})
        messages.append({"role": "user", "content": tool_results})

        final = _converse(messages)
        content = final["output"]["message"]["content"]

    text = " ".join(c.get("text", "") for c in content if c.get("text"))
    return {
        "model": model,
        "utterance": utterance,
        "answer": text.strip() or "(no answer drafted)",
        "front_door": "bedrock",
    }