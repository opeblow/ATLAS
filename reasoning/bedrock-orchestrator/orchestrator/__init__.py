"""ATLAS reasoning layer (AWS Builder mini-challenge, reasoning/orchestration).

Two front-doors:
  * `orchestrator.bedrock`  — Amazon Bedrock Converse with native tool use.
  * `orchestrator.fallback` — rule-based intent router used when Bedrock is
    unreachable (no AWS credentials locally, network restrictions, cost caps),
    so the demo never hard-depends on the cloud.

Both execute the same six ATLAS capabilities against the same REST backends
the MCP server wraps, then draft a human answer from the tool output.
"""

__version__ = "0.1.0"