# ATLAS — 7-minute live demo script

A guided walkthrough that tells the whole story: real ML risk scoring, safe
voice retries, a genuine planner, reasoning with a cloud fallback, and a
dashboard that shows the agent working. Everything runs locally on Windows.

## 0. Pre-flight (already true on this machine)

Five processes in one `ATLAS` shell:

```powershell
# in atlas/  (the repo root)
$env:ATLAS_DATABASE_URL = "sqlite:///C:\Users\USER\Documents\ATLAS\atlas\atlas.db"
. .\scripts\dev.ps1        # boots risk-model 8000, finance 8001, scheduling 8002, mcp 8003
npm run dev                # dashboard on 3000 (dashboard/)
```

Check the foundation is alive:
```powershell
Invoke-WebRequest http://127.0.0.1:8000/health   # risk model
Invoke-WebRequest http://127.0.0.1:8003/health   # mcp gate
```

---

## Minute 0–1 — "The agent has a real model"

Open `ATLAS` PowerShell:

```
python demo_client.py            # mcp-server/tests helper or minimal MCP client
```

Walk the **risk snapshot** tool — show that the score isn't a rule:
  `get_risk_snapshot(u_demo)` → `0.09, low risk` + "income utilization lowers risk (impact −0.07)".

Point the judge at the *why*: the model is a trained PyTorch MLP (val R² 0.959)
served from its own service; the MCP server is just the mouthpiece. The factors
are computed from the gradient — surfaced factors, not canned strings.

## Minute 1–2 — "It judges affordability like an adviser"

```
assess_affordability(u_demo, amount_ngn=120_000, category='electronics')
```

- Verdict `safe`, risk moves `0.09 → 0.16`, balance `267,000`, "…you'd have about
  135,000 NGN left over."
- Now try `2,300,000` → verdict `blocked`. One model, two honest answers.
- Optional: seed some spend then re-check — same tool, changed circumstances.

**The trick worth showing:** the projection is deliberately *not* persisted, so
asking "what if I buy this" never poisons the score history. That's the delta
most naive demos skip.

## Minute 2–3 — "Voice retries are safe"

This is the demo's quiet flex. Call `log_transaction(u_demo, −45_000, 'food')`
**or** `commit_schedule` with a stored `idempotency_key`, then call it again
with the **same key**:

- First call: recorded / blocks added.
- Second call: `"already recorded"` / `"already committed"` no-op.

Say it out loud: *"Alexa retries voice commands; idempotency keys make a retry a
no-op instead of a double-spend or a double-booking."*

## Minute 3–4 — "It turns deadlines into a calendar"

```
plan_study_week(u_demo, deadlines=[AI Systems Assignment w3, Math Midterm w2],
                available_hours=[18:00–21:00 × 6 days])
```
- 15 proposed blocks, spaced across days (greedy spaced allocation), shown as a
  plan, not a pile-up on day zero.
- `commit_schedule(...)` → blocks land; a conflicting re-plan reports `conflicts`
  instead of overwriting.

Then switch to the dashboard tab for the **Time** screen and press *Generate
plan* → *Commit*, pointing out the same JSON is rendered as UI.

## Minute 4–5 — "Reasoning that never goes dark"

Run the reasoning layer twice in a row:

```powershell
python -m orchestrator --say "Can I afford a 120k laptop now?" --user u_demo
python -m orchestrator --say "Good morning" --user u_demo
```

With no AWS credentials, it prints `[reasoning] Bedrock unavailable … using local
fallback` and still answers correctly through the rule router. With Bedrock
reachable, the same entry point does a two-turn `converse` tool-use loop against
`amazon.nova-micro-v1:0`. Same `mcp_tool_calls` audit rows either way.

## Minute 5–6 — "The dashboard shows the agent working"

Open `http://localhost:3000/`. Four screens, one story:

1. **Today** — balance, risk gauge (0.09 · low), trend line, today's blocks,
   upcoming deadlines, shortcuts. Live from the services.
2. **Money** — the can-I-afford-it box (type 120000 → see the model's verdict
   inline), factor bars, ledger.
3. **Time** — availability picker, plan generator, one-click commit, committed
   calendar.
4. **Agent Log** — every tool call from every door (MCP, fallback, dashboard)
   with latency, auto-refreshing.

## Minute 6–7 — "Fast-forward to production"

Flip to `docs/aws-integration.md` / the `infra/terraform` folder and land the
mapping in under 60 seconds:

- identical code on **RDS Postgres** (one env var; `schema.sql` already
  partition-ready);
- four **Fargate** tasks + ALB path `/mcp*`;
- **Bedrock** `converse` as the hosted orchestrator, fallback router still there;
- **AgentCore** hosts the Alexa+ skill over the self-hosted MCP server.

---

## Dress-rehearsal gotchas

- Restart order: `risk-model` → `finance` → `scheduling` → `mcp`. The MCP server
  needs the two services; finance needs the model.
- If the demo DB drifts too far from the script's numbers, re-seed:
  `POST /demo/seed` on 8001 and 8002, then retrain or restart in order.
- The gauge/balance numbers in minute 0 come from the ledger; a different seed
  changes the words, not the narrative.
- Keep the dashboard tab at `:3000` open before the demo — first paint compiles
  on demand.