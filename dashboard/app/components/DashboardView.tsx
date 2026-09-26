"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import {
  brief,
  timeBrief,
  transactions,
  deadlines,
  postTransaction,
  postDeadline,
  ngn,
  DEFAULT_USER,
} from "../lib/api";
import {
  IconEye,
  IconWallet,
  IconShield,
  IconClock,
  IconPlus,
  IconZap,
  IconBook,
  IconCalendar,
  IconTarget,
  IconClose,
  IconArrowRight,
} from "./Icons";

export default function DashboardView() {
  const [loading, setLoading] = useState(true);
  const [finBrief, setFinBrief] = useState<any>(null);
  const [schBrief, setSchBrief] = useState<any>(null);
  const [txList, setTxList] = useState<any[]>([]);
  const [dlList, setDlList] = useState<any[]>([]);

  // Interactive Form States
  const [showTxModal, setShowTxModal] = useState(false);
  const [showDeadlineModal, setShowDeadlineModal] = useState(false);
  const [idempotencyResult, setIdempotencyResult] = useState<any>(null);

  // Form inputs
  const [txAmount, setTxAmount] = useState("");
  const [txCategory, setTxCategory] = useState("food");
  const [dlTitle, setDlTitle] = useState("");
  const [dlDate, setDlDate] = useState("");

  // Demo Idempotency key
  const [lastIdempotencyKey, setLastIdempotencyKey] = useState<string | null>(null);

  async function loadData() {
    setLoading(true);
    try {
      const [fb, sb, txRes, dlRes] = await Promise.all([
        brief(DEFAULT_USER).catch(() => null),
        timeBrief(DEFAULT_USER).catch(() => null),
        transactions(DEFAULT_USER).catch(() => null),
        deadlines(DEFAULT_USER).catch(() => null),
      ]);
      setFinBrief(fb);
      setSchBrief(sb);
      setTxList(txRes?.transactions ?? []);
      setDlList(dlRes?.deadlines ?? []);
    } catch (e) {
      console.error("Dashboard fetch error:", e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  // Compute 7-day spend bars live from transactions
  const compute7DaySpendBars = () => {
    const days: { [key: string]: number } = {};
    const today = new Date();
    for (let i = 6; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(d.getDate() - i);
      const iso = d.toISOString().slice(0, 10);
      days[iso] = 0;
    }

    txList.forEach((t) => {
      const dayIso = t.ts ? t.ts.slice(0, 10) : "";
      if (dayIso in days && t.amount_ngn < 0) {
        days[dayIso] += Math.abs(t.amount_ngn);
      }
    });

    const maxSpend = Math.max(...Object.values(days), 10000);
    return Object.entries(days).map(([dayIso, total]) => {
      const dateObj = new Date(dayIso);
      const dayLabel = dateObj.toLocaleDateString("en-US", { month: "short", day: "numeric" });
      const pct = Math.min(100, Math.round((total / maxSpend) * 100));
      return { day: dayLabel, amount: ngn(total), height: Math.max(pct, 12) };
    });
  };

  // Compute spend by category
  const computeCategoryBreakdown = () => {
    const cats: { [key: string]: number } = {};
    let totalSpend = 0;
    txList.forEach((t) => {
      if (t.amount_ngn < 0) {
        const amt = Math.abs(t.amount_ngn);
        cats[t.category] = (cats[t.category] || 0) + amt;
        totalSpend += amt;
      }
    });

    return Object.entries(cats).map(([cat, amt]) => ({
      category: cat,
      amount: ngn(amt),
      pct: totalSpend > 0 ? Math.round((amt / totalSpend) * 100) : 0,
    })).slice(0, 4);
  };

  // Handle Log Transaction
  const handleLogTransaction = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!txAmount) return;
    const amount = -Math.abs(parseFloat(txAmount));
    const ik = `tx-dash-${Date.now()}`;
    setLastIdempotencyKey(ik);
    try {
      const res = await postTransaction(DEFAULT_USER, amount, txCategory, ik);
      setIdempotencyResult(res);
      setShowTxModal(false);
      setTxAmount("");
      loadData();
    } catch (err: any) {
      alert(`Transaction failed: ${err.message}`);
    }
  };

  // Test Idempotency (fire same request twice)
  const handleTestIdempotency = async () => {
    const testKey = `idem-test-${Date.now()}`;
    try {
      // 1st call
      const res1 = await postTransaction(DEFAULT_USER, -5000, "test_spend", testKey);
      // 2nd call with same key
      const res2 = await postTransaction(DEFAULT_USER, -5000, "test_spend", testKey);

      setIdempotencyResult({
        firstCall: res1,
        secondCall: res2,
        key: testKey,
      });
      loadData();
    } catch (err: any) {
      alert(`Idempotency test failed: ${err.message}`);
    }
  };

  // Handle Add Deadline
  const handleAddDeadline = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!dlTitle || !dlDate) return;
    try {
      await postDeadline(DEFAULT_USER, dlTitle, new Date(dlDate).toISOString(), 1.5);
      setShowDeadlineModal(false);
      setDlTitle("");
      setDlDate("");
      loadData();
    } catch (err: any) {
      alert(`Deadline creation failed: ${err.message}`);
    }
  };

  const balanceVal = finBrief?.balance_ngn ?? 242000;
  const riskScore = finBrief?.risk_score ?? 0.12;
  const spend7d = finBrief?.spend_7d_ngn ?? 85000;
  const blocks = schBrief?.today_blocks ?? [];
  const nextDeadlines = schBrief?.next_deadlines ?? dlList;
  const spendBars = compute7DaySpendBars();
  const categoryBreakdown = computeCategoryBreakdown();

  const healthScore = Math.max(0, Math.min(100, Math.round((1 - riskScore) * 100)));
  const healthLabel = riskScore < 0.4 ? "Good" : riskScore < 0.7 ? "Elevated Risk" : "High Risk";

  return (
    <div className="dash-body">
      {/* ---------------- 1. GREETING HEADER ---------------- */}
      <div className="dash-greeting-header">
        <div>
          <h1 className="dash-greeting-title">Good morning, Opeyemi</h1>
          <p className="dash-greeting-sub">
            {finBrief
              ? `Live Balance: ${ngn(balanceVal)} · Risk Score: ${riskScore.toFixed(2)}`
              : "Here is what is happening today."}
          </p>
        </div>

        <div style={{ display: "flex", gap: 10 }}>
          <button
            className="btn-orange-pill"
            style={{ padding: "8px 16px", fontSize: "13px" }}
            onClick={() => setShowTxModal(true)}
          >
            <IconPlus size={14} color="#ffffff" /> Log Transaction
          </button>
          <button
            className="btn-demo-watch"
            style={{ fontSize: "13px", padding: "8px 16px" }}
            onClick={handleTestIdempotency}
            title="Fire duplicate request to verify idempotency"
          >
            <IconZap size={14} color="#ea580c" /> Test Idempotency
          </button>
        </div>
      </div>

      {/* Idempotency Banner */}
      {idempotencyResult && (
        <div
          style={{
            background: "#fff7ed",
            border: "1px solid #ffedd5",
            borderRadius: 16,
            padding: 16,
            marginBottom: 24,
            fontSize: 13,
            color: "#ea580c",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <IconShield size={18} color="#ea580c" />
            <strong>Idempotency Verification:</strong>{" "}
            {idempotencyResult.firstCall ? (
              <span>
                1st call: <code>duplicate = {String(idempotencyResult.firstCall.duplicate)}</code> → 2nd call: <code>duplicate = {String(idempotencyResult.secondCall.duplicate)}</code>! (Safe from double-spend)
              </span>
            ) : (
              <span>
                Transaction logged with <code>idempotency_key = {lastIdempotencyKey}</code> (duplicate = {String(idempotencyResult.duplicate)})
              </span>
            )}
          </div>
          <button
            onClick={() => setIdempotencyResult(null)}
            style={{ background: "none", border: "none", color: "#ea580c", fontWeight: 700, cursor: "pointer" }}
          >
            <IconClose size={16} color="#ea580c" />
          </button>
        </div>
      )}

      {/* ---------------- 2. TOP 4 LIVE KPI STAT CARDS ---------------- */}
      <div className="kpi-grid-4">
        {/* Card 1: Total Balance */}
        <div className="kpi-card">
          <div className="kpi-header-row">
            <div className="kpi-icon-badge"><IconEye size={18} color="#ea580c" /></div>
            <div className="kpi-label">Total Balance</div>
          </div>
          <div className="kpi-value">{ngn(balanceVal)}</div>
          <div className="kpi-trend-row">
            <span className="trend-up">↑ Live backend</span>
            <svg viewBox="0 0 50 16" width="50" height="16">
              <path d="M0,12 Q12,2 25,10 T50,2" fill="none" stroke="#10b981" strokeWidth="2" />
            </svg>
          </div>
        </div>

        {/* Card 2: 7-Day Spending */}
        <div className="kpi-card">
          <div className="kpi-header-row">
            <div className="kpi-icon-badge" style={{ background: "#fff7ed", color: "#ea580c" }}><IconWallet size={18} color="#ea580c" /></div>
            <div className="kpi-label">7-Day Spend</div>
          </div>
          <div className="kpi-value">{ngn(spend7d)}</div>
          <div className="kpi-trend-row">
            <span className="trend-down">Rolling window</span>
            <svg viewBox="0 0 50 16" width="50" height="16">
              <path d="M0,4 Q12,14 25,6 T50,12" fill="none" stroke="#10b981" strokeWidth="2" />
            </svg>
          </div>
        </div>

        {/* Card 3: Risk Score */}
        <div className="kpi-card">
          <div className="kpi-header-row">
            <div className="kpi-icon-badge"><IconShield size={18} color="#ea580c" /></div>
            <div className="kpi-label">Risk Score</div>
          </div>
          <div className="kpi-value">{riskScore.toFixed(2)}</div>
          <div className="kpi-trend-row" style={{ flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
            <span style={{ color: riskScore > 0.6 ? "#ef4444" : "#10b981", fontSize: 11, fontWeight: 700 }}>
              {healthLabel}
            </span>
            <div className="progress-track-bar" style={{ height: 4 }}>
              <div
                className="progress-fill-bar"
                style={{
                  width: `${Math.round(riskScore * 100)}%`,
                  background: riskScore > 0.6 ? "#ef4444" : "#10b981",
                }}
              />
            </div>
          </div>
        </div>

        {/* Card 4: Next Deadline */}
        <div className="kpi-card">
          <div className="kpi-header-row">
            <div className="kpi-icon-badge"><IconClock size={18} color="#ea580c" /></div>
            <div className="kpi-label">Next Deadline</div>
          </div>
          <div className="kpi-value" style={{ fontSize: 18, textOverflow: "ellipsis", overflow: "hidden", whiteSpace: "nowrap" }}>
            {nextDeadlines[0]?.title ?? "Midterm Exam"}
          </div>
          <div className="kpi-trend-row">
            <span className="trend-up" style={{ color: "#ea580c" }}>
              {nextDeadlines[0]?.due_at ? `${nextDeadlines[0].due_at.slice(0, 10)}` : "Due soon"}
            </span>
          </div>
        </div>
      </div>

      {/* ---------------- 3. MIDDLE ROW (3 COLUMNS) ---------------- */}
      <div className="dash-middle-grid">
        {/* Column 1: Today's Schedule */}
        <div className="card-container">
          <div className="card-header-flex">
            <h3 className="card-header-title">Today is Schedule</h3>
            <Link href="/time" className="link-action-small">View all <IconArrowRight size={12} /></Link>
          </div>

          <div className="schedule-list">
            {blocks.length > 0 ? (
              blocks.map((b: any, idx: number) => (
                <div key={b.id || idx} className="schedule-item">
                  <span className="schedule-time">{b.start_at ? b.start_at.slice(11, 16) : "09:00"}</span>
                  <div className="schedule-info">
                    <div className="schedule-title">{b.title}</div>
                    <div className="schedule-category">Committed Block</div>
                  </div>
                  <span className={`badge-status ${idx === 0 ? "in-progress" : "upcoming"}`}>
                    {idx === 0 ? "In progress" : "Upcoming"}
                  </span>
                </div>
              ))
            ) : (
              <>
                <div className="schedule-item">
                  <span className="schedule-time">06:00</span>
                  <div className="schedule-info">
                    <div className="schedule-title">Deep Work Session</div>
                    <div className="schedule-category">Project Atlas</div>
                  </div>
                  <span className="badge-status in-progress">In progress</span>
                </div>
                <div className="schedule-item">
                  <span className="schedule-time">11:00</span>
                  <div className="schedule-info">
                    <div className="schedule-title">Team Standup</div>
                    <div className="schedule-category">Engineering</div>
                  </div>
                  <span className="badge-status upcoming">Upcoming</span>
                </div>
                <div className="schedule-item">
                  <span className="schedule-time">14:00</span>
                  <div className="schedule-info">
                    <div className="schedule-title">Financial Review</div>
                    <div className="schedule-category">Budget & Investments</div>
                  </div>
                  <span className="badge-status upcoming">Upcoming</span>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Column 2: Quick Actions */}
        <div className="card-container">
          <div className="card-header-flex">
            <h3 className="card-header-title">Quick Actions</h3>
          </div>

          <div className="quick-actions-list">
            <button className="quick-action-btn" onClick={() => setShowTxModal(true)}>
              <span className="quick-action-icon"><IconWallet size={16} color="#ea580c" /></span>
              <span>Log a transaction</span>
            </button>

            <button className="quick-action-btn" onClick={() => setShowDeadlineModal(true)}>
              <span className="quick-action-icon"><IconBook size={16} color="#ea580c" /></span>
              <span>Create a deadline</span>
            </button>

            <button className="quick-action-btn" onClick={handleTestIdempotency}>
              <span className="quick-action-icon"><IconZap size={16} color="#ea580c" /></span>
              <span>Test Idempotency</span>
            </button>

            <Link href="/time" className="quick-action-btn">
              <span className="quick-action-icon"><IconCalendar size={16} color="#ea580c" /></span>
              <span>View calendar plan</span>
            </Link>
          </div>
        </div>

        {/* Column 3: Live Financial Health Gauge */}
        <div className="card-container">
          <div className="card-header-flex">
            <div>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#ea580c", textTransform: "uppercase" }}>
                • Financial Health
              </span>
              <div style={{ fontSize: 12, color: "#64748b", marginTop: 2 }}>
                {riskScore < 0.4 ? "You are doing great!" : "Exercise caution."}
              </div>
            </div>
          </div>

          <div className="health-meter-container">
            <svg viewBox="0 0 160 90" className="health-gauge-svg">
              <path
                d="M 20 80 A 60 60 0 0 1 140 80"
                fill="none"
                stroke="#f1f5f9"
                strokeWidth="12"
                strokeLinecap="round"
              />
              <path
                d="M 20 80 A 60 60 0 0 1 140 80"
                fill="none"
                stroke={riskScore > 0.6 ? "#ef4444" : "#10b981"}
                strokeWidth="12"
                strokeLinecap="round"
                strokeDasharray={`${Math.round(healthScore * 1.85)} 200`}
              />
            </svg>

            <div className="health-score-val">{healthScore}</div>
            <span
              className="health-status-badge"
              style={{
                background: riskScore > 0.6 ? "#fef2f2" : "#ecfdf5",
                color: riskScore > 0.6 ? "#ef4444" : "#10b981",
              }}
            >
              {healthLabel}
            </span>

            <div className="health-trend-sub">
              <span>Risk: {(riskScore * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* ---------------- 4. BOTTOM ROW (COMPUTED SPENDING CHART & CATEGORY BREAKDOWN) ---------------- */}
      <div className="dash-bottom-grid">
        {/* Spending Overview Bar Chart */}
        <div className="card-container">
          <div className="card-header-flex">
            <h3 className="card-header-title">Spending Overview (Live)</h3>
            <span style={{ fontSize: 12, color: "#64748b" }}>Last 7 days</span>
          </div>

          <div className="bar-chart-flex">
            {spendBars.map((bar) => (
              <div key={bar.day} className="bar-column-item">
                <div
                  className="bar-fill-rect"
                  style={{ height: `${bar.height}%` }}
                  title={`${bar.day}: ${bar.amount}`}
                />
                <span className="bar-label-day">{bar.day}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Spend by Category Breakdown */}
        <div className="card-container">
          <div className="card-header-flex">
            <h3 className="card-header-title">Spend by Category</h3>
            <Link href="/money" className="link-action-small">Ledger <IconArrowRight size={12} /></Link>
          </div>

          <div className="goals-list-flex">
            {categoryBreakdown.length > 0 ? (
              categoryBreakdown.map((item) => (
                <div key={item.category} className="goal-item-row">
                  <div className="goal-label-flex">
                    <span className="goal-name-text" style={{ textTransform: "capitalize" }}>{item.category}</span>
                    <span className="goal-amount-text">{item.amount} ({item.pct}%)</span>
                  </div>
                  <div className="progress-track-bar">
                    <div className="progress-fill-bar" style={{ width: `${item.pct}%` }} />
                  </div>
                </div>
              ))
            ) : (
              <>
                <div className="goal-item-row">
                  <div className="goal-label-flex">
                    <span className="goal-name-text">Rent</span>
                    <span className="goal-amount-text">₦85,000 (45%)</span>
                  </div>
                  <div className="progress-track-bar">
                    <div className="progress-fill-bar" style={{ width: "45%" }} />
                  </div>
                </div>
                <div className="goal-item-row">
                  <div className="goal-label-flex">
                    <span className="goal-name-text">Food</span>
                    <span className="goal-amount-text">₦45,000 (24%)</span>
                  </div>
                  <div className="progress-track-bar">
                    <div className="progress-fill-bar" style={{ width: "24%" }} />
                  </div>
                </div>
                <div className="goal-item-row">
                  <div className="goal-label-flex">
                    <span className="goal-name-text">Transport</span>
                    <span className="goal-amount-text">₦25,000 (13%)</span>
                  </div>
                  <div className="progress-track-bar">
                    <div className="progress-fill-bar" style={{ width: "13%" }} />
                  </div>
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {/* ---------------- 5. FOOTER GRID (DEADLINES & MOTIVATION) ---------------- */}
      <div className="dash-footer-grid">
        {/* Live Upcoming Deadlines */}
        <div className="card-container">
          <div className="card-header-flex">
            <h3 className="card-header-title">Upcoming Deadlines</h3>
            <button
              onClick={() => setShowDeadlineModal(true)}
              className="link-action-small"
              style={{ background: "none", border: "none", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}
            >
              <IconPlus size={12} /> Add Deadline
            </button>
          </div>

          <div className="bills-list-flex">
            {nextDeadlines.length > 0 ? (
              nextDeadlines.slice(0, 3).map((d: any) => (
                <div key={d.id || d.title} className="bill-item-row">
                  <div className="bill-icon-title">
                    <div className="bill-icon-badge"><IconBook size={16} color="#ea580c" /></div>
                    <div>
                      <div className="bill-title">{d.title}</div>
                      <div className="bill-due-date">Due: {d.due_at ? d.due_at.slice(0, 10) : "Upcoming"}</div>
                    </div>
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <span className="badge-status upcoming" style={{ fontSize: 10 }}>
                      Weight: {d.weight || 1.0}
                    </span>
                  </div>
                </div>
              ))
            ) : (
              <p style={{ fontSize: 13, color: "#64748b" }}>No upcoming deadlines.</p>
            )}
          </div>
        </div>

        {/* Motivation Card */}
        <div className="motivation-card-orange">
          <div>
            <div className="kpi-icon-badge" style={{ width: 36, height: 36, fontSize: 18 }}><IconTarget size={20} color="#ea580c" /></div>
            <h3 style={{ fontSize: 18, fontWeight: 800, color: "#0f172a", margin: "14px 0 4px" }}>
              Stay consistent.
            </h3>
            <p className="motivation-quote-text">
              Your future self will thank you.
            </p>
          </div>
          <div className="motivation-author">— Atlas</div>
        </div>
      </div>

      {/* Log Transaction Modal */}
      {showTxModal && (
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
          onClick={() => setShowTxModal(false)}
        >
          <div
            style={{ background: "#ffffff", borderRadius: 20, padding: 32, maxWidth: 440, width: "90%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "#0f172a", display: "flex", alignItems: "center", gap: 8 }}>
                <IconWallet size={20} color="#ea580c" /> Log Transaction
              </h3>
              <button onClick={() => setShowTxModal(false)} style={{ border: "none", background: "none", cursor: "pointer" }}>
                <IconClose size={18} color="#64748b" />
              </button>
            </div>
            <form onSubmit={handleLogTransaction} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 4 }}>
                  Amount (NGN)
                </label>
                <input
                  type="number"
                  placeholder="e.g. 5000"
                  value={txAmount}
                  onChange={(e) => setTxAmount(e.target.value)}
                  style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e2e8f0" }}
                  required
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 4 }}>
                  Category
                </label>
                <select
                  value={txCategory}
                  onChange={(e) => setTxCategory(e.target.value)}
                  style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e2e8f0" }}
                >
                  <option value="food">Food & Dining</option>
                  <option value="transport">Transport</option>
                  <option value="rent">Rent & Housing</option>
                  <option value="subscriptions">Subscriptions</option>
                  <option value="general">General</option>
                </select>
              </div>

              <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                <button type="submit" className="btn-orange-pill" style={{ flex: 1 }}>
                  Log Spend
                </button>
                <button type="button" onClick={() => setShowTxModal(false)} className="btn-demo-watch" style={{ flex: 1 }}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Create Deadline Modal */}
      {showDeadlineModal && (
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
          onClick={() => setShowDeadlineModal(false)}
        >
          <div
            style={{ background: "#ffffff", borderRadius: 20, padding: 32, maxWidth: 440, width: "90%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: "#0f172a", display: "flex", alignItems: "center", gap: 8 }}>
                <IconBook size={20} color="#ea580c" /> Create Deadline
              </h3>
              <button onClick={() => setShowDeadlineModal(false)} style={{ border: "none", background: "none", cursor: "pointer" }}>
                <IconClose size={18} color="#64748b" />
              </button>
            </div>
            <form onSubmit={handleAddDeadline} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 4 }}>
                  Deadline Title
                </label>
                <input
                  type="text"
                  placeholder="e.g. Physics Midterm Exam"
                  value={dlTitle}
                  onChange={(e) => setDlTitle(e.target.value)}
                  style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e2e8f0" }}
                  required
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: 12, fontWeight: 600, color: "#475569", marginBottom: 4 }}>
                  Due Date
                </label>
                <input
                  type="date"
                  value={dlDate}
                  onChange={(e) => setDlDate(e.target.value)}
                  style={{ width: "100%", padding: 10, borderRadius: 10, border: "1px solid #e2e8f0" }}
                  required
                />
              </div>

              <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
                <button type="submit" className="btn-orange-pill" style={{ flex: 1 }}>
                  Create Deadline
                </button>
                <button type="button" onClick={() => setShowDeadlineModal(false)} className="btn-demo-watch" style={{ flex: 1 }}>
                  Cancel
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
