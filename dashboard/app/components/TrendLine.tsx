export default function TrendLine({ points }: { points: { score: number }[] }) {
  const scores = points.map((p) => p.score);
  if (scores.length < 2) {
    return <p className="faint">Not enough snapshots yet.</p>;
  }
  const W = 600;
  const H = 90;
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const span = max - min || 1;
  const px = (i: number) => (i / (scores.length - 1)) * (W - 20) + 10;
  const py = (v: number) => H - 12 - ((v - min) / span) * (H - 24);
  const path = scores.map((v, i) => `${i === 0 ? "M" : "L"}${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");
  const last = scores[scores.length - 1];
  const first = scores[0];

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="risk trend">
        <path d={path} fill="none" stroke="currentColor" strokeWidth="2" />
        {scores.map((v, i) => (
          <circle key={i} cx={px(i)} cy={py(v)} r="2.5" fill="currentColor" />
        ))}
      </svg>
      <div className="mono" style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "var(--fg-faint)" }}>
        <span>
          {first.toFixed(2)} → <span style={{ color: last >= first ? "var(--negative)" : "var(--positive)" }}>{last.toFixed(2)}</span>
        </span>
        <span>{last >= first ? "trending up" : "trending down"}</span>
      </div>
    </div>
  );
}