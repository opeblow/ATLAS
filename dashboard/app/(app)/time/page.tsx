"use client";

import { useEffect, useState } from "react";
import { deadlines, schedule, DEFAULT_USER } from "../../lib/api";
import Planner from "../../components/Planner";

// Client-rendered for Cloudflare static export; see the note in money/page.tsx.
export default function Time() {
  const [dl, setDl] = useState<any[]>([]);
  const [blocks, setBlocks] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      deadlines(DEFAULT_USER).catch(() => null),
      schedule(DEFAULT_USER).catch(() => null),
    ]).then(([d, s]) => {
      if (cancelled) return;
      setDl(d?.deadlines ?? []);
      setBlocks(s?.blocks ?? []);
      setLoading(false);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <div className="pagehead">
        <div>
          <div className="crumb">Time Desk</div>
          <h1>Turn deadlines into a calendar.</h1>
        </div>
        <a href="/today" className="btn">← today</a>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Committed blocks · next 7 days</h2>
        {!loading && blocks.length ? (
          <table className="tbl">
            <thead>
              <tr>
                <th>When</th>
                <th>Window</th>
                <th>Block</th>
              </tr>
            </thead>
            <tbody>
              {blocks.slice(0, 12).map((b: any) => (
                <tr key={b.id}>
                  <td className="mono muted">{b.start_at.slice(0, 10)}</td>
                  <td className="mono faint">
                    {b.start_at.slice(11, 16)}–{b.end_at.slice(11, 16)}
                  </td>
                  <td>{b.title}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>
            {loading ? "Loading…" : "Nothing committed yet — generate a plan below."}
          </p>
        )}
      </div>

      <Planner deadlines={dl} />
    </div>
  );
}