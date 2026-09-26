"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { checkServicesHealth, DEFAULT_USER } from "../lib/api";
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
  const [searchQuery, setSearchQuery] = useState("");
  const [isDarkMode, setIsDarkMode] = useState(false);
  const [activeUser, setActiveUser] = useState(DEFAULT_USER);
  const [showSettingsModal, setShowSettingsModal] = useState(false);
  const [serviceHealth, setServiceHealth] = useState<Array<{ name: string; port: number; online: boolean }>>([
    { name: "risk-model", port: 8000, online: true },
    { name: "finance", port: 8001, online: true },
    { name: "schedule", port: 8002, online: true },
    { name: "mcp", port: 8003, online: true },
  ]);

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

  return (
    <div className={`dashboard-layout ${isDarkMode ? "dark-theme" : ""}`}>
      {/* ---------------- 1. LEFT SIDEBAR ---------------- */}
      <aside className="dash-sidebar">
        <div className="dash-sidebar-top">
          <Link href="/" className="brand-logo" style={{ padding: "0 8px" }}>
            <span className="brand-dot" />
            <span>ATLAS</span>
          </Link>

          <nav className="dash-nav-list">
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
          <div className="dash-search-box">
            <IconSearch size={16} color="#94a3b8" />
            <input
              type="text"
              className="dash-search-input"
              placeholder="Search finances, schedules, transactions..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          <div className="dash-topnav-right">
            <div className="date-badge-pill">
              <span>{new Date().toLocaleDateString("en-NG", { weekday: "long", day: "numeric", month: "long" })}</span>
              <IconCalendar size={14} color="#64748b" />
            </div>

            {/* User Switcher */}
            <select
              value={activeUser}
              onChange={(e) => setActiveUser(e.target.value)}
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
            >
              {isDarkMode ? <IconMoon size={18} /> : <IconSun size={18} />}
            </button>

            <div className="user-profile-badge">
              <img
                src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80"
                alt="Opeyemi"
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
            style={{ background: isListening ? "#10b981" : "#ea580c" }}
          >
            <IconMic size={18} color="#ffffff" />
          </button>
          <input
            type="text"
            className="voice-widget-input"
            placeholder="Ask Atlas anything..."
            value={voiceQuery}
            onChange={(e) => setVoiceQuery(e.target.value)}
          />
          {isListening && (
            <div className="soundwave-bars" style={{ height: 12, marginRight: 8 }}>
              <span className="soundwave-bar" style={{ background: "#10b981" }} />
              <span className="soundwave-bar" style={{ background: "#10b981" }} />
              <span className="soundwave-bar" style={{ background: "#10b981" }} />
            </div>
          )}
        </div>
      </div>

      {/* Settings Modal */}
      {showSettingsModal && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(15, 23, 42, 0.6)",
            backdropFilter: "blur(4px)",
            zIndex: 100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          onClick={() => setShowSettingsModal(false)}
        >
          <div
            style={{
              background: "#ffffff",
              borderRadius: 20,
              padding: 32,
              maxWidth: 480,
              width: "90%",
              boxShadow: "0 25px 50px -12px rgba(0,0,0,0.25)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
              <h3 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "#0f172a", display: "flex", alignItems: "center", gap: 8 }}>
                <IconSettings size={22} color="#ea580c" /> ATLAS Settings
              </h3>
              <button onClick={() => setShowSettingsModal(false)} style={{ border: "none", background: "none", fontSize: 18, cursor: "pointer" }}>
                <IconClose size={18} color="#64748b" />
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 16, fontSize: 14 }}>
              <div>
                <label style={{ display: "block", fontWeight: 600, marginBottom: 4, color: "#475569" }}>Active User ID</label>
                <input type="text" value={activeUser} readOnly style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e2e8f0", background: "#f8fafc" }} />
              </div>
              <div>
                <label style={{ display: "block", fontWeight: 600, marginBottom: 4, color: "#475569" }}>Finance Service API</label>
                <input type="text" value="http://127.0.0.1:8001" readOnly style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e2e8f0", background: "#f8fafc" }} />
              </div>
              <div>
                <label style={{ display: "block", fontWeight: 600, marginBottom: 4, color: "#475569" }}>Scheduling Service API</label>
                <input type="text" value="http://127.0.0.1:8002" readOnly style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e2e8f0", background: "#f8fafc" }} />
              </div>
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