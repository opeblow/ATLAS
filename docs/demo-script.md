# ATLAS — under-three-minute hackathon demo

**Primary track:** Alexa+ (self-hosted Streamable HTTP MCP server).
**Mini-challenge entries:** AWS Builder (Bedrock Converse integration) and Open
Source (MIT-licensed repository; see the submission caveat below).

Keep the recording under three minutes. Show the working interface and MCP
calls; do not narrate unimplemented Alexa+ account linking, bank/calendar
connectors, AgentCore hosting, production scale, or model accuracy.

## Before recording

From the repository root, install the Python packages in the active environment:

```powershell
python -m pip install -e .\services\common -e .\services\edge `
  -e .\services\risk-model -e .\services\finance-service `
  -e .\services\scheduling-service -e .\mcp-server `
  -e .\reasoning\bedrock-orchestrator
```

In terminal 1, start the single-origin demo with a disposable local database:

```powershell
$env:ATLAS_DATABASE_URL = "sqlite:///./atlas_demo.db"
$env:ATLAS_REQUIRE_AUTH = "1"
$env:ATLAS_SEED_ON_START = "1"
$env:ATLAS_MOCK_BEDROCK = "1"
python -m atlas_edge.asgi
```

Wait for `http://127.0.0.1:8000/edge/health` to return `{"status":"ok"}`.
In terminal 2, start the dashboard:

```powershell
cd dashboard
npm ci
$env:NEXT_PUBLIC_ATLAS_URL = "http://127.0.0.1:8000"
npm run dev
```

Open `http://localhost:3000`. In terminal 3, the MCP walkthrough can be run
with `python scripts/demo_client.py`. The service installs above include the
MCP client dependency. Rehearse the browser and terminal transitions first.

## Recording beats

| Time | Show | Say |
|---|---|---|
| 0:00–0:20 | Dashboard Today screen and seeded sample account | “ATLAS is a voice-first chief of staff for one everyday tension: deciding what you can spend while protecting time for what matters. This is a synthetic demo account.” |
| 0:20–0:45 | MCP client initializes and lists the six tools; call `get_risk_snapshot` and `assess_affordability` | “Alexa+ can connect through the self-hosted MCP Streamable HTTP server. Affordability is a projection; it does not write to the ledger.” |
| 0:45–1:10 | Call `log_transaction` twice with the same idempotency key; show first/duplicate result | “Voice clients retry. The ledger's database uniqueness rule makes this retry safe.” |
| 1:10–1:35 | Generate a study plan, commit it, then show Time screen | “ATLAS turns deadlines and availability into a proposal; the user reviews it before committing.” |
| 1:35–2:05 | Show the Agent Log and the dashboard's finance/time views | “The same backend powers the dashboard and MCP tools. The log makes the agent's actions inspectable.” |
| 2:05–2:35 | Show `/api/capabilities` and the system-design diagram | “This run uses a local simulated language router, not a live Bedrock call. Bedrock Converse is implemented as an optional AWS path. Today’s hosted demo is a single edge process and SQLite, not a million-user deployment.” |
| 2:35–2:55 | End on repository README and short call to action | “The next step is real identity and calendar/bank integrations, tested with user consent. Scores are experimental, based on synthetic training data, and not financial advice.” |

## Submission checks

- Record an English-language public YouTube or Vimeo video under 3 minutes.
- Verify all six tools and retry behavior against a running stack; do not rely on
  tests that skipped due to an unavailable server.
- The Open Source mini-challenge requires a **new additional project** or a
  contribution URL from the hackathon window. A license in this primary-track
  repository by itself does not prove that additional entry.
- Submit product feedback for each actually used Amazon tool/API/SDK. Clearly
  distinguish a local simulated response from a Bedrock response; do not invent
  onboarding experiences or product feedback that did not happen.
- Provide the repository URL, GitHub username, chosen tracks, a clear summary
  of changes made during the hackathon, and any required reviewer access.
