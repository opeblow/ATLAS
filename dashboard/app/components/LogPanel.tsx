"use client";

import { useCallback, useEffect, useState } from "react";
import { audit } from "../lib/api";

type Row = {
  id: string;
  tool_name: string;
  user_id: string;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error: string | null;
  latency_ms: number;
  created_at: string | null;
};

export default function LogPanel({ initial }: { initial: Row[] }) {
  const [rows, setRows] = useState<Row[]>(initial);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      setRows(((await audit(40)).rows ?? []) as Row[]);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    const t = setInterval(refresh, 8000);
    return () => clearInterval(t);
  }, [refresh]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>
          Every MCP tool call and orchestrator step lands here via the audit trail. Auto-refreshes every 8s.
        </p>
        <button className="btn" onClick={refresh} disabled={busy}>
          ⟳ refresh
        </button>
      </div>

      <div className="card">
        {rows.length ? (
          rows.map((r) => (
            <div className="log-row" key={r.id}>
              <div>
                <div className="tool">{r.tool_name}</div>
                <div className="when mono">{r.created_at ? r.created_at.slice(11, 19) : "—"}</div>
              </div>
              <div>
                <div className="faint mono" style={{ fontSize: 12 }}>
                  {r.user_id} · {r.latency_ms} ms
                </div>
                {r.input && (
                  <div className="mono" style={{ fontSize: 12, color: "var(--muted)" }}>
                    {JSON.stringify(r.input).slice(0, 120)}
                  </div>
                )}
                {r.error && <div className="down" style={{ fontSize: 12 }}>{r.error.slice(0, 140)}</div>}
              </div>
              <div className="mono" style={{ textAlign: "right", color: "var(--faint)", fontSize: 12 }}>
                {r.latency_ms >= 1500 ? ">1.5s" : r.latency_ms >= 500 ? ">500ms" : "fast"}
              </div>
            </div>
          ))
        ) : (
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>
            No tool activity recorded yet — say something to the agent.
          </p>
        )}
      </div>
    </div>
  );
}