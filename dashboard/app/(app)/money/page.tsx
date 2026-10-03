"use client";

import { useEffect, useState } from "react";
import { balance, ngn, risk, transactions, trend, DEFAULT_USER } from "../../lib/api";
import StatCard from "../../components/StatCard";
import RiskGauge from "../../components/RiskGauge";
import TrendLine from "../../components/TrendLine";
import AffordabilityBox from "../../components/AffordabilityBox";

// Client-rendered so the dashboard can be statically exported to Cloudflare
// Pages. The previous version was an async server component, which forced a
// Node runtime and made a static deploy impossible.
export default function Money() {
  const [bal, setBal] = useState<any>(null);
  const [rk, setRk] = useState<any>(null);
  const [tx, setTx] = useState<any[]>([]);
  const [tr, setTr] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      balance(DEFAULT_USER).catch(() => null),
      risk(DEFAULT_USER).catch(() => null),
      transactions(DEFAULT_USER).catch(() => null),
      trend(DEFAULT_USER).catch(() => null),
    ]).then(([b, r, t, trd]) => {
      if (cancelled) return;
      setBal(b);
      setRk(r);
      setTx(t?.transactions ?? []);
      setTr(trd?.points ?? []);
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
          <div className="crumb">Money Desk</div>
          <h1>Cash, risk &amp; the ledger.</h1>
        </div>
        <Link_Home />
      </div>

      <div className="grid grid-3" style={{ marginBottom: 16 }}>
        <StatCard label="Balance" value={loading ? "—" : ngn(bal?.balance_ngn)} sub="available cash" tone="accent" />
        <StatCard
          label="Risk"
          value={loading ? "—" : (rk?.score?.toFixed(2) ?? "—")}
          sub={rk?.stale ? "stale snapshot" : "live model output"}
          tone={rk?.score >= 0.7 ? "down" : rk?.score >= 0.4 ? "warn" : "up"}
        />
        <StatCard label="Spend · 7d" value={loading ? "—" : ngn(rk?.spend_7d_ngn ?? 0)} sub="includes repeats" />
      </div>

      <div className="hero" style={{ marginBottom: 16 }}>
        <div className="card">
          <h2>Model explainability</h2>
          <div className="grid grid-2" style={{ gap: 8 }}>
            <RiskGauge score={rk?.score ?? 0} />
            <div>
              <div className="lang">
                {(rk?.factors ?? []).slice(0, 6).map((f: any) => (
                  <div className="kv" key={f.feature}>
                    <span>{f.label}</span>
                    <span className="mono">
                      {f.direction === "lowers risk" ? "−" : "+"}
                      {Math.abs(f.impact).toFixed(3)}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <TrendLine points={tr} />
          </div>
        </div>

        <div className="card">
          <h2>Can-I-afford-it check</h2>
          <AffordabilityBox />
        </div>
      </div>

      <div className="card">
        <h2>Ledger · last {tx.length} movements</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th>When</th>
              <th>Category</th>
              <th className="amt">Amount</th>
            </tr>
          </thead>
          <tbody>
            {tx.slice(0, 12).map((t: any) => (
              <tr key={t.id}>
                <td className="mono faint">{t.ts ? t.ts.slice(0, 16).replace("T", " ") : "—"}</td>
                <td>{t.category}</td>
                <td className={`mono amt ${t.amount_ngn < 0 ? "down" : "up"}`}>
                  {t.amount_ngn < 0 ? "−" : "+"}
                  {ngn(t.amount_ngn)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Link_Home() {
  return <a href="/today" className="btn">← today</a>;
}