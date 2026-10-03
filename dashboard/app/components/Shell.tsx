"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useRef } from "react";
import { ask, capabilities, checkServicesHealth, DEFAULT_USER, type AskReply } from "../lib/api";

const ATLAS_URL = process.env.NEXT_PUBLIC_ATLAS_URL || "";
import {
  IconHome,
  IconWallet,
  IconCalendar,
  IconTarget,
  IconChart,
  IconSettings,
  IconSearch,
  IconSun,
  IconMoon,
  IconMic,
  IconUser,
  IconClose,
} from "./Icons";

const NAV_ITEMS = [
  { href: "/dashboard", Icon: IconHome, label: "Home" },
  { href: "/money", Icon: IconWallet, label: "Finances" },
  { href: "/time", Icon: IconCalendar, label: "Schedule" },
  { href: "/dashboard#goals", Icon: IconTarget, label: "Goals" },
  { href: "/log", Icon: IconChart, label: "Reports" },
  { href: "#settings", Icon: IconSettings, label: "Settings" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [voiceQuery, setVoiceQuery] = useState("");
  const [isListening, setIsListening] = useState(false);
  const [isAsking, setIsAsking] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [activeUser, setActiveUser] = useState(DEFAULT_USER);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const settingsDialogRef = useRef<HTMLDivElement>(null);
  const [caps, setCaps] = useState<Record<string, { mode: string; reason?: string }> | null>(null);
  const [serviceHealth, setServiceHealth] = useState<Array<{ name: string; port: number; online: boolean }>>([
    { name: "risk-model", port: 8000, online: true },
    { name: "finance", port: 8001, online: true },
    { name: "schedule", port: 8002, online: true },
    { name: "mcp", port: 8003, online: true },
  ]);

  // Which capabilities are live vs simulated, so the demo never implies a
  // real Bedrock/AWS call happened.
  useEffect(() => {
    if (!ATLAS_URL) return;
    capabilities().then(setCaps).catch(() => setCaps(null));
  }, []);

  // Poll service health
  useEffect(() => {
    async function updateHealth() {
      const statuses = await checkServicesHealth();
      setServiceHealth(statuses);
    }
    updateHealth();
    const interval = setInterval(updateHealth, 10000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (!showSettingsModal) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = settingsDialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), a[href]'
    );
    focusable?.[0]?.focus();

    const handleDialogKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setShowSettingsModal(false);
        return;
      }
      if (event.key !== "Tab" || !focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    window.addEventListener("keydown", handleDialogKeyDown);
    return () => {
      window.removeEventListener("keydown", handleDialogKeyDown);
      previousFocus?.focus();
    };
  }, [showSettingsModal]);

  // Theme toggle
  const toggleTheme = () => {
    setIsDarkMode((prev) => {
      const next = !prev;
      if (next) {
        document.documentElement.classList.add("dark-mode");
      } else {
        document.documentElement.classList.remove("dark-mode");
      }
      return next;
    });
  };

  const handleMicClick = () => {
    setIsListening(!isListening);
    if (!isListening) {
      setVoiceQuery("Listening...");
      setTimeout(() => {
        setVoiceQuery("What's my risk score and daily brief?");
      }, 1500);
    }
  };

  // Real turn through the orchestrator (POST /api/ask). Shows whatever the
  // backend actually returned, including its simulated/not-simulated label, so
  // the widget can't imply a live Bedrock call when there isn't one.
  const [reply, setReply] = useState<AskReply | null>(null);

  const sendVoiceQuery = async () => {
    const utterance = voiceQuery.trim();
    if (!utterance || isAsking) return;
    setIsAsking(true);
    setReply(null);
    try {
      setReply(await ask(utterance, activeUser));
    } catch (err: any) {
      setReply({ error: err?.message || "could not reach the ATLAS backend" });
    } finally {
      setIsAsking(false);
      setIsListening(false);
    }
  };

  return (
    <div className={`dashboard-layout ${isDarkMode ? "dark-theme" : ""}`}>
      {/* ---------------- 1. LEFT SIDEBAR ---------------- */}
      <aside className="dash-sidebar">
        <div className="dash-sidebar-top">
          <Link href="/" className="brand-logo" style={{ padding: "0 8px" }}>
            <span className="brand-dot" />
            <span>ATLAS</span>
          </Link>

          <nav className="dash-nav-list" aria-label="Primary navigation">
            {NAV_ITEMS.map((item) => {
              const isActive =
                pathname === item.href ||
                (item.href === "/dashboard" && (pathname === "/today" || pathname === "/dashboard"));

              if (item.label === "Settings") {
                return (
                  <button
                    key={item.label}
                    onClick={() => setShowSettingsModal(true)}
                    className="dash-nav-item"
                    type="button"
                    aria-haspopup="dialog"
                  >
                    <span className="dash-nav-icon"><item.Icon size={18} /></span>
                    <span>{item.label}</span>
                  </button>
                );
              }

              return (
                <Link
                  key={item.label}
                  href={item.href}
                  className={`dash-nav-item ${isActive ? "active" : ""}`}
                  aria-current={isActive ? "page" : undefined}
                >
                  <span className="dash-nav-icon"><item.Icon size={18} /></span>
                  <span>{item.label}</span>
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Real Service Health Strip */}
        <div style={{ paddingTop: 16, borderTop: "1px solid #f1f5f9" }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: "#94a3b8", marginBottom: 8, padding: "0 8px", letterSpacing: "0.05em" }}>
            SERVICE HEALTH
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6, padding: "0 8px" }}>
            {serviceHealth.map((s) => (
              <div
                key={s.name}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  fontSize: 11,
                  padding: "4px 8px",
                  borderRadius: 6,
                  background: s.online ? "rgba(16, 185, 129, 0.08)" : "rgba(239, 68, 68, 0.08)",
                  border: `1px solid ${s.online ? "rgba(16, 185, 129, 0.2)" : "rgba(239, 68, 68, 0.2)"}`,
                }}
              >
                <span style={{ color: s.online ? "#10b981" : "#ef4444", fontWeight: 600 }}>
                  ● {s.name}
                </span>
                <span style={{ color: "#94a3b8", fontSize: 10 }}>:{s.port}</span>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ---------------- 2. MAIN CONTAINER ---------------- */}
      <div className="dash-main-container">
        {/* Top Navbar */}
        <header className="dash-topnav">
          <label className="dash-search-box">
            <IconSearch size={16} color="#94a3b8" />
            <input
              type="text"
              className="dash-search-input"
              aria-label="Search finances, schedules, and transactions"
              placeholder="Search finances, schedules, transactions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </label>

          <div className="dash-topnav-right">
            <div className="date-badge-pill">
              <span>{new Date().toLocaleDateString("en-NG", { weekday: "long", day: "numeric", month: "long" })}</span>
              <IconCalendar size={14} color="#64748b" />
            </div>

            {/* User Switcher */}
            <select
              value={activeUser}
              onChange={(e) => setActiveUser(e.target.value)}
              aria-label="Active demo user"
              style={{
                fontSize: 12,
                fontWeight: 600,
                border: "1px solid #e2e8f0",
                borderRadius: 99,
                padding: "4px 12px",
                background: "#ffffff",
                color: "#0f172a",
                cursor: "pointer",
              }}
            >
              <option value="u_demo">u_demo</option>
              <option value="u_alex">u_alex</option>
              <option value="u_sarah">u_sarah</option>
            </select>

            <button
              className="icon-btn-circle"
              onClick={toggleTheme}
              title={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
              aria-label={isDarkMode ? "Switch to light mode" : "Switch to dark mode"}
              aria-pressed={isDarkMode}
            >
              {isDarkMode ? <IconMoon size={18} /> : <IconSun size={18} />}
            </button>

            <div className="user-profile-badge">
              <img
                src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80"
                alt=""
                className="user-avatar-img"
              />
              <span className="user-name-text">Opeyemi</span>
              <span style={{ fontSize: 10, color: "#94a3b8" }}>▾</span>
            </div>
          </div>
        </header>

        {/* Content Body */}
        <main style={{ flex: 1 }}>{children}</main>

        {/* ---------------- 3. FLOATING VOICE ASSISTANT WIDGET ---------------- */}
        <div className="floating-voice-widget">
          <button
            className="voice-widget-mic"
            onClick={handleMicClick}
            title="Ask Atlas by voice"
            aria-label={isListening ? "Stop voice input" : "Start voice input"}
            aria-pressed={isListening}
            style={{ background: isListening ? "#10b981" : "#ea580c" }}
          >
            <IconMic size={18} color="#ffffff" />
          </button>
          <input
            type="text"
            className="voice-widget-input"
            aria-label="Ask ATLAS a question"
            placeholder="Ask Atlas anything..."
            value={voiceQuery}
            onChange={(e) => setVoiceQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") sendVoiceQuery();
            }}
          />
          {isListening && (
            <div className="soundwave-bars" style={{ height: 12, marginRight: 8 }}>
              <span className="soundwave-bar" style={{ background: "#10b981" }} />
              <span className="soundwave-bar" style={{ background: "#10b981" }} />
              <span className="soundwave-bar" style={{ background: "#10b981" }} />
            </div>
          )}
          <button
            onClick={sendVoiceQuery}
            disabled={isAsking || !voiceQuery.trim()}
            className="voice-widget-send"
            title="Send"
            aria-label="Send question to ATLAS"
            style={{ opacity: isAsking || !voiceQuery.trim() ? 0.4 : 1 }}
          >
            {isAsking ? "..." : "Send"}
          </button>
        </div>

        {/* Orchestrator reply, echoed with its live/simulated label */}
        {reply && (
          <div className="voice-widget-reply" role="status" aria-live="polite" style={{ right: 24, bottom: 92, maxWidth: 460 }}>
            <div className="voice-widget-reply-head">
              <span>{reply.error ? "Error" : reply.tool || "Atlas"}</span>
              {reply.simulated && !reply.error && <span className="badge-sim">simulated</span>}
            </div>
            <div className="voice-widget-reply-body">
              {reply.error || reply.answer || "No response."}
            </div>
          </div>
        )}
      </div>

      {/* Settings Modal */}
      {showSettingsModal && (
        <div className="modal-overlay" onClick={() => setShowSettingsModal(false)}>
          <div
            ref={settingsDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="atlas-settings-title"
            className="shell-settings-dialog"
            onKeyDown={(event) => {
              if (event.key === "Escape") setShowSettingsModal(false);
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
              <h3 id="atlas-settings-title" style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "#0f172a", display: "flex", alignItems: "center", gap: 8 }}>
                <IconSettings size={22} color="#ea580c" /> ATLAS Settings
              </h3>
              <button type="button" aria-label="Close settings" onClick={() => setShowSettingsModal(false)} style={{ border: "none", background: "none", fontSize: 18, cursor: "pointer" }}>
                <IconClose size={18} color="#64748b" />
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 16, fontSize: 14 }}>
              <div>
                <label style={{ display: "block", fontWeight: 600, marginBottom: 4, color: "#475569" }}>Active User ID</label>
                <input type="text" value={activeUser} readOnly style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e2e8f0", background: "#f8fafc" }} />
              </div>
              <div>
                <label style={{ display: "block", fontWeight: 600, marginBottom: 4, color: "#475569" }}>Backend origin</label>
                <input
                  type="text"
                  value={ATLAS_URL || "local stack (4 ports)"}
                  readOnly
                  style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e2e8f0", background: "#f8fafc" }}
                />
              </div>
              {caps &&
                Object.entries(caps).map(([name, c]) => (
                  <div key={name}>
                    <label style={{ display: "block", fontWeight: 600, marginBottom: 4, color: "#475569" }}>
                      {name.replace(/_/g, " ")}{" "}
                      <span
                        className="mono"
                        style={{
                          fontSize: 11,
                          color: c.mode === "live" || c.mode === "trained" ? "#10b981" : "#d97706",
                        }}
                      >
                        {c.mode}
                      </span>
                    </label>
                    {c.reason && (
                      <p className="muted" style={{ fontSize: 12, margin: 0 }}>{c.reason}</p>
                    )}
                  </div>
                ))}
              <button
                className="btn-orange-pill"
                onClick={() => setShowSettingsModal(false)}
                style={{ marginTop: 10 }}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}