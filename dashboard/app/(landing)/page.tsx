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

const PILLARS = [
  {
    icon: IconShield,
    title: "Financial Planning",
    desc: "Track spending, build budgets, grow wealth.",
  },
  {
    icon: IconCalendar,
    title: "Smart Scheduling",
    desc: "Prioritize what matters, never miss a deadline.",
  },
  {
    icon: IconTarget,
    title: "Goal Tracking",
    desc: "Turn your goals into a step-by-step plan.",
  },
  {
    icon: IconMic,
    title: "Voice-First AI",
    desc: "Just speak. Atlas handles the rest.",
  },
];

const STEPS = [
  {
    icon: IconMic,
    title: "1. Tell Atlas",
    desc: "Speak your goals, ask questions, or set a plan.",
  },
  {
    icon: IconChart,
    title: "2. Get a Plan",
    desc: "Atlas creates a personalized financial and time plan.",
  },
  {
    icon: IconTarget,
    title: "3. Stay on Track",
    desc: "Receive updates, reminders, and insights — automatically.",
  },
];

const STATS = [
  { value: "24/7", label: "Always on" },
  { value: "100%", label: "Your data, your control" },
  { value: "∞", label: "Possibilities" },
];

export default function LandingPage() {
  const [showAboutModal, setShowAboutModal] = useState(false);
  const aboutDialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!showAboutModal) return;
    const previousFocus =
      document.activeElement instanceof HTMLElement ? document.activeElement : null;
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

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleDialogKeyDown);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleDialogKeyDown);
      previousFocus?.focus();
    };
  }, [showAboutModal]);

  return (
    <div className="landing-page">
      {/* ------------------------------ header ------------------------------ */}
      <header className="landing-header">
        <div className="landing-header-inner">
          <div className="brand-logo">
            <span className="brand-dot" />
            <span>ATLAS</span>
          </div>

          <nav className="landing-nav-links">
            <a href="#home">Home</a>
            <a href="#how-it-works">How It Works</a>
            <a href="#features">Features</a>
            <button type="button" onClick={() => setShowAboutModal(true)}>
              About
            </button>
          </nav>

          <Link href="/dashboard" className="btn-primary">
            Get Started →
          </Link>
        </div>
      </header>

      {/* ------------------------------- hero ------------------------------- */}
      <section id="home" className="landing-hero">
        <div className="hero-content">
          <div className="hero-pill-badge">
            <IconShield size={12} /> AI-powered financial planning
          </div>

          <h1 className="hero-title">
            A chief of staff your voice can actually use for money and time.
          </h1>

          <p className="hero-subtitle">
            Atlas listens, understands your goals, and turns them into a real
            plan — tracking your finances, managing your schedule, and helping
            you make better decisions, every day.
          </p>

          <div className="hero-ctas">
            <Link href="/dashboard" className="btn-primary">
              Get Started Free →
            </Link>
            <a href="#product-preview" className="btn-demo-watch">
              <span>Explore the product</span>
              <span aria-hidden="true">↓</span>
            </a>
          </div>
        </div>

        <div className="hero-product-image" id="product-preview">
          <div className="hero-product-image-inner">
            <img
              src="/product-preview.svg"
              alt="The ATLAS dashboard: navigation, spend, risk and schedule figures, a twelve-week spend trend, and the assistant"
              width={1120}
              height={700}
              loading="eager"
              decoding="async"
            />
          </div>
        </div>
      </section>

      {/* ----------------------------- pillars ----------------------------- */}
      <section id="features" className="landing-pillars-bar">
        <div className="pillars-grid-4">
          {PILLARS.map(({ icon: Icon, title, desc }) => (
            <div className="pillar-card-item" key={title}>
              <div className="pillar-card-icon">
                <Icon size={18} />
              </div>
              <div className="pillar-card-title">{title}</div>
              <div className="pillar-card-desc">{desc}</div>
            </div>
          ))}
        </div>
      </section>

          {/* -------------------------- how it works ------------------------- */}
      <section id="how-it-works" className="how-it-works-section">
        <div className="how-it-works-inner">
          <div>
            <span className="section-tag-pill">How it works</span>
            <h2 className="section-title-large">
              Simple. Powerful. Built for your goals.
            </h2>
            <p className="section-desc-text">
              Get started in minutes and let Atlas handle the complexity. It is
              like having a personal chief of staff in your pocket.
            </p>
            <Link href="/dashboard" className="btn-primary">
              See how it works →
            </Link>
          </div>

          <div className="workflow-steps-list">
            {STEPS.map(({ icon: Icon, title, desc }) => (
              <div className="workflow-step-card" key={title}>
                <div className="workflow-step-icon">
                  <Icon size={16} />
                </div>
                <div>
                  <div className="workflow-step-title">{title}</div>
                  <div className="workflow-step-desc">{desc}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------------------- metrics ----------------------------- */}
      <section className="landing-metrics-section">
        <div className="metrics-left-box">
          <span className="hero-pill-badge">Atlas architecture</span>
          <h2 className="section-title-large">More control. Less stress.</h2>
          <p className="section-desc-text">
            Your goals deserve more than a spreadsheet. They deserve Atlas.
          </p>

          <div className="metrics-stats-grid">
            {STATS.map(({ value, label }) => (
              <div key={label}>
                <div className="stat-number-big">{value}</div>
                <div className="stat-label-text">{label}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="chat-card-preview">
          <div className="chat-user-row">
            <div className="chat-avatar-mark" aria-hidden="true">
              A
            </div>
            <div className="lang">
              <div className="chat-name-text">Atlas</div>
              <div className="chat-role-text">Your AI financial partner</div>
            </div>
          </div>

          <div className="chat-bubble-speech">
            You are making great progress on your goals, Opeyemi!
          </div>

          <div className="soundwave-bars" aria-hidden="true">
            {[0, 1, 2, 3, 4].map((i) => (
              <span className="soundwave-bar" key={i} />
            ))}
          </div>
        </div>
      </section>

      {/* ----------------------------- footer ----------------------------- */}
      <footer>
        <div>
          <div className="brand-logo">
            <span className="brand-dot" />
            <span>ATLAS</span>
          </div>

          <p>© {new Date().getFullYear()} ATLAS. Built for money and time.</p>

          <Link href="/dashboard" className="btn-primary">
            Open Dashboard →
          </Link>
        </div>
      </footer>

      {/* ---------------------------- about modal --------------------------- */}
      {showAboutModal && (
        <div className="modal-overlay" onClick={() => setShowAboutModal(false)}>
          <div
            ref={aboutDialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="about-atlas-title"
            className="about-dialog-panel"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="dialog-head">
              <div id="about-atlas-title" className="dialog-head-title">
                <span className="brand-dot" />
                <span>About ATLAS</span>
              </div>
              <button
                type="button"
                aria-label="Close About dialog"
                className="dialog-close"
                onClick={() => setShowAboutModal(false)}
              >
                <IconClose size={16} />
              </button>
            </div>

            <p>
              <strong>ATLAS</strong> is an agentic chief of staff driven by
              voice. It combines a trained PyTorch financial risk model (scoring
              risk in gradient space), an append-only idempotent transaction
              ledger, and automated spaced study scheduling.
            </p>

            <div className="about-innovation-list">
              <div className="about-innovation-label">Key innovations</div>
              <ul>
                <li>
                  <strong>Idempotency safety:</strong> Replayed voice commands
                  are guaranteed no-ops.
                </li>
                <li>
                  <strong>Explainable risk:</strong> Every score unpacks its top
                  gradient drivers.
                </li>
                <li>
                  <strong>Spaced scheduling:</strong> Deadlines automatically
                  turn into conflict-free study blocks.
                </li>
              </ul>
            </div>

            <Link href="/dashboard" className="btn-primary btn-block">
              Explore Dashboard
            </Link>
          </div>
        </div>
      )}
    </div>
  );
}