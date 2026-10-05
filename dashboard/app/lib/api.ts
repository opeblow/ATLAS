import { getAccessToken, getAuthenticatedUserId } from "./auth";
export { authenticatedUserId as DEFAULT_USER } from "./auth";

const ENV = process.env.NEXT_PUBLIC_ATLAS_URL || "";

// In a deployed build the dashboard is static (Cloudflare Pages) and the backend
// is a single public origin (atlas-edge on Render), so every call goes through
// one base URL. In local dev the four services run on separate ports.
const FIN = process.env.NEXT_PUBLIC_FINANCE_URL || (ENV ? `${ENV}/finance` : "http://127.0.0.1:8001");
const SCH = process.env.NEXT_PUBLIC_SCHEDULING_URL || (ENV ? `${ENV}/schedule` : "http://127.0.0.1:8002");
const RSK = process.env.NEXT_PUBLIC_RISK_URL || (ENV ? `${ENV}/risk` : "http://127.0.0.1:8000");
const MCP = process.env.NEXT_PUBLIC_MCP_URL || (ENV ? `${ENV}/mcp` : "http://127.0.0.1:8003");

export const currentUserId = () => getAuthenticatedUserId();

function authenticatedHeaders(contentType = false): HeadersInit {
  const token = getAccessToken();
  if (!token) throw new Error("Sign in to use ATLAS.");
  return {
    ...(contentType ? { "Content-Type": "application/json" } : {}),
    Authorization: `Bearer ${token}`,
  };
}

// In-flight request deduplication map and micro-cache for zero-latency UI re-renders
const inflightRequests = new Map<string, Promise<any>>();
const cacheStore = new Map<string, { data: any; expiry: number }>();
const CACHE_TTL_MS = 1500; // 1.5s micro-cache

// Every backend call is bounded: a hung socket otherwise pins the request
// forever and leaks a pending promise on each render pass.
const REQUEST_TIMEOUT_MS = 12000;

async function apiFetch(url: string, init: RequestInit = {}): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err) {
    if ((err as Error)?.name === "AbortError") {
      throw new Error("The ATLAS service did not respond. Try again in a moment.");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

// Backend error bodies can carry driver messages, SQL fragments, or stack
// traces. Surface the status to the user and keep the detail in the console
// for debugging rather than rendering it into the DOM.
async function readError(res: Response): Promise<Error> {
  let detail = "";
  try {
    detail = (await res.text()).slice(0, 500);
  } catch {
    /* body already consumed or unreadable */
  }
  if (detail) console.error(`ATLAS ${res.status} ${detail}`);
  if (res.status === 401 || res.status === 403) return new Error("Your session has expired. Sign in again.");
  if (res.status === 429) return new Error("Too many requests. Give it a moment.");
  if (res.status >= 500) return new Error("The ATLAS service is temporarily unavailable.");
  return new Error(`Request failed (${res.status}).`);
}

export async function jget(url: string, useCache = true): Promise<any> {
  const now = Date.now();
  if (useCache && cacheStore.has(url)) {
    const cached = cacheStore.get(url)!;
    if (now < cached.expiry) {
      return cached.data;
    }
  }

  if (inflightRequests.has(url)) {
    return inflightRequests.get(url);
  }

  const promise = (async () => {
    try {
      const r = await apiFetch(url, { headers: authenticatedHeaders(), cache: "no-store" });
      if (!r.ok) throw await readError(r);
      const data = await r.json();
      if (useCache) {
        cacheStore.set(url, { data, expiry: Date.now() + CACHE_TTL_MS });
      }
      return data;
    } finally {
      inflightRequests.delete(url);
    }
  })();

  inflightRequests.set(url, promise);
  return promise;
}

export async function jpost(url: string, body: any): Promise<any> {
  // Clear cache on mutations
  cacheStore.clear();
  const r = await apiFetch(url, {
    method: "POST",
    headers: authenticatedHeaders(true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) throw await readError(r);
  return r.json();
}

export async function jpatch(url: string, body: any): Promise<any> {
  cacheStore.clear();
  const r = await apiFetch(url, {
    method: "PATCH",
    headers: authenticatedHeaders(true),
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!r.ok) throw await readError(r);
  return r.json();
}

export const todayIso = () => new Date().toISOString().slice(0, 10);

export const brief = (user = currentUserId()) => jget(`${FIN}/users/${user}/brief`);
export const timeBrief = (user = currentUserId(), day = todayIso()) => jget(`${SCH}/users/${user}/brief/${day}`);
export const balance = (user = currentUserId()) => jget(`${FIN}/users/${user}/balance`);
export const risk = (user = currentUserId()) => jget(`${FIN}/users/${user}/risk?window=30d`);
export const trend = (user = currentUserId()) => jget(`${FIN}/users/${user}/risk/trend`);
export const transactions = (user = currentUserId()) => jget(`${FIN}/users/${user}/transactions`);
export const schedule = (user = currentUserId(), status = "committed") => jget(`${SCH}/users/${user}/schedule?status=${status}`);
export const deadlines = (user = currentUserId()) => jget(`${SCH}/users/${user}/deadlines`);
export const audit = (limit = 40) => jget(`${FIN}/audit/tool_calls?limit=${limit}`);

// Which capabilities are live vs simulated. Lets the demo state its own
// limitations instead of implying every external call is real.
export const capabilities = () => jget(`${ENV}/api/capabilities`);

export type AskReply = {
  answer?: string;
  tool?: string;
  front_door?: string;
  simulated?: boolean;
  note?: string;
  tool_output?: any;
  error?: string;
};

// Single natural-language turn through the orchestrator. Identical to what the
// MCP tool surface exposes; falls back to the rule-based router when Bedrock
// credentials are absent, and the reply says so via `simulated`.
export const ask = (utterance: string, user = currentUserId()) =>
  jpost(`${ENV}/api/ask`, { utterance, user_id: user });

export const postTransaction = (user = currentUserId(), amount_ngn: number, category = "general", idempotency_key?: string) =>
  jpost(`${FIN}/transactions`, {
    user_id: user,
    amount_ngn,
    category,
    source: "dashboard_ui",
    idempotency_key,
  });

export const postDeadline = (user = currentUserId(), title: string, due_at: string, weight = 1.0) =>
  jpost(`${SCH}/deadlines`, {
    user_id: user,
    title,
    due_at,
    weight,
  });

export const patchBlock = (block_id: string, updates: { start_at?: string; end_at?: string; status?: string }) =>
  jpatch(`${SCH}/schedule/block/${block_id}`, updates);

export async function checkServicesHealth() {
  const services = [
    { name: "risk-model", url: `${RSK}/health`, port: 8000 },
    { name: "finance", url: `${FIN}/health`, port: 8001 },
    { name: "schedule", url: `${SCH}/health`, port: 8002 },
    { name: "mcp", url: `${MCP}/health`, port: 8003 },
  ];

  const results = await Promise.all(
    services.map(async (s) => {
      // Health probes are unauthenticated by design; bounded so a dead service
      // cannot hang the settings panel forever.
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 4000);
      try {
        const res = await fetch(s.url, { cache: "no-store", signal: controller.signal });
        return { name: s.name, port: s.port, online: res.ok };
      } catch {
        return { name: s.name, port: s.port, online: false };
      } finally {
        clearTimeout(timer);
      }
    })
  );

  return results;
}

export function ngn(n: number | null | undefined): string {
  return `₦${Math.abs(Number(n ?? 0)).toLocaleString("en-NG")}`;
}