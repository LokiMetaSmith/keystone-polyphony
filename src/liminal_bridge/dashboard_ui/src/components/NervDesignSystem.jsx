import { useState, useEffect, useRef, useCallback } from "react";

/*
╔══════════════════════════════════════════════════════════════════════════════╗
║  PYNCH LABS DESIGN SYSTEM — CODENAME: NERV                                ║
║  Evangelion-Inspired Design Language for React + Tailwind                   ║
║                                                                            ║
║  VERSION: 1.0.0                                                            ║
║  AUTHOR: Andrew / Pynch Labs LLC                                           ║
║                                                                            ║
║  USAGE:                                                                    ║
║  1. Copy TOKENS object into your project constants                         ║
║  2. Copy TAILWIND_EXTEND into tailwind.config.js → theme.extend            ║
║  3. Copy CSS_CUSTOM_PROPERTIES into your global.css                        ║
║  4. Reference component patterns in the interactive preview below          ║
║  5. Per-app theming: set data-theme attribute on root element              ║
║                                                                            ║
║  GOOGLE FONTS (add to <head>):                                             ║
║  families: Archivo+Black, Share+Tech+Mono, Space+Mono:wght@400;700,       ║
║           Noto+Sans+JP:wght@400;700;900, Orbitron:wght@400;700;900        ║
╚══════════════════════════════════════════════════════════════════════════════╝
*/

// ═══════════════════════════════════════════════════════════════════════════
// SECTION 01: DESIGN TOKENS
// ═══════════════════════════════════════════════════════════════════════════

const TOKENS = {
  colors: {
    bg: {
      void:     "#000000",
      base:     "#0a0a0f",
      surface:  "#111118",
      elevated: "#1a1a24",
      overlay:  "rgba(10,10,15,0.85)",
    },
    grid: {
      line:   "rgba(255,255,255,0.06)",
      strong: "rgba(255,255,255,0.12)",
      tick:   "rgba(255,255,255,0.25)",
      axis:   "rgba(255,255,255,0.4)",
    },
    text: {
      primary:   "#e8e8f0",
      secondary: "#8888a0",
      muted:     "#555566",
      inverse:   "#0a0a0f",
    },
    status: {
      danger:     "#ff1a1a",
      dangerDark: "#991111",
      caution:    "#ffaa00",
      ok:         "#00cc66",
      info:       "#4488ff",
    },
    hazard: {
      green:  ["#22bb44","#111118"],
      red:    ["#cc2200","#ddaa00"],
    },
  },
  themes: {
    nerv: {
      name: "NERV", jp: "ネルフ本部",
      primary: "#ff8800", primaryMuted: "#cc6600", primaryGlow: "rgba(255,136,0,0.15)",
      secondary: "#00ddaa", secondaryMuted: "#009977", secondaryGlow: "rgba(0,221,170,0.12)",
      tertiary: "#ff3366", tertiaryMuted: "#cc2255",
    },
    magi: {
      name: "MAGI", jp: "マギ",
      primary: "#00ff88", primaryMuted: "#00cc66", primaryGlow: "rgba(0,255,136,0.12)",
      secondary: "#ff6600", secondaryMuted: "#cc5500", secondaryGlow: "rgba(255,102,0,0.10)",
      tertiary: "#ffdd00", tertiaryMuted: "#ccaa00",
    },
    seele: {
      name: "SEELE", jp: "ゼーレ",
      primary: "#cc3333", primaryMuted: "#991a1a", primaryGlow: "rgba(204,51,51,0.12)",
      secondary: "#8888aa", secondaryMuted: "#666688", secondaryGlow: "rgba(136,136,170,0.08)",
      tertiary: "#ffcc00", tertiaryMuted: "#cc9900",
    },
    terminal: {
      name: "TERMINAL", jp: "ターミナル",
      primary: "#00ccff", primaryMuted: "#0099cc", primaryGlow: "rgba(0,204,255,0.12)",
      secondary: "#88ff44", secondaryMuted: "#66cc22", secondaryGlow: "rgba(136,255,68,0.10)",
      tertiary: "#ff4488", tertiaryMuted: "#cc2266",
    },
  },
  type: {
    display: "'Archivo Black', Impact, sans-serif",
    body:    "'Space Mono', monospace",
    data:    "'Share Tech Mono', 'Orbitron', monospace",
    jp:      "'Noto Sans JP', sans-serif",
  },
  radii: { none: 0, sm: 2, md: 3 },
  borders: { hairline: 1, normal: 2, heavy: 3 },
  motion: {
    scanline: "8s linear infinite",
    pulse:    "2s ease-in-out infinite",
    blink:    "1s step-end infinite",
    cascadeMs: 600,
    staggerMs: 60,
    flickerMs: 100,
  },
};

// ═══════════════════════════════════════════════════════════════════════════
// SECTION 02: INTERACTIVE PREVIEW APPLICATION
// ═══════════════════════════════════════════════════════════════════════════

const SECTIONS = [
  { id:"themes",     en:"THEME PRESETS",     jp:"テーマ設定",     num:"01" },
  { id:"palette",    en:"COLOR PALETTE",     jp:"カラーパレット",  num:"02" },
  { id:"typography", en:"TYPOGRAPHY",        jp:"タイポグラフィ",  num:"03" },
  { id:"components", en:"COMPONENTS",        jp:"コンポーネント",  num:"04" },
  { id:"patterns",   en:"LAYOUT PATTERNS",   jp:"レイアウト",     num:"05" },
  { id:"animation",  en:"ANIMATION",         jp:"アニメーション",  num:"06" },
  { id:"code",       en:"IMPLEMENTATION",    jp:"実装コード",     num:"07" },
];

// ─── Styles ────────────────────────────────────────────────────────────────

const S = {
  root: {
    background: TOKENS.colors.bg.base,
    color: TOKENS.colors.text.primary,
    fontFamily: TOKENS.type.body,
    fontSize: 14,
    lineHeight: 1.5,
    letterSpacing: "0.04em",
    minHeight: "100vh",
    position: "relative",
    overflow: "hidden",
  },
  scanlines: {
    position: "fixed", inset: 0, pointerEvents: "none", zIndex: 9999,
    background: "repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.04) 2px,rgba(0,0,0,0.04) 4px)",
  },
  inner: {
    maxWidth: 960, margin: "0 auto", padding: "0 24px", position: "relative", zIndex: 1,
  },
  header: {
    padding: "48px 0 32px", borderBottom: `1px solid ${TOKENS.colors.grid.strong}`,
    marginBottom: 40,
  },
  sectionHead: {
    display: "flex", alignItems: "baseline", gap: 12, marginBottom: 4, marginTop: 48,
  },
  sectionNum: {
    fontFamily: TOKENS.type.data, fontSize: 11, letterSpacing: "0.12em",
    color: TOKENS.colors.text.muted, minWidth: 28,
  },
  sectionEn: {
    fontFamily: TOKENS.type.display, fontSize: 18, letterSpacing: "0.12em",
    textTransform: "uppercase",
  },
  sectionJp: {
    fontFamily: TOKENS.type.jp, fontSize: 12, color: TOKENS.colors.text.secondary,
    marginLeft: 8,
  },
  divider: {
    height: 1, background: TOKENS.colors.grid.strong, margin: "8px 0 24px",
  },
  label: {
    fontFamily: TOKENS.type.body, fontSize: 10, letterSpacing: "0.1em",
    textTransform: "uppercase", color: TOKENS.colors.text.muted, marginBottom: 4,
  },
  sublabel: {
    fontFamily: TOKENS.type.data, fontSize: 11, color: TOKENS.colors.text.secondary,
  },
  card: {
    background: TOKENS.colors.bg.surface,
    border: `1px solid ${TOKENS.colors.grid.strong}`,
    borderRadius: TOKENS.radii.sm,
    padding: 16,
  },
  code: {
    background: TOKENS.colors.bg.void,
    border: `1px solid ${TOKENS.colors.grid.strong}`,
    borderRadius: TOKENS.radii.sm,
    padding: 16,
    fontFamily: TOKENS.type.data,
    fontSize: 12,
    lineHeight: 1.6,
    color: TOKENS.colors.text.secondary,
    overflowX: "auto",
    whiteSpace: "pre",
    maxHeight: 400,
  },
  tick: (color) => ({
    display: "inline-block", width: 8, height: 2, background: color || TOKENS.colors.grid.tick,
    marginRight: 6, verticalAlign: "middle",
  }),
};

// ─── Sub-components ─────────────────────────────────────────────────────────

function SectionHeader({ en, jp, num, color }) {
  return (
    <>
      <div style={S.sectionHead}>
        <span style={S.sectionNum}>{num}</span>
        <span style={{ ...S.sectionEn, color: color || TOKENS.colors.text.primary }}>{en}</span>
        <span style={S.sectionJp}>{jp}</span>
      </div>
      <div style={{ ...S.divider, background: color ? `${color}44` : S.divider.background }} />
    </>
  );
}

function Swatch({ color, name, value, size = 48 }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 6 }}>
      <div style={{
        width: size, height: size, background: color, borderRadius: TOKENS.radii.sm,
        border: `1px solid ${TOKENS.colors.grid.strong}`, flexShrink: 0,
      }} />
      <div>
        <div style={{ fontSize: 12, fontFamily: TOKENS.type.body }}>{name}</div>
        <div style={{ fontSize: 11, fontFamily: TOKENS.type.data, color: TOKENS.colors.text.muted }}>{value}</div>
      </div>
    </div>
  );
}

function Crosshairs({ color = TOKENS.colors.grid.tick }) {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" style={{ display: "inline-block", verticalAlign: "middle" }}>
      <line x1="7" y1="0" x2="7" y2="14" stroke={color} strokeWidth="1" />
      <line x1="0" y1="7" x2="14" y2="7" stroke={color} strokeWidth="1" />
    </svg>
  );
}

function HazardStripe({ type = "green", height = 12, style: s }) {
  const [a, b] = type === "green" ? TOKENS.colors.hazard.green : TOKENS.colors.hazard.red;
  return (
    <div style={{
      height, width: "100%",
      background: `repeating-linear-gradient(-45deg,${a} 0px,${a} 8px,${b} 8px,${b} 16px)`,
      ...s,
    }} />
  );
}

function AxisRuler({ count = 20, color }) {
  const c = color || TOKENS.colors.grid.tick;
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 0, height: 16, overflow: "hidden" }}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: "center", width: 24 }}>
          <div style={{
            width: 1, height: i % 5 === 0 ? 10 : 5,
            background: i % 5 === 0 ? c : `${c}66`,
          }} />
          {i % 5 === 0 && (
            <span style={{ fontSize: 8, fontFamily: TOKENS.type.data, color: TOKENS.colors.text.muted, marginTop: 1 }}>
              {i * 10}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

function GridBg({ children, style: s }) {
  return (
    <div style={{
      backgroundImage: `linear-gradient(${TOKENS.colors.grid.line} 1px,transparent 1px),linear-gradient(90deg,${TOKENS.colors.grid.line} 1px,transparent 1px)`,
      backgroundSize: "48px 48px",
      position: "relative",
      ...s,
    }}>
      {children}
    </div>
  );
}

// ─── Animated components ────────────────────────────────────────────────────

function BlinkingText({ children, style: s }) {
  const [on, setOn] = useState(true);
  useEffect(() => {
    const t = setInterval(() => setOn(v => !v), 1000);
    return () => clearInterval(t);
  }, []);
  return <span style={{ ...s, opacity: on ? 1 : 0 }}>{children}</span>;
}

function TypewriterText({ text, speed = 40, style: s }) {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    setShown(0);
    const t = setInterval(() => setShown(v => {
      if (v >= text.length) { clearInterval(t); return v; }
      return v + 1;
    }), speed);
    return () => clearInterval(t);
  }, [text, speed]);
  return (
    <span style={s}>
      {text.slice(0, shown)}
      {shown < text.length && <BlinkingText style={{ color: TOKENS.colors.text.primary }}>_</BlinkingText>}
    </span>
  );
}

function PulsingDot({ color, size = 8 }) {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    let frame;
    const start = Date.now();
    const loop = () => {
      const t = (Date.now() - start) / 1000;
      setScale(1 + 0.3 * Math.sin(t * Math.PI));
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, []);
  return (
    <div style={{
      width: size, height: size, borderRadius: "50%", background: color,
      transform: `scale(${scale})`, boxShadow: `0 0 ${size}px ${color}`,
      display: "inline-block",
    }} />
  );
}

function DataCounter({ target, duration = 2000, prefix = "", suffix = "", style: s }) {
  const [val, setVal] = useState(0);
  useEffect(() => {
    const start = Date.now();
    const loop = () => {
      const elapsed = Date.now() - start;
      const progress = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - progress, 3);
      setVal(Math.round(target * eased));
      if (progress < 1) requestAnimationFrame(loop);
    };
    requestAnimationFrame(loop);
  }, [target, duration]);
  return <span style={s}>{prefix}{val.toLocaleString()}{suffix}</span>;
}

function CascadeList({ items, stagger = 60 }) {
  const [visible, setVisible] = useState(0);
  useEffect(() => {
    if (visible < items.length) {
      const t = setTimeout(() => setVisible(v => v + 1), stagger);
      return () => clearTimeout(t);
    }
  }, [visible, items.length, stagger]);
  return (
    <div>
      {items.map((item, i) => (
        <div key={i} style={{
          opacity: i < visible ? 1 : 0,
          transform: i < visible ? "translateY(0)" : "translateY(-8px)",
          transition: "opacity 0.4s ease-out, transform 0.4s ease-out",
          marginBottom: 4,
        }}>
          {item}
        </div>
      ))}
    </div>
  );
}

function WaveformSVG({ color, width = "100%", height = 60 }) {
  const ref = useRef(null);
  const [offset, setOffset] = useState(0);
  useEffect(() => {
    let frame;
    const loop = () => {
      setOffset(o => o + 0.03);
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(frame);
  }, []);
  const points = Array.from({ length: 100 }).map((_, i) => {
    const x = (i / 99) * 400;
    const y = 30 + 20 * Math.sin((i / 12) + offset) * Math.cos((i / 20) + offset * 0.7);
    return `${x},${y}`;
  }).join(" ");
  return (
    <svg viewBox="0 0 400 60" style={{ width, height, display: "block" }}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" opacity="0.8" />
    </svg>
  );
}

// ─── Main App ───────────────────────────────────────────────────────────────

export default function NervDesignSystem() {
  const [theme, setTheme] = useState("nerv");
  const [activeSection, setActiveSection] = useState("themes");
  const [codeTab, setCodeTab] = useState("tailwind");
  const t = TOKENS.themes[theme];

  const [time, setTime] = useState(new Date());
  useEffect(() => {
    const i = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(i);
  }, []);

  const fmtTime = time.toLocaleTimeString("en-US", { hour12: false });
  const fmtDate = time.toLocaleDateString("ja-JP");

  return (
    <div style={S.root}>
      <link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Share+Tech+Mono&family=Space+Mono:wght@400;700&family=Noto+Sans+JP:wght@400;700;900&family=Orbitron:wght@400;700;900&display=swap" rel="stylesheet" />
      <div style={S.scanlines} />

      <div style={S.inner}>
        {/* ─── HEADER ────────────────────────────────────────── */}
        <header style={S.header}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 16 }}>
            <div>
              <div style={{ fontFamily: TOKENS.type.display, fontSize: 32, letterSpacing: "0.1em", textTransform: "uppercase", color: t.primary }}>
                PYNCH DESIGN SYSTEM
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 6 }}>
                <span style={{ fontFamily: TOKENS.type.jp, fontSize: 13, color: TOKENS.colors.text.secondary }}>
                  設計システム
                </span>
                <span style={S.tick(t.primary)} />
                <span style={{ fontFamily: TOKENS.type.data, fontSize: 11, color: TOKENS.colors.text.muted }}>
                  CODENAME: NERV
                </span>
                <span style={S.tick(t.secondary)} />
                <span style={{ fontFamily: TOKENS.type.data, fontSize: 11, color: TOKENS.colors.text.muted }}>
                  v1.0.0
                </span>
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontFamily: TOKENS.type.data, fontSize: 28, color: t.primary, letterSpacing: "0.05em" }}>
                {fmtTime}
              </div>
              <div style={{ fontFamily: TOKENS.type.jp, fontSize: 11, color: TOKENS.colors.text.muted }}>
                {fmtDate}
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end", marginTop: 4 }}>
                <PulsingDot color={TOKENS.colors.status.ok} />
                <span style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.status.ok }}>
                  SYSTEM NOMINAL
                </span>
              </div>
            </div>
          </div>

          {/* Nav tabs */}
          <div style={{ display: "flex", gap: 0, marginTop: 20, borderBottom: `1px solid ${TOKENS.colors.grid.line}`, flexWrap: "wrap" }}>
            {SECTIONS.map(s => (
              <button key={s.id} onClick={() => setActiveSection(s.id)} style={{
                background: activeSection === s.id ? `${t.primary}15` : "transparent",
                border: "none", borderBottom: activeSection === s.id ? `2px solid ${t.primary}` : "2px solid transparent",
                color: activeSection === s.id ? t.primary : TOKENS.colors.text.muted,
                fontFamily: TOKENS.type.body, fontSize: 11, letterSpacing: "0.08em",
                textTransform: "uppercase", padding: "8px 14px", cursor: "pointer",
                transition: "all 0.2s",
              }}>
                <span style={{ fontFamily: TOKENS.type.data, marginRight: 6, opacity: 0.5 }}>{s.num}</span>
                {s.en}
              </button>
            ))}
          </div>
        </header>

        {/* ─── 01: THEMES ────────────────────────────────────── */}
        {activeSection === "themes" && (
          <section>
            <SectionHeader en="THEME PRESETS" jp="テーマ設定" num="01" color={t.primary} />
            <p style={{ color: TOKENS.colors.text.secondary, marginBottom: 20, fontSize: 13 }}>
              Each app in the Pynch ecosystem uses a shared base palette (backgrounds, grids, text, status colors) but swaps its accent triad: primary, secondary, tertiary. Set <code style={{ color: t.primary }}>data-theme</code> on your root element to switch.
            </p>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 12 }}>
              {Object.entries(TOKENS.themes).map(([key, th]) => (
                <button key={key} onClick={() => setTheme(key)} style={{
                  ...S.card,
                  cursor: "pointer",
                  borderColor: theme === key ? th.primary : TOKENS.colors.grid.strong,
                  boxShadow: theme === key ? `0 0 20px ${th.primaryGlow}, inset 0 0 20px ${th.primaryGlow}` : "none",
                  transition: "all 0.3s",
                  textAlign: "left",
                }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <span style={{ fontFamily: TOKENS.type.display, fontSize: 16, letterSpacing: "0.1em", color: th.primary }}>
                      {th.name}
                    </span>
                    <span style={{ fontFamily: TOKENS.type.jp, fontSize: 11, color: TOKENS.colors.text.muted }}>
                      {th.jp}
                    </span>
                  </div>
                  <div style={{ display: "flex", gap: 6 }}>
                    {[th.primary, th.secondary, th.tertiary].map((c, i) => (
                      <div key={i} style={{
                        width: 32, height: 16, background: c, borderRadius: TOKENS.radii.sm,
                        border: `1px solid rgba(255,255,255,0.1)`,
                      }} />
                    ))}
                  </div>
                  <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted, marginTop: 8 }}>
                    {th.primary} / {th.secondary} / {th.tertiary}
                  </div>
                </button>
              ))}
            </div>

            <div style={{ marginTop: 24 }}>
              <div style={S.label}>ACTIVE THEME PREVIEW 現在のテーマ</div>
              <GridBg style={{ ...S.card, padding: 24, marginTop: 8 }}>
                <div style={{ display: "flex", gap: 24, flexWrap: "wrap", alignItems: "center" }}>
                  <div>
                    <div style={{ fontFamily: TOKENS.type.display, fontSize: 42, color: t.primary, letterSpacing: "0.08em" }}>
                      {t.name}
                    </div>
                    <div style={{ fontFamily: TOKENS.type.jp, fontSize: 16, color: t.secondary, marginTop: -4 }}>
                      {t.jp}
                    </div>
                  </div>
                  <div style={{ flex: 1, minWidth: 200 }}>
                    <WaveformSVG color={t.primary} height={50} />
                    <WaveformSVG color={t.secondary} height={40} />
                  </div>
                  <div style={{ textAlign: "right" }}>
                    <DataCounter target={99847} prefix="" suffix="" style={{ fontFamily: TOKENS.type.data, fontSize: 36, color: t.primary }} />
                    <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted, marginTop: 2 }}>
                      SYNC RATE データ同期率
                    </div>
                  </div>
                </div>
                <HazardStripe type="green" style={{ marginTop: 16, opacity: 0.6 }} />
              </GridBg>
            </div>
          </section>
        )}

        {/* ─── 02: PALETTE ───────────────────────────────────── */}
        {activeSection === "palette" && (
          <section>
            <SectionHeader en="COLOR PALETTE" jp="カラーパレット" num="02" color={t.primary} />

            <div style={S.label}>BACKGROUNDS 背景色</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 8, marginBottom: 20 }}>
              {Object.entries(TOKENS.colors.bg).filter(([k]) => k !== "overlay").map(([name, val]) => (
                <Swatch key={name} color={val} name={`bg.${name}`} value={val} />
              ))}
            </div>

            <div style={S.label}>TEXT テキスト</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 8, marginBottom: 20 }}>
              {Object.entries(TOKENS.colors.text).map(([name, val]) => (
                <Swatch key={name} color={val} name={`text.${name}`} value={val} />
              ))}
            </div>

            <div style={S.label}>ACCENT TRIAD (THEME-DEPENDENT) アクセント</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 8, marginBottom: 20 }}>
              <Swatch color={t.primary} name="primary" value={t.primary} />
              <Swatch color={t.primaryMuted} name="primaryMuted" value={t.primaryMuted} />
              <Swatch color={t.secondary} name="secondary" value={t.secondary} />
              <Swatch color={t.secondaryMuted} name="secondaryMuted" value={t.secondaryMuted} />
              <Swatch color={t.tertiary} name="tertiary" value={t.tertiary} />
              <Swatch color={t.tertiaryMuted} name="tertiaryMuted" value={t.tertiaryMuted} />
            </div>

            <div style={S.label}>STATUS STATES ステータス</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 8, marginBottom: 20 }}>
              {Object.entries(TOKENS.colors.status).map(([name, val]) => (
                <Swatch key={name} color={val} name={`status.${name}`} value={val} />
              ))}
            </div>

            <div style={S.label}>GRID & STRUCTURAL LINES グリッド</div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))", gap: 8 }}>
              {Object.entries(TOKENS.colors.grid).map(([name, val]) => (
                <Swatch key={name} color={val} name={`grid.${name}`} value={val} />
              ))}
            </div>

            <div style={{ marginTop: 24 }}>
              <div style={S.label}>HAZARD PATTERNS 警告パターン</div>
              <div style={{ display: "flex", gap: 12, marginTop: 8 }}>
                <div style={{ flex: 1 }}>
                  <HazardStripe type="green" height={24} />
                  <div style={{ ...S.sublabel, marginTop: 4 }}>nerv-hazard-green</div>
                </div>
                <div style={{ flex: 1 }}>
                  <HazardStripe type="red" height={24} />
                  <div style={{ ...S.sublabel, marginTop: 4 }}>nerv-hazard-red</div>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* ─── 03: TYPOGRAPHY ────────────────────────────────── */}
        {activeSection === "typography" && (
          <section>
            <SectionHeader en="TYPOGRAPHY" jp="タイポグラフィ" num="03" color={t.primary} />

            <div style={{ ...S.card, marginBottom: 16 }}>
              <div style={S.label}>DISPLAY フォント — ARCHIVO BLACK</div>
              <div style={{ fontFamily: TOKENS.type.display, fontSize: 48, letterSpacing: "0.08em", textTransform: "uppercase", color: t.primary, lineHeight: 1.1 }}>
                CENTRAL DOGMA
              </div>
              <div style={{ fontFamily: TOKENS.type.display, fontSize: 24, letterSpacing: "0.12em", textTransform: "uppercase", color: TOKENS.colors.text.primary, marginTop: 8 }}>
                PATTERN BLUE DETECTED
              </div>
              <div style={{ fontFamily: TOKENS.type.data, fontSize: 11, color: TOKENS.colors.text.muted, marginTop: 8 }}>
                Usage: Page titles, section headers, alert banners, hero text. Always uppercase, tracked wide.
              </div>
            </div>

            <div style={{ ...S.card, marginBottom: 16 }}>
              <div style={S.label}>BODY フォント — SPACE MONO</div>
              <div style={{ fontFamily: TOKENS.type.body, fontSize: 14, color: TOKENS.colors.text.primary, lineHeight: 1.6 }}>
                The MAGI system consists of three supercomputers: MELCHIOR-1, BALTHASAR-2, and CASPER-3. Each represents an aspect of their creator's personality, enabling consensus-based decision making for NERV operations.
              </div>
              <div style={{ fontFamily: TOKENS.type.body, fontSize: 14, color: TOKENS.colors.text.secondary, marginTop: 8, lineHeight: 1.6 }}>
                Secondary text color for supporting information and descriptions that don't require primary emphasis.
              </div>
              <div style={{ fontFamily: TOKENS.type.data, fontSize: 11, color: TOKENS.colors.text.muted, marginTop: 8 }}>
                Usage: Body copy, descriptions, form labels, navigation items. Default font for all UI text.
              </div>
            </div>

            <div style={{ ...S.card, marginBottom: 16 }}>
              <div style={S.label}>DATA フォント — SHARE TECH MONO</div>
              <div style={{ fontFamily: TOKENS.type.data, color: t.primary, marginBottom: 12 }}>
                <span style={{ fontSize: 48, letterSpacing: "0.05em" }}>223,229</span>
                <span style={{ fontSize: 14, color: TOKENS.colors.text.muted, marginLeft: 8 }}>sec.</span>
              </div>
              <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontFamily: TOKENS.type.data, fontSize: 24, color: t.secondary }}>00:15:42</div>
                  <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>ELAPSED TIME 経過時間</div>
                </div>
                <div>
                  <div style={{ fontFamily: TOKENS.type.data, fontSize: 24, color: TOKENS.colors.status.caution }}>078.3%</div>
                  <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>SYNC RATE 同期率</div>
                </div>
                <div>
                  <div style={{ fontFamily: TOKENS.type.data, fontSize: 24, color: TOKENS.colors.status.danger }}>
                    <BlinkingText>CRITICAL</BlinkingText>
                  </div>
                  <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>STATUS ステータス</div>
                </div>
              </div>
              <div style={{ fontFamily: TOKENS.type.data, fontSize: 11, color: TOKENS.colors.text.muted, marginTop: 12 }}>
                Usage: Numerical readouts, timestamps, counters, axis labels, technical data. Use tabular-nums for alignment.
              </div>
            </div>

            <div style={{ ...S.card }}>
              <div style={S.label}>JAPANESE フォント — NOTO SANS JP</div>
              <div style={{ fontFamily: TOKENS.type.jp }}>
                <div style={{ fontSize: 24, fontWeight: 900, color: t.primary }}>汎用人型決戦兵器</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: TOKENS.colors.text.primary, marginTop: 4 }}>エヴァンゲリオン初号機</div>
                <div style={{ fontSize: 13, fontWeight: 400, color: TOKENS.colors.text.secondary, marginTop: 4 }}>全てのシステム、正常に稼働中</div>
              </div>
              <div style={{ fontFamily: TOKENS.type.data, fontSize: 11, color: TOKENS.colors.text.muted, marginTop: 12 }}>
                Usage: Bilingual labels (JP above EN), decorative katakana accents, section subtitles. Weights: 400 (body), 700 (labels), 900 (display).
              </div>
            </div>

            <div style={{ marginTop: 20 }}>
              <div style={S.label}>TYPE SCALE タイプスケール</div>
              <div style={{ ...S.card, padding: 0 }}>
                {[
                  { name: "mega",  size: 48, ex: "64px — Countdown splash" },
                  { name: "data",  size: 32, ex: "32px — Big number readouts" },
                  { name: "3xl",   size: 32, ex: "40px — Hero text" },
                  { name: "2xl",   size: 28, ex: "28px — Page titles" },
                  { name: "xl",    size: 20, ex: "20px — Section headers" },
                  { name: "lg",    size: 16, ex: "16px — Emphasized body" },
                  { name: "base",  size: 14, ex: "14px — Body text (default)" },
                  { name: "sm",    size: 12, ex: "12px — Captions, metadata" },
                  { name: "xs",    size: 10, ex: "10px — Axis labels, fine print" },
                ].map((row, i) => (
                  <div key={row.name} style={{
                    display: "flex", alignItems: "baseline", gap: 12, padding: "8px 16px",
                    borderBottom: i < 8 ? `1px solid ${TOKENS.colors.grid.line}` : "none",
                  }}>
                    <span style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted, width: 40 }}>{row.name}</span>
                    <span style={{ fontFamily: TOKENS.type.display, fontSize: Math.min(row.size, 32), color: t.primary, letterSpacing: "0.08em", textTransform: "uppercase" }}>
                      Ag
                    </span>
                    <span style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>{row.ex}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* ─── 04: COMPONENTS ────────────────────────────────── */}
        {activeSection === "components" && (
          <section>
            <SectionHeader en="COMPONENTS" jp="コンポーネント" num="04" color={t.primary} />

            {/* Buttons */}
            <div style={S.label}>BUTTONS ボタン</div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 20 }}>
              {[
                { label: "PRIMARY 実行", bg: t.primary, color: TOKENS.colors.text.inverse, border: t.primary },
                { label: "SECONDARY", bg: "transparent", color: t.primary, border: t.primary },
                { label: "GHOST", bg: "transparent", color: TOKENS.colors.text.secondary, border: TOKENS.colors.grid.strong },
                { label: "DANGER 危険", bg: TOKENS.colors.status.danger, color: "#fff", border: TOKENS.colors.status.danger },
              ].map((btn, i) => (
                <button key={i} style={{
                  background: btn.bg, color: btn.color,
                  border: `${TOKENS.borders.normal}px solid ${btn.border}`,
                  borderRadius: TOKENS.radii.sm,
                  fontFamily: TOKENS.type.body, fontSize: 12, letterSpacing: "0.08em",
                  textTransform: "uppercase", padding: "8px 20px",
                  cursor: "pointer",
                }}>
                  {btn.label}
                </button>
              ))}
            </div>

            {/* Status badges */}
            <div style={S.label}>STATUS BADGES ステータスバッジ</div>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap", marginBottom: 20 }}>
              {[
                { label: "ACTIVE", jp: "稼働中", color: TOKENS.colors.status.ok },
                { label: "WARNING", jp: "警告", color: TOKENS.colors.status.caution },
                { label: "CRITICAL", jp: "危険", color: TOKENS.colors.status.danger },
                { label: "LOCKED", jp: "ロック", color: t.primary },
                { label: "INFO", jp: "情報", color: TOKENS.colors.status.info },
              ].map((b, i) => (
                <div key={i} style={{
                  background: `${b.color}18`, border: `1px solid ${b.color}`,
                  borderRadius: TOKENS.radii.sm, padding: "4px 12px",
                  display: "inline-flex", alignItems: "center", gap: 8,
                }}>
                  <PulsingDot color={b.color} size={6} />
                  <span style={{ fontFamily: TOKENS.type.body, fontSize: 11, color: b.color, letterSpacing: "0.08em" }}>
                    {b.label}
                  </span>
                  <span style={{ fontFamily: TOKENS.type.jp, fontSize: 10, color: `${b.color}88` }}>
                    {b.jp}
                  </span>
                </div>
              ))}
            </div>

            {/* Panel / Card */}
            <div style={S.label}>PANEL パネル</div>
            <div style={{
              background: TOKENS.colors.bg.surface,
              border: `1px solid ${t.primary}44`,
              borderRadius: TOKENS.radii.sm,
              marginBottom: 20,
              overflow: "hidden",
            }}>
              <div style={{
                background: `${t.primary}15`, borderBottom: `1px solid ${t.primary}44`,
                padding: "8px 16px", display: "flex", justifyContent: "space-between", alignItems: "center",
              }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Crosshairs color={t.primary} />
                  <span style={{ fontFamily: TOKENS.type.display, fontSize: 13, letterSpacing: "0.12em", color: t.primary }}>
                    SYSTEM STATUS
                  </span>
                  <span style={{ fontFamily: TOKENS.type.jp, fontSize: 11, color: TOKENS.colors.text.muted }}>
                    システム状態
                  </span>
                </div>
                <span style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>
                  PANEL-001
                </span>
              </div>
              <GridBg style={{ padding: 16 }}>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 }}>
                  {[
                    { label: "MELCHIOR", jp: "メルキオール", val: "ONLINE", color: TOKENS.colors.status.ok },
                    { label: "BALTHASAR", jp: "バルタザール", val: "STANDBY", color: TOKENS.colors.status.caution },
                    { label: "CASPER", jp: "カスパー", val: "OFFLINE", color: TOKENS.colors.status.danger },
                  ].map((m, i) => (
                    <div key={i} style={{ textAlign: "center" }}>
                      <div style={{ fontFamily: TOKENS.type.display, fontSize: 14, letterSpacing: "0.1em", color: TOKENS.colors.text.primary }}>{m.label}</div>
                      <div style={{ fontFamily: TOKENS.type.jp, fontSize: 10, color: TOKENS.colors.text.muted }}>{m.jp}</div>
                      <div style={{
                        fontFamily: TOKENS.type.data, fontSize: 12, color: m.color,
                        marginTop: 6, padding: "3px 8px",
                        background: `${m.color}15`, border: `1px solid ${m.color}44`,
                        borderRadius: TOKENS.radii.sm, display: "inline-block",
                      }}>
                        {m.val === "OFFLINE" ? <BlinkingText>{m.val}</BlinkingText> : m.val}
                      </div>
                    </div>
                  ))}
                </div>
                <HazardStripe type="green" style={{ marginTop: 16, opacity: 0.4 }} height={8} />
              </GridBg>
            </div>

            {/* Data Table */}
            <div style={S.label}>DATA TABLE データテーブル</div>
            <div style={{
              border: `1px solid ${TOKENS.colors.grid.strong}`, borderRadius: TOKENS.radii.sm,
              overflow: "hidden", marginBottom: 20,
            }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ background: `${t.primary}10`, borderBottom: `1px solid ${t.primary}44` }}>
                    {["UNIT ユニット", "PILOT パイロット", "STATUS", "SYNC %"].map((h, i) => (
                      <th key={i} style={{
                        fontFamily: TOKENS.type.body, fontSize: 10, letterSpacing: "0.1em",
                        textTransform: "uppercase", color: t.primary, padding: "8px 12px",
                        textAlign: "left",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    { unit: "EVA-00", pilot: "AYANAMI REI", status: "STANDBY", sync: "67.3", statusColor: TOKENS.colors.status.caution },
                    { unit: "EVA-01", pilot: "IKARI SHINJI", status: "ACTIVE", sync: "94.1", statusColor: TOKENS.colors.status.ok },
                    { unit: "EVA-02", pilot: "SORYU ASUKA", status: "DAMAGED", sync: "---", statusColor: TOKENS.colors.status.danger },
                  ].map((row, i) => (
                    <tr key={i} style={{ borderBottom: `1px solid ${TOKENS.colors.grid.line}` }}>
                      <td style={{ padding: "8px 12px", fontFamily: TOKENS.type.data, fontSize: 13, color: t.secondary }}>{row.unit}</td>
                      <td style={{ padding: "8px 12px", fontFamily: TOKENS.type.body, fontSize: 12, color: TOKENS.colors.text.primary }}>{row.pilot}</td>
                      <td style={{ padding: "8px 12px", fontFamily: TOKENS.type.data, fontSize: 11, color: row.statusColor }}>
                        {row.status === "DAMAGED" ? <BlinkingText>{row.status}</BlinkingText> : row.status}
                      </td>
                      <td style={{ padding: "8px 12px", fontFamily: TOKENS.type.data, fontSize: 13, color: t.primary }}>{row.sync}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Alert Banner */}
            <div style={S.label}>ALERT BANNERS アラートバナー</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { type: "DANGER", jp: "警報", msg: "AT FIELD PATTERN: BLOOD TYPE BLUE", color: TOKENS.colors.status.danger },
                { type: "CAUTION", jp: "注意", msg: "APPROACHING ACTIVATION LIMITS", color: TOKENS.colors.status.caution },
                { type: "INFO", jp: "通知", msg: "NEUROLOGICAL LINK ESTABLISHED", color: t.secondary },
              ].map((a, i) => (
                <div key={i} style={{
                  display: "flex", alignItems: "center", gap: 12,
                  background: `${a.color}08`, border: `1px solid ${a.color}44`,
                  borderLeft: `3px solid ${a.color}`,
                  borderRadius: TOKENS.radii.sm, padding: "10px 16px",
                }}>
                  <div style={{
                    fontFamily: TOKENS.type.display, fontSize: 11, letterSpacing: "0.12em",
                    color: a.color, background: `${a.color}20`, padding: "2px 8px",
                    borderRadius: TOKENS.radii.sm, whiteSpace: "nowrap",
                  }}>
                    {a.type}
                    <span style={{ fontFamily: TOKENS.type.jp, fontSize: 10, marginLeft: 6, opacity: 0.7 }}>{a.jp}</span>
                  </div>
                  <span style={{ fontFamily: TOKENS.type.data, fontSize: 12, color: TOKENS.colors.text.primary }}>
                    {a.msg}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}

        {/* ─── 05: LAYOUT PATTERNS ───────────────────────────── */}
        {activeSection === "patterns" && (
          <section>
            <SectionHeader en="LAYOUT PATTERNS" jp="レイアウト" num="05" color={t.primary} />

            <div style={S.label}>GRID BACKGROUND + CROSSHAIRS グリッド背景</div>
            <GridBg style={{ ...S.card, height: 160, position: "relative", marginBottom: 20 }}>
              {/* Crosshairs at intersections */}
              {[
                [48, 48], [96, 48], [144, 48], [192, 48],
                [48, 96], [96, 96], [144, 96], [192, 96],
                [48, 144], [96, 144], [144, 144], [192, 144],
              ].map(([x, y], i) => (
                <div key={i} style={{ position: "absolute", left: x - 7, top: y - 7 }}>
                  <Crosshairs color={`${t.primary}33`} />
                </div>
              ))}
              <div style={{ position: "absolute", bottom: 8, left: 16 }}>
                <AxisRuler count={15} color={t.primary} />
              </div>
              <div style={{ position: "absolute", top: 8, right: 16, fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>
                GRID: 48px / TICK MARKS AT INTERSECTIONS
              </div>
            </GridBg>

            <div style={S.label}>PANEL HEADER PATTERN パネルヘッダー</div>
            <p style={{ color: TOKENS.colors.text.secondary, fontSize: 12, marginBottom: 8 }}>
              Every panel follows: colored top border or header bar with crosshair icon, JP subtitle, panel ID. Content sits on grid background.
            </p>
            <div style={{ fontFamily: TOKENS.type.data, ...S.code, marginBottom: 20 }}>
{`┌─ [+] SECTION TITLE セクション名 ──────── PANEL-ID ─┐
│  ┌─ grid background (48px) ──────────────────────┐  │
│  │  +     +     +     +     +     +     +        │  │
│  │                                               │  │
│  │  +     +     +     +     +     +     +        │  │
│  │           [ content area ]                    │  │
│  │  +     +     +     +     +     +     +        │  │
│  └───────────────────────────────────────────────┘  │
│  ═══ hazard stripe (optional) ═════════════════════ │
└─────────────────────────────────────────────────────`}
            </div>

            <div style={S.label}>AXIS RULER 軸ルーラー</div>
            <div style={{ ...S.card, marginBottom: 20 }}>
              <AxisRuler count={30} color={t.primary} />
              <div style={{ marginTop: 12 }}>
                <AxisRuler count={30} color={t.secondary} />
              </div>
            </div>

            <div style={S.label}>BILINGUAL LABEL PATTERN ラベルパターン</div>
            <div style={{ ...S.card }}>
              <p style={{ color: TOKENS.colors.text.secondary, fontSize: 12, marginBottom: 12 }}>
                Labels always show Japanese above or beside English. JP is smaller, secondary color. EN is primary or accent.
              </p>
              <div style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
                <div>
                  <div style={{ fontFamily: TOKENS.type.jp, fontSize: 10, color: TOKENS.colors.text.muted }}>三人目の子供</div>
                  <div style={{ fontFamily: TOKENS.type.display, fontSize: 28, color: t.primary, letterSpacing: "0.08em" }}>01</div>
                  <div style={{ fontFamily: TOKENS.type.body, fontSize: 11, color: TOKENS.colors.text.secondary, letterSpacing: "0.08em" }}>THIRD CHILD</div>
                </div>
                <div>
                  <div style={{ fontFamily: TOKENS.type.jp, fontSize: 10, color: TOKENS.colors.text.muted }}>経過時間</div>
                  <div style={{ fontFamily: TOKENS.type.data, fontSize: 28, color: t.secondary }}>120 M — 7200 S</div>
                  <div style={{ fontFamily: TOKENS.type.body, fontSize: 11, color: TOKENS.colors.text.secondary, letterSpacing: "0.08em" }}>ELAPSED TIME</div>
                </div>
                <div style={{ background: TOKENS.colors.status.danger, padding: "6px 16px" }}>
                  <div style={{ fontFamily: TOKENS.type.jp, fontSize: 10, color: "rgba(255,255,255,0.7)" }}>状態</div>
                  <div style={{ fontFamily: TOKENS.type.display, fontSize: 20, color: "#fff", letterSpacing: "0.12em" }}>DAMAGED</div>
                  <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: "rgba(255,255,255,0.6)" }}>CONDITION RED</div>
                </div>
              </div>
            </div>
          </section>
        )}

        {/* ─── 06: ANIMATION ─────────────────────────────────── */}
        {activeSection === "animation" && (
          <section>
            <SectionHeader en="ANIMATION" jp="アニメーション" num="06" color={t.primary} />

            <div style={S.label}>WAVEFORM 波形</div>
            <div style={{ ...S.card, marginBottom: 16 }}>
              <WaveformSVG color={t.primary} height={60} />
              <WaveformSVG color={t.secondary} height={50} />
              <WaveformSVG color={t.tertiary} height={40} />
            </div>

            <div style={S.label}>DATA COUNTER カウンター</div>
            <div style={{ ...S.card, display: "flex", gap: 32, flexWrap: "wrap", marginBottom: 16 }}>
              <div>
                <DataCounter target={223229} style={{ fontFamily: TOKENS.type.data, fontSize: 36, color: t.primary }} />
                <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>TARGET VALUE</div>
              </div>
              <div>
                <DataCounter target={99} suffix="%" style={{ fontFamily: TOKENS.type.data, fontSize: 36, color: t.secondary }} />
                <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>SYNC RATE</div>
              </div>
              <div>
                <DataCounter target={7200} suffix=" sec" style={{ fontFamily: TOKENS.type.data, fontSize: 36, color: TOKENS.colors.status.caution }} />
                <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>TIME REMAINING</div>
              </div>
            </div>

            <div style={S.label}>BLINKING TEXT 点滅テキスト</div>
            <div style={{ ...S.card, marginBottom: 16, display: "flex", gap: 24, flexWrap: "wrap" }}>
              <BlinkingText style={{ fontFamily: TOKENS.type.display, fontSize: 20, color: TOKENS.colors.status.danger, letterSpacing: "0.12em" }}>
                WARNING
              </BlinkingText>
              <BlinkingText style={{ fontFamily: TOKENS.type.data, fontSize: 16, color: TOKENS.colors.status.caution }}>
                APPROACHING LIMITS
              </BlinkingText>
              <span style={{ fontFamily: TOKENS.type.data, fontSize: 14, color: t.primary }}>
                CURSOR<BlinkingText>_</BlinkingText>
              </span>
            </div>

            <div style={S.label}>TYPEWRITER タイプライター</div>
            <div style={{ ...S.card, marginBottom: 16 }}>
              <TypewriterText
                text="INITIALIZING NERV SYSTEM... MAGI CONSENSUS ACHIEVED. ALL UNITS STANDING BY."
                style={{ fontFamily: TOKENS.type.data, fontSize: 14, color: t.primary }}
              />
            </div>

            <div style={S.label}>CASCADE LIST カスケード</div>
            <div style={{ ...S.card, marginBottom: 16 }}>
              <CascadeList stagger={80} items={[
                <span style={{ fontFamily: TOKENS.type.data, fontSize: 13, color: t.primary }}>
                  <span style={S.tick(t.primary)} /> LINK A — 01 ............ <span style={{ color: TOKENS.colors.status.ok }}>CONNECTED</span>
                </span>,
                <span style={{ fontFamily: TOKENS.type.data, fontSize: 13, color: t.primary }}>
                  <span style={S.tick(t.primary)} /> LINK A — 02 ............ <span style={{ color: TOKENS.colors.status.ok }}>CONNECTED</span>
                </span>,
                <span style={{ fontFamily: TOKENS.type.data, fontSize: 13, color: t.primary }}>
                  <span style={S.tick(t.primary)} /> LINK A — 03 ............ <span style={{ color: TOKENS.colors.status.caution }}>PENDING</span>
                </span>,
                <span style={{ fontFamily: TOKENS.type.data, fontSize: 13, color: t.primary }}>
                  <span style={S.tick(t.primary)} /> LINK A — 04 ............ <span style={{ color: TOKENS.colors.status.danger }}><BlinkingText>FAILED</BlinkingText></span>
                </span>,
                <span style={{ fontFamily: TOKENS.type.data, fontSize: 13, color: t.primary }}>
                  <span style={S.tick(t.primary)} /> LINK A — 05 ............ <span style={{ color: TOKENS.colors.status.ok }}>CONNECTED</span>
                </span>,
              ]} />
            </div>

            <div style={S.label}>PULSING DOT パルスドット</div>
            <div style={{ ...S.card, display: "flex", gap: 24, alignItems: "center" }}>
              {[t.primary, t.secondary, t.tertiary, TOKENS.colors.status.ok, TOKENS.colors.status.danger, TOKENS.colors.status.caution].map((c, i) => (
                <PulsingDot key={i} color={c} size={12} />
              ))}
            </div>
          </section>
        )}

        {/* ─── 07: IMPLEMENTATION ────────────────────────────── */}
        {activeSection === "code" && (
          <section>
            <SectionHeader en="IMPLEMENTATION" jp="実装コード" num="07" color={t.primary} />

            <div style={{ display: "flex", gap: 0, marginBottom: 0, borderBottom: `1px solid ${TOKENS.colors.grid.line}` }}>
              {[
                { id: "tailwind", label: "TAILWIND CONFIG" },
                { id: "css", label: "CSS VARIABLES" },
                { id: "tokens", label: "JS TOKENS" },
              ].map(tab => (
                <button key={tab.id} onClick={() => setCodeTab(tab.id)} style={{
                  background: codeTab === tab.id ? `${t.primary}15` : "transparent",
                  border: "none", borderBottom: codeTab === tab.id ? `2px solid ${t.primary}` : "2px solid transparent",
                  color: codeTab === tab.id ? t.primary : TOKENS.colors.text.muted,
                  fontFamily: TOKENS.type.body, fontSize: 11, letterSpacing: "0.06em",
                  padding: "8px 16px", cursor: "pointer",
                }}>
                  {tab.label}
                </button>
              ))}
            </div>

            {codeTab === "tailwind" && (
              <pre style={{ ...S.code, marginTop: 12 }}>
{`// tailwind.config.js → theme.extend
{
  colors: {
    nerv: {
      void: '#000000',
      base: '#0a0a0f',
      surface: '#111118',
      elevated: '#1a1a24',
      primary: 'var(--nerv-primary, #ff8800)',
      'primary-muted': 'var(--nerv-primary-muted, #cc6600)',
      secondary: 'var(--nerv-secondary, #00ddaa)',
      'secondary-muted': 'var(--nerv-secondary-muted, #009977)',
      tertiary: 'var(--nerv-tertiary, #ff3366)',
      danger: '#ff1a1a',
      'danger-dark': '#991111',
      caution: '#ffaa00',
      ok: '#00cc66',
      info: '#4488ff',
      grid: 'rgba(255,255,255,0.06)',
      'grid-strong': 'rgba(255,255,255,0.12)',
      tick: 'rgba(255,255,255,0.25)',
    },
    'nerv-text': {
      primary: '#e8e8f0',
      secondary: '#8888a0',
      muted: '#555566',
      inverse: '#0a0a0f',
    },
  },
  fontFamily: {
    'nerv-display': ["'Archivo Black'", 'Impact', 'sans-serif'],
    'nerv-body': ["'Space Mono'", 'monospace'],
    'nerv-data': ["'Share Tech Mono'", "'Orbitron'", 'monospace'],
    'nerv-jp': ["'Noto Sans JP'", 'sans-serif'],
  },
  fontSize: {
    'nerv-xs': ['0.625rem', { lineHeight: '1rem', letterSpacing: '0.08em' }],
    'nerv-sm': ['0.75rem', { lineHeight: '1.125rem', letterSpacing: '0.06em' }],
    'nerv-base': ['0.875rem', { lineHeight: '1.375rem', letterSpacing: '0.04em' }],
    'nerv-lg': ['1rem', { lineHeight: '1.5rem', letterSpacing: '0.03em' }],
    'nerv-xl': ['1.25rem', { lineHeight: '1.75rem', letterSpacing: '0.02em' }],
    'nerv-2xl': ['1.75rem', { lineHeight: '2rem', letterSpacing: '0.01em' }],
    'nerv-3xl': ['2.5rem', { lineHeight: '2.75rem', letterSpacing: '-0.01em' }],
    'nerv-data': ['2rem', { lineHeight: '2.25rem', letterSpacing: '0.05em' }],
    'nerv-mega': ['4rem', { lineHeight: '4rem', letterSpacing: '-0.02em' }],
  },
  borderRadius: {
    nerv: '2px',
  },
  animation: {
    'nerv-pulse': 'nervPulse 2s ease-in-out infinite',
    'nerv-blink': 'nervBlink 1s step-end infinite',
    'nerv-cascade': 'nervCascade 0.6s ease-out forwards',
    'nerv-scanline': 'nervScanline 8s linear infinite',
  },
  keyframes: {
    nervPulse: {
      '0%, 100%': { opacity: '1' },
      '50%': { opacity: '0.4' },
    },
    nervBlink: {
      '0%, 100%': { opacity: '1' },
      '50%': { opacity: '0' },
    },
    nervCascade: {
      from: { opacity: '0', transform: 'translateY(-8px)' },
      to: { opacity: '1', transform: 'translateY(0)' },
    },
    nervScanline: {
      from: { transform: 'translateY(-100%)' },
      to: { transform: 'translateY(100vh)' },
    },
  },
}`}
              </pre>
            )}

            {codeTab === "css" && (
              <pre style={{ ...S.code, marginTop: 12 }}>
{`:root {
  --nerv-primary: #ff8800;
  --nerv-primary-muted: #cc6600;
  --nerv-primary-glow: rgba(255,136,0,0.15);
  --nerv-secondary: #00ddaa;
  --nerv-secondary-muted: #009977;
  --nerv-secondary-glow: rgba(0,221,170,0.12);
  --nerv-tertiary: #ff3366;
  --nerv-tertiary-muted: #cc2255;
}

[data-theme="magi"] {
  --nerv-primary: #00ff88;
  --nerv-primary-muted: #00cc66;
  --nerv-primary-glow: rgba(0,255,136,0.12);
  --nerv-secondary: #ff6600;
  --nerv-secondary-muted: #cc5500;
  --nerv-secondary-glow: rgba(255,102,0,0.10);
  --nerv-tertiary: #ffdd00;
  --nerv-tertiary-muted: #ccaa00;
}

[data-theme="seele"] {
  --nerv-primary: #cc3333;
  --nerv-primary-muted: #991a1a;
  --nerv-primary-glow: rgba(204,51,51,0.12);
  --nerv-secondary: #8888aa;
  --nerv-secondary-muted: #666688;
  --nerv-secondary-glow: rgba(136,136,170,0.08);
  --nerv-tertiary: #ffcc00;
  --nerv-tertiary-muted: #cc9900;
}

[data-theme="terminal"] {
  --nerv-primary: #00ccff;
  --nerv-primary-muted: #0099cc;
  --nerv-primary-glow: rgba(0,204,255,0.12);
  --nerv-secondary: #88ff44;
  --nerv-secondary-muted: #66cc22;
  --nerv-secondary-glow: rgba(136,255,68,0.10);
  --nerv-tertiary: #ff4488;
  --nerv-tertiary-muted: #cc2266;
}

/* Scanline overlay */
.nerv-scanlines::after {
  content: '';
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 9999;
  background: repeating-linear-gradient(
    0deg, transparent, transparent 2px,
    rgba(0,0,0,0.04) 2px, rgba(0,0,0,0.04) 4px
  );
}

/* Grid background */
.nerv-grid {
  background-image:
    linear-gradient(rgba(255,255,255,0.06) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.06) 1px, transparent 1px);
  background-size: 48px 48px;
}

/* Hazard stripes */
.nerv-hazard-green {
  background: repeating-linear-gradient(
    -45deg, #22bb44 0 8px, #111118 8px 16px);
}
.nerv-hazard-red {
  background: repeating-linear-gradient(
    -45deg, #cc2200 0 8px, #ddaa00 8px 16px);
}

/* Glow effect for focused/active elements */
.nerv-glow {
  box-shadow: 0 0 20px var(--nerv-primary-glow),
              inset 0 0 20px var(--nerv-primary-glow);
}`}
              </pre>
            )}

            {codeTab === "tokens" && (
              <pre style={{ ...S.code, marginTop: 12 }}>
{`// tokens.ts — import into any project
export const NERV_TOKENS = ${JSON.stringify(TOKENS, null, 2)};`}
              </pre>
            )}

            <div style={{ marginTop: 24 }}>
              <div style={S.label}>COMPONENT PATTERN CHEATSHEET パターン早見表</div>
              <pre style={{ ...S.code }}>
{`// Panel with header
<div className="bg-nerv-surface border border-nerv-grid-strong rounded-nerv">
  <div className="bg-[var(--nerv-primary-glow)] border-b border-nerv-primary/25
                  px-4 py-2 flex justify-between items-center">
    <span className="font-nerv-display text-nerv-primary text-sm
                     tracking-[0.12em] uppercase">
      SECTION TITLE
    </span>
    <span className="font-nerv-jp text-nerv-text-muted text-xs">
      セクション名
    </span>
  </div>
  <div className="nerv-grid p-4">
    {/* content */}
  </div>
</div>

// Status badge
<div className="inline-flex items-center gap-2 px-3 py-1
                bg-nerv-ok/10 border border-nerv-ok rounded-nerv">
  <span className="w-1.5 h-1.5 rounded-full bg-nerv-ok animate-nerv-pulse" />
  <span className="font-nerv-body text-nerv-ok text-xs tracking-wider">
    ACTIVE
  </span>
  <span className="font-nerv-jp text-nerv-ok/50 text-[10px]">
    稼働中
  </span>
</div>

// Data readout
<div>
  <span className="font-nerv-jp text-nerv-text-muted text-[10px]">
    同期率
  </span>
  <div className="font-nerv-data text-nerv-data text-nerv-primary
                  tabular-nums tracking-wider">
    094.1
  </div>
  <span className="font-nerv-body text-nerv-text-secondary text-xs
                   tracking-[0.08em] uppercase">
    SYNC RATE
  </span>
</div>

// Bilingual label (JP above EN)
<div>
  <span className="font-nerv-jp text-nerv-text-muted text-[10px] block">
    警告
  </span>
  <span className="font-nerv-display text-nerv-danger text-xl
                   tracking-[0.12em]">
    WARNING
  </span>
</div>

// Alert banner
<div className="flex items-center gap-3 bg-nerv-danger/5
                border border-nerv-danger/25 border-l-[3px]
                border-l-nerv-danger rounded-nerv px-4 py-2.5">
  <span className="font-nerv-display text-nerv-danger text-xs
                   tracking-[0.12em] bg-nerv-danger/10 px-2 py-0.5
                   rounded-nerv shrink-0">
    DANGER <span className="font-nerv-jp opacity-70">危険</span>
  </span>
  <span className="font-nerv-data text-nerv-text-primary text-xs">
    PATTERN BLUE DETECTED
  </span>
</div>`}
              </pre>
            </div>
          </section>
        )}

        {/* ─── FOOTER ────────────────────────────────────────── */}
        <footer style={{
          marginTop: 48, padding: "20px 0", borderTop: `1px solid ${TOKENS.colors.grid.strong}`,
          display: "flex", justifyContent: "space-between", alignItems: "center",
          flexWrap: "wrap", gap: 12,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Crosshairs color={t.primary} />
            <span style={{ fontFamily: TOKENS.type.body, fontSize: 11, color: TOKENS.colors.text.muted, letterSpacing: "0.06em" }}>
              PYNCH LABS LLC
            </span>
            <span style={{ fontFamily: TOKENS.type.jp, fontSize: 10, color: TOKENS.colors.text.muted }}>
              設計システム v1.0.0
            </span>
          </div>
          <div style={{ fontFamily: TOKENS.type.data, fontSize: 10, color: TOKENS.colors.text.muted }}>
            NERV DESIGN SYSTEM — ALL SYSTEMS NOMINAL
            <PulsingDot color={TOKENS.colors.status.ok} size={6} />
          </div>
        </footer>
        <div style={{ height: 32 }} />
      </div>
    </div>
  );
}
