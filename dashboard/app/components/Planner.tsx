"use client";

import { useMemo, useState } from "react";
import { jpost, DEFAULT_USER } from "../lib/api";

const SCH_URL =
  process.env.NEXT_PUBLIC_SCHEDULING_URL ||
  (process.env.NEXT_PUBLIC_ATLAS_URL
    ? `${process.env.NEXT_PUBLIC_ATLAS_URL}/schedule`
    : "http://127.0.0.1:8002");

const DAYS = Array.from({ length: 7 }, (_, i) => {
  const d = new Date();
  d.setDate(d.getDate() + i);
  return d.toISOString().slice(0, 10);
});

type Deadline = { id: string; title: string; due_at: string; weight: number };

type PlanBlock = { title: string; start_at: string; end_at: string; deadline_id?: string | null };

export default function Planner({ deadlines }: { deadlines: Deadline[] }) {
  const [hours, setHours] = useState<Record<string, { s: number; e: number }>>(
    Object.fromEntries(DAYS.map((d) => [d, { s: 18, e: 21 }]))
  );
  const [plan, setPlan] = useState<PlanBlock[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [commitMsg, setCommitMsg] = useState<string | null>(null);

  const available = useMemo(
    () =>
      DAYS.map((d) => ({ date: d, start_hour: hours[d].s, end_hour: hours[d].e })).filter(
        (a) => a.start_hour < a.end_hour
      ),
    [hours]
  );

  const deadlinePayload = deadlines.map((d) => ({
    title: d.title,
    due_at: d.due_at,
    weight: d.weight ?? 1,
  }));

  async function generate() {
    setBusy(true);
    setPlan(null);
    setCommitMsg(null);
    try {
      const j = await jpost(`${SCH_URL}/plan/week`, {
        user_id: DEFAULT_USER,
        deadlines: deadlinePayload,
        available_hours: available,
      });
      setPlan(j.proposed_blocks ?? []);
      if ((j.conflicts ?? []).length) setCommitMsg(`Plan has ${j.conflicts.length} conflicts.`);
    } catch (e: any) {
      setCommitMsg(`generate failed: ${e?.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  async function commit() {
    if (!plan?.length) return;
    setBusy(true);
    setCommitMsg(null);
    try {
      const j = await jpost(`${SCH_URL}/schedule/commit`, {
        user_id: DEFAULT_USER,
        blocks: plan,
        idempotency_key: crypto.randomUUID(),
      });
      const conflicts = (j.conflicts ?? []) as { block?: string }[];
      const added = j.calendar_diff?.added ?? j.committed ?? 0;
      setCommitMsg(
        `Locked in ${added} block(s).` +
          (conflicts.length ? ` ${conflicts.length} conflicted and were skipped.` : "")
      );
      setPlan(null);
    } catch (e: any) {
      setCommitMsg(`commit failed: ${e?.message ?? e}`);
    } finally {
      setBusy(false);
    }
  }

  const totalHours = daysWork(available);

  return (
    <div>
      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Availability · next 7 days ({totalHours}h selected)</h2>
        <div className="grid grid-3" style={{ gap: 8 }}>
          {DAYS.map((d) => (
            <div key={d} className="card" style={{ padding: 12, background: "var(--panel-2)" }}>
              <div className="faint mono" style={{ fontSize: 11, marginBottom: 6 }}>{d}</div>
              <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                <select
                  className="input"
                  style={{ padding: 4 }}
                  value={hours[d].s}
                  onChange={(e) => setHours({ ...hours, [d]: { ...hours[d], s: Number(e.target.value) } })}
                >
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>
                  ))}
                </select>
                <span className="faint">→</span>
                <select
                  className="input"
                  style={{ padding: 4 }}
                  value={hours[d].e}
                  onChange={(e) => setHours({ ...hours, [d]: { ...hours[d], e: Number(e.target.value) } })}
                >
                  {Array.from({ length: 24 }, (_, h) => (
                    <option key={h} value={h}>{String(h).padStart(2, "0")}:00</option>
                  ))}
                </select>
              </div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 14 }}>
          <button className="btn accent" onClick={generate} disabled={busy || !available.length}>
            {busy ? "planning…" : "Generate plan"}
          </button>
        </div>
      </div>

      {(commitMsg || plan) && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2>Proposal</h2>
          {commitMsg && <p className="muted" style={{ fontSize: 13 }}>{commitMsg}</p>}
          {plan && (
            <>
              <table className="tbl" style={{ marginBottom: 12 }}>
                <thead>
                  <tr>
                    <th>Day</th>
                    <th>Window</th>
                    <th>Block</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.map((b, i) => (
                    <tr key={i}>
                      <td className="mono muted">{b.start_at.slice(0, 10)}</td>
                      <td className="mono faint">{b.start_at.slice(11, 16)}–{b.end_at.slice(11, 16)}</td>
                      <td>{b.title}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button className="btn accent" onClick={commit} disabled={busy}>
                {busy ? "committing…" : `Commit ${plan.length} block(s)`}
              </button>
            </>
          )}
        </div>
      )}

      <div className="card">
        <h2>Deadlines the planner is working around</h2>
        <table className="tbl">
          <tbody>
            {deadlines.map((d) => (
              <tr key={d.id}>
                <td>{d.title}</td>
                <td className="mono muted amt">due {d.due_at.slice(0, 10)}</td>
                <td className="mono faint amt">weight {d.weight}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function daysWork(available: { start_hour: number; end_hour: number }[]) {
  return available.reduce((acc, a) => acc + (a.end_hour - a.start_hour), 0);
}