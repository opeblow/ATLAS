"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  IconShield,
  IconCalendar,
  IconTarget,
  IconMic,
  IconChart,
  IconClose,
} from "../components/Icons";

export default function LandingPage() {
  const [showAboutModal, setShowAboutModal] = useState(false);
  const aboutDialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showAboutModal) return;
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const focusable = aboutDialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not([disabled]), a[href]'
    );
    focusable?.[0]?.focus();

    const handleDialogKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setShowAboutModal(false);
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
  }, [showAboutModal]);

  return (
    <div className="landing-page">
      {/* ---------------- 1. TOP NAVIGATION HEADER ---------------- */}
      <header className="landing-header">
        <div className="landing-header-inner">
          <div className="brand-logo">
            <span className="brand-dot" />
            <span style={{ color: "#0f172a" }}>ATLAS</span>
          </div>

          <nav className="landing-nav-links">
            <a href="#home">Home</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#features">Features</a>
            <button
              type="button" onClick={() => setShowAboutModal(true)}
              style={{ background: "none", border: "none", font: "inherit", color: "inherit", cursor: "pointer" }}
            >
              About
            </button>
          </nav>

          <Link href="/dashboard" className="btn-orange-pill">
            Get Started →
          </Link>
        </div>
      </header>

      {/* ---------------- 2. HERO SECTION ---------------- */}
      <section id="home" className="landing-hero">
        <div className="hero-content">
          <div className="hero-pill-badge">
            <IconShield size={12} color="#ea580c" /> AI-POWERED FINANCIAL PLANNING
          </div>

          <h1 className="hero-title">
            A chief of staff your voice can actually use for{" "}
            <span className="highlight">money</span> and{" "}
            <span className="highlight">time.</span>
          </h1>

          <p className="hero-subtitle">
            Atlas listens, understands your goals, and turns them into a real plan — tracking your finances, managing your schedule, and helping you make better decisions, every day.
          </p>

          <div className="hero-ctas">
            <Link href="/dashboard" className="btn-orange-pill" style={{ padding: "14px 30px", fontSize: "15px" }}>
              Get Started Free →
            </Link>

            <a href="#product-preview" className="btn-demo-watch">
              <span>Explore the product</span>
              <span aria-hidden="true">↓</span>
            </a>
          </div>
        </div>

        <div className="hero-product-image" id="product-preview">
          <img
            src="/landing_page_showcase.png"
            alt="ATLAS financial dashboard with spending insights, schedule, and voice assistant"
          />
        </div>
      </section>

      {/* ---------------- 3. FEATURE PILLARS BAR ---------------- */}
      <section id="features" className="landing-pillars-bar">
        <div className="pillars-grid-4">
          <div className="pillar-card-item">
            <div className="pillar-card-icon"><IconShield size={20} color="#ea580c" /></div>
            <div className="pillar-card-title">Financial Planning</div>
            <div className="pillar-card-desc">Track spending, build budgets, grow wealth.</div>
          </div>

          <div className="pillar-card-item">
            <div className="pillar-card-icon"><IconCalendar size={20} color="#ea580c" /></div>
            <div className="pillar-card-title">Smart Scheduling</div>
            <div className="pillar-card-desc">Prioritize what matters, never miss a deadline.</div>
          </div>

          <div className="pillar-card-item">
            <div className="pillar-card-icon"><IconTarget size={20} color="#ea580c" /></div>
            <div className="pillar-card-title">Goal Tracking</div>
            <div className="pillar-card-desc">Turn your goals into a step-by-step plan.</div>
          </div>

          <div className="pillar-card-item">
            <div className="pillar-card-icon"><IconMic size={20} color="#ea580c" /></div>
            <div className="pillar-card-title">Voice-First AI</div>
            <div className="pillar-card-desc">Just speak. Atlas handles the rest.</div>
          </div>
        </div>
      </section>

      {/* ---------------- 4. HOW IT WORKS SECTION ---------------- */}
      <section id="how-it-works" className="how-it-works-section">
        <div className="how-it-works-inner">
          <div>
            <span className="section-tag-pill">HOW IT WORKS</span>
            <h2 className="section-title-large">Simple. Powerful. Built for your goals.</h2>
            <p className="section-desc-text">
              Get started in minutes and let Atlas handle the complexity. It is like having a personal chief of staff in your pocket.
            </p>
            <Link href="/dashboard" className="btn-orange-pill">
              See how it works →
            </Link>
          </div>

          <div className="workflow-steps-list">
            <div className="workflow-step-card">
              <div className="workflow-step-icon"><IconMic size={18} color="#ea580c" /></div>
              <div>
                <div className="workflow-step-title">1. Tell Atlas</div>
                <div className="workflow-step-desc">Speak your goals, ask questions, or set a plan.</div>
              </div>
            </div>

            <div className="workflow-step-card">
              <div className="workflow-step-icon"><IconChart size={18} color="#ea580c" /></div>
              <div>
                <div className="workflow-step-title">2. Get a Plan</div>
                <div className="workflow-step-desc">Atlas creates a personalized financial and time plan.</div>
              </div>
            </div>

            <div className="workflow-step-card">
              <div className="workflow-step-icon"><IconTarget size={18} color="#ea580c" /></div>
              <div>
                <div className="workflow-step-title">3. Stay on Track</div>
                <div className="workflow-step-desc">Receive updates, reminders, and insights — automatically.</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------- 5. MORE CONTROL. LESS STRESS. SECTION ---------------- */}
      <section className="landing-metrics-section">
        <div className="metrics-left-box">
          <span className="hero-pill-badge" style={{ margin: 0 }}>
            • ATLAS ARCHITECTURE
          </span>
          <h2 className="section-title-large" style={{ marginTop: 12 }}>
            More control. Less stress.
          </h2>
          <p className="section-desc-text">
            Your goals deserve more than a spreadsheet. They deserve Atlas.
          </p>

          <div className="metrics-stats-grid">
            <div>
              <div className="stat-number-big">24/7</div>
              <div className="stat-label-text">Always on</div>
            </div>

            <div>
              <div className="stat-number-big">100%</div>
              <div className="stat-label-text">Your data, your control</div>
            </div>

            <div>
              <div className="stat-number-big">∞</div>
              <div className="stat-label-text">Possibilities</div>
            </div>
          </div>
        </div>

        {/* Right Chat Preview Box */}
        <div className="chat-card-preview">
          <div className="chat-user-row">
            <img
              src="https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=100&auto=format&fit=crop&q=80"
              alt="Atlas Partner"
              className="user-avatar-circle"
            />
            <div>
              <div style={{ fontWeight: 700, fontSize: 14, color: "#0f172a" }}>Atlas</div>
              <div style={{ fontSize: 11, color: "#94a3b8" }}>Your AI financial partner</div>
            </div>
          </div>

          <div className="chat-bubble-speech">
            You are making great progress on your goals, Opeyemi!
          </div>

          <div className="soundwave-bars" style={{ justifyContent: "flex-start", paddingLeft: 8 }}>
            <span className="soundwave-bar" style={{ background: "#ea580c" }} />
            <span className="soundwave-bar" style={{ background: "#ea580c" }} />
            <span className="soundwave-bar" style={{ background: "#ea580c" }} />
            <span className="soundwave-bar" style={{ background: "#ea580c" }} />
            <span className="soundwave-bar" style={{ background: "#ea580c" }} />
          </div>
        </div>
      </section>

      {/* ---------------- 6. FOOTER ---------------- */}
      <footer style={{ borderTop: "1px solid #e2e8f0", padding: "40px 24px", textAlign: "center", background: "#f8fafc" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 20 }}>
          <div className="brand-logo" style={{ fontSize: 16 }}>
            <span className="brand-dot" />
            <span>ATLAS</span>
          </div>

          <p style={{ margin: 0, fontSize: 13, color: "#64748b" }}>
            © {new Date().getFullYear()} ATLAS. All rights reserved. Built for money and time.
          </p>

          <Link href="/dashboard" className="btn-orange-pill" style={{ padding: "8px 18px", fontSize: "13px" }}>
            Open Dashboard →
          </Link>
        </div>
      </footer>

      {/* About Modal */}
      {showAboutModal && (
        <div className="modal-overlay" onClick={() => setShowAboutModal(false)}>
          <div
            ref={aboutDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="about-atlas-title"
            className="about-dialog-panel"
            onKeyDown={(event) => {
              if (event.key === "Escape") setShowAboutModal(false);
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
              <div id="about-atlas-title" className="brand-logo">
                <span className="brand-dot" />
                <span>About ATLAS</span>
              </div>
              <button type="button" aria-label="Close About dialog" onClick={() => setShowAboutModal(false)} style={{ border: "none", background: "none", cursor: "pointer" }}>
                <IconClose size={18} color="#64748b" />
              </button>
            </div>

            <p style={{ fontSize: 15, color: "#475569", lineHeight: 1.6, marginBottom: 16 }}>
              <strong>ATLAS</strong> is an agentic chief of staff driven by voice. It combines a trained PyTorch financial risk model (scoring risk in gradient space), an append-only idempotent transaction ledger, and automated spaced study scheduling.
            </p>

            <div className="about-innovation-list">
              <div style={{ fontWeight: 700, color: "#ea580c", marginBottom: 6 }}>Key Innovations:</div>
              <ul style={{ margin: 0, paddingLeft: 20, lineHeight: 1.6 }}>
                <li><strong>Idempotency Safety:</strong> Replayed voice commands are guaranteed no-ops.</li>
                <li><strong>Explainable Risk:</strong> Every score unpacks its top gradient drivers.</li>
                <li><strong>Spaced Scheduling:</strong> Deadlines automatically turn into conflict-free study blocks.</li>
              </ul>
            </div>

            <Link href="/dashboard" className="btn-orange-pill" style={{ width: "100%" }}>
              Explore Dashboard
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}
