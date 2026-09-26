export default function StatCard({
  label,
  value,
  sub,
  tone,
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "up" | "down" | "warn" | "accent";
}) {
  return (
    <div className="card big">
      <h2>{label}</h2>
      <div className={`bigval mono ${tone === "up" ? "up" : tone === "down" ? "down" : tone === "warn" ? "warn" : tone === "accent" ? "accent-badge" : ""}`}>
        {value}
      </div>
      {sub && <div className="sub">{sub}</div>}
    </div>
  );
}