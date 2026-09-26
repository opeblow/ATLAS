import { deadlines, schedule } from "../../lib/api";
import Planner from "../../components/Planner";

export const dynamic = "force-dynamic";

export default async function Time() {
  const [dl, sc] = await Promise.all([deadlines().catch(() => null), schedule().catch(() => null)]);
  const deadlineRows = dl?.deadlines ?? [];
  const blocks = sc?.blocks ?? [];

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
        {blocks.length ? (
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
                  <td className="mono faint">{b.start_at.slice(11, 16)}–{b.end_at.slice(11, 16)}</td>
                  <td>{b.title}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted" style={{ fontSize: 13, margin: 0 }}>Nothing committed yet — generate a plan below.</p>
        )}
      </div>

      <Planner deadlines={deadlineRows} />
    </div>
  );
}