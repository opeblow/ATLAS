"use client";

import { useEffect, useState } from "react";
import { audit } from "../../lib/api";
import LogPanel from "../../components/LogPanel";

// Client-rendered for Cloudflare static export; see the note in money/page.tsx.
export default function Log() {
  const [rows, setRows] = useState<any[]>([]);

  useEffect(() => {
    audit(40)
      .then((d) => setRows(d?.rows ?? []))
      .catch(() => setRows([]));
  }, []);

  return (
    <div>
      <div className="pagehead">
        <div>
          <div className="crumb">Agent Log</div>
          <h1>Everything the agent has been doing.</h1>
        </div>
        <a href="/today" className="btn">← today</a>
      </div>
      <LogPanel initial={rows} />
    </div>
  );
}