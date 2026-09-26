"""Tool registry — one file per MCP tool (Section 5).

Keeps a tight tool surface: 6 unambiguous tools so Alexa+'s reasoning layer
performs better than with overlapping alternatives.
"""

from __future__ import annotations

from atlas_mcp_server.tools import (
    assess_affordability,
    commit_schedule,
    get_daily_brief,
    get_risk_snapshot,
    log_transaction,
    plan_study_week,
)

_ALL = [
    assess_affordability,
    get_risk_snapshot,
    log_transaction,
    plan_study_week,
    commit_schedule,
    get_daily_brief,
]


def register(mcp: object) -> None:
    for module in _ALL:
        module.register(mcp)