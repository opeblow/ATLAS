export default function RiskGauge({ score }: { score: number }) {
  const pct = Math.max(0, Math.min(1, score));
  const angle = 180 * pct;
  const label = pct < 0.4 ? "low" : pct < 0.7 ? "elevated" : "high";
  const col = pct < 0.4 ? "var(--positive)" : pct < 0.7 ? "var(--warning)" : "var(--negative)";

  const needleX = 90 + 72 * Math.cos(Math.PI - angle * (Math.PI / 180));
  const needleY = 88 - 72 * Math.sin(Math.PI - angle * (Math.PI / 180));

  return (
    <div className="gauge" style={{ textAlign: "center" }}>
      <svg viewBox="0 0 180 100" width="180" height="100" role="img" aria-label={`risk ${label}`}>
        <path
          d="M16 88 A72 72 0 0 1 164 88"
          fill="none"
          stroke="var(--fg)"
          strokeWidth="10"
          strokeLinecap="round"
        />
        <path
          d="M16 88 A72 72 0 0 1 164 88"
          fill="none"
          stroke={col}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${(Math.PI * 72 * pct).toFixed(1)} 400`}
        />
        <line x1="90" y1="88" x2={needleX} y2={needleY} stroke={col} strokeWidth="2.5" />
        <circle cx="90" cy="88" r="4" fill={col} />
      </svg>
      <div className="mono" style={{ marginTop: 4 }}>
        <span style={{ color: col, fontSize: 22, fontWeight: 700 }}>{score.toFixed(2)}</span>
        <span className="muted" style={{ fontSize: 12 }}> {label} risk</span>
      </div>
    </div>
  );
}