import { balance, ngn, risk, transactions, trend } from "../../lib/api";
import StatCard from "../../components/StatCard";
import RiskGauge from "../../components/RiskGauge";
import TrendLine from "../../components/TrendLine";
import AffordabilityBox from "../../components/AffordabilityBox";

export const dynamic = "force-dynamic";

export default async function Money() {
  const [bal, rk, tx, tr] = await Promise.all([balance().catch(() => null), risk().catch(() => null), transactions().catch(() => null), trend().catch(() => null)]);
  const rows = tx?.transactions ?? [];

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
        <StatCard label="Balance" value={ngn(bal?.balance_ngn)} sub="available cash" tone="accent" />
        <StatCard label="Risk" value={rk?.score?.toFixed(2) ?? "—"} sub={rk?.stale ? "stale snapshot" : "live model output"} tone={rk?.score >= 0.7 ? "down" : rk?.score >= 0.4 ? "warn" : "up"} />
        <StatCard label="Spend · 7d" value={ngn(rk?.spend_7d_ngn ?? 0)} sub="includes repeats" />
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
                    <span className="mono">{f.direction === "lowers risk" ? "−" : "+"}{Math.abs(f.impact).toFixed(3)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div style={{ marginTop: 12 }}>
            <TrendLine points={tr?.points ?? []} />
          </div>
        </div>

        <div className="card">
          <h2>Can-I-afford-it check</h2>
          <AffordabilityBox />
        </div>
      </div>

      <div className="card">
        <h2>Ledger · last {rows.length} movements</h2>
        <table className="tbl">
          <thead>
            <tr>
              <th>When</th>
              <th>Category</th>
              <th className="amt">Amount</th>
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 12).map((t: any) => (
              <tr key={t.id}>
                <td className="mono faint">{t.ts ? t.ts.slice(0, 16).replace("T", " ") : "—"}</td>
                <td>{t.category}</td>
                <td className={`mono amt ${t.amount_ngn < 0 ? "down" : "up"}`}>
                  {t.amount_ngn < 0 ? "−" : "+"}{ngn(t.amount_ngn)}
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
  // small helper to keep page file self-contained; route list above
  return (
    <a href="/today" className="btn">← today</a>
  );
}