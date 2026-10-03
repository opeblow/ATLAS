"use client";

import { useState } from "react";
import { jpost, ngn, DEFAULT_USER } from "../lib/api";

const FIN_URL =
  process.env.NEXT_PUBLIC_FINANCE_URL ||
  (process.env.NEXT_PUBLIC_ATLAS_URL
    ? `${process.env.NEXT_PUBLIC_ATLAS_URL}/finance`
    : "http://127.0.0.1:8001");

type Verdict = {
  verdict?: string;
  balance_ngn?: number;
  risk_score?: number;
  baseline_risk_score?: number;
  explanation?: string;
  error?: string;
};

export default function AffordabilityBox() {
  const [amount, setAmount] = useState("50000");
  const [category, setCategory] = useState("electronics");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Verdict | null>(null);

  async function check() {
    setBusy(true);
    setResult(null);
    try {
      setResult(
        (await jpost(`${FIN_URL}/assess/affordability`, {
          user_id: DEFAULT_USER,
          amount_ngn: Number(amount),
          category,
        })) as Verdict
      );
    } catch (e: any) {
      setResult({ error: String(e?.message ?? e) });
    } finally {
      setBusy(false);
    }
  }

  const tone = result?.verdict === "safe" ? "mint" : result?.verdict === "risky" ? "warn" : "rose";

  return (
    <div>
      <div className="grid grid-2" style={{ marginBottom: 14 }}>
        <label className="field">
          <span>Amount (NGN)</span>
          <input className="input mono" value={amount} onChange={(e) => setAmount(e.target.value)} type="number" min="0" />
        </label>
        <label className="field">
          <span>Category</span>
          <select className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
            {["electronics", "food", "transport", "fashion", "rent", "entertainment", "general"].map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </label>
      </div>
      <button className="btn accent" onClick={check} disabled={busy}>
        {busy ? "running the model…" : "Can I afford this?"}
      </button>

      {result && (
        <div
          className="card"
          style={{
            marginTop: 14,
            borderColor: tone === "mint" ? "rgba(52,211,153,.4)" : tone === "rose" ? "rgba(251,113,133,.4)" : "rgba(251,191,36,.4)",
          }}
        >
          {result.error ? (
            <p className="down">{result.error}</p>
          ) : (
            <>
              <div className="mono" style={{ fontWeight: 700, fontSize: 18, textTransform: "capitalize", color: tone === "mint" ? "var(--mint)" : tone === "rose" ? "var(--rose)" : "var(--amber)" }}>
                {result.verdict}
              </div>
              <p className="muted" style={{ margin: "8px 0 0", fontSize: 13 }}>{result.explanation}</p>
              <div className="mono faint" style={{ marginTop: 10, fontSize: 12 }}>
                balance {ngn(result.balance_ngn)} · risk {result.baseline_risk_score?.toFixed(2)} → {result.risk_score?.toFixed(2)}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}