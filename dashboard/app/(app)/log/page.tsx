import { audit } from "../../lib/api";
import LogPanel from "../../components/LogPanel";

export const dynamic = "force-dynamic";

export default async function Log() {
  const data = await audit().catch(() => ({ rows: [] }));
  return (
    <div>
      <div className="pagehead">
        <div>
          <div className="crumb">Agent Log</div>
          <h1>Everything the agent has been doing.</h1>
        </div>
        <a href="/today" className="btn">← today</a>
      </div>
      <LogPanel initial={data.rows} />
    </div>
  );
}