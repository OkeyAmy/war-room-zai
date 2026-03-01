"use client";

import { useEffect, useState } from "react";

// --- Room Intelligence ---

export interface IntelligenceItem {
  id: string;
  label: string;
  value: string;
  trend: "up" | "down" | "neutral";
  critical?: boolean;
}

export interface IntelAlert {
  id: string;
  type: "CONTRADICTION" | "ALLIANCE" | "BLIND_SPOT";
  text: string;
  timestamp: string;
  meta?: string;
}

export interface TrustScore {
  agentName: string;
  score: number;
}

interface RoomIntelligenceProps {
  items?: IntelligenceItem[]; // Legacy support or simplified view
  alerts?: IntelAlert[];
  trustScores?: TrustScore[];
}

export function RoomIntelligence({ items = [], alerts = [], trustScores = [] }: RoomIntelligenceProps) {
  const [open, setOpen] = useState(true);

  return (
    <div
      style={{
        background: "#0D1117",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: "36px",
          padding: "0 12px",
          borderBottom: open ? "1px solid rgba(180,77,255,0.25)" : "none",
          background: "rgba(180,77,255,0.04)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setOpen((o) => !o)}
      >
        <span
          style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 600,
            fontSize: "11px",
            color: "#B44DFF",
            letterSpacing: "0.12em",
          }}
        >
          ROOM INTELLIGENCE
        </span>
        <span style={{ color: "#4A5568", fontSize: "10px", transition: "transform 150ms ease", display: "inline-block", transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}>▼</span>
      </div>

      {open && <div className="wr-scrollbar" style={{ overflowY: "auto", maxHeight: "250px" }}>
        {/* Alerts Section */}
        {alerts.length > 0 && alerts.map((alert) => (
          <div
            key={alert.id}
            style={{
              padding: "8px 10px 8px 12px",
              borderBottom: "1px solid #1E2D3D",
              borderLeft: "2px solid",
              borderLeftColor:
                alert.type === "CONTRADICTION"
                  ? "#FF6B00"
                  : alert.type === "ALLIANCE"
                    ? "#4A9EFF"
                    : "#B44DFF",
              background:
                alert.type === "CONTRADICTION"
                  ? "rgba(255,107,0,0.05)"
                  : alert.type === "ALLIANCE"
                    ? "rgba(74,158,255,0.05)"
                    : "rgba(180,77,255,0.05)",
            }}
          >
            <div
              style={{
                fontFamily: "'Barlow Condensed', sans-serif",
                fontWeight: 600,
                fontSize: "10px",
                letterSpacing: "0.08em",
                color:
                  alert.type === "CONTRADICTION"
                    ? "#FF6B00"
                    : alert.type === "ALLIANCE"
                      ? "#4A9EFF"
                      : "#B44DFF",
                marginBottom: "2px",
              }}
            >
              {alert.type === "CONTRADICTION"
                ? "⚠️ CONTRADICTION"
                : alert.type === "ALLIANCE"
                  ? "🤝 ALLIANCE FORMING"
                  : "🎯 CRITICAL UNASKED"}
            </div>
            <div
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontWeight: 400,
                fontSize: "10px",
                color: "#E8EDF2",
                lineHeight: 1.4,
              }}
            >
              {alert.text}
            </div>
            <div
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontWeight: 400,
                fontSize: "9px",
                color: "#4A5568",
                marginTop: "4px",
              }}
            >
              {alert.timestamp} {alert.meta ? `• ${alert.meta}` : ""}
            </div>
          </div>
        ))}

        {/* Intelligence Items (Simplified) */}
        {items.length > 0 && items.map((item) => (
          <div
            key={item.id}
            style={{
              padding: "8px 12px",
              borderBottom: "1px solid #1E2D3D",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "#8A9BB0" }}>{item.label}</span>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span style={{ fontFamily: "'Orbitron', sans-serif", fontSize: "11px", fontWeight: 700, color: item.critical ? "#FF2D2D" : "#E8EDF2" }}>
                {item.value}
              </span>
              <span style={{ fontSize: "10px", color: item.trend === 'up' ? '#00C896' : item.trend === 'down' ? '#FF2D2D' : '#4A5568' }}>
                {item.trend === 'up' ? '↑' : item.trend === 'down' ? '↓' : '→'}
              </span>
            </div>
          </div>
        ))}

        {/* Trust Scores Section */}
        {trustScores.length > 0 && (
          <div style={{ padding: "6px 10px", borderTop: "1px solid #1E2D3D" }}>
            <div
              style={{
                fontFamily: "'Barlow Condensed', sans-serif",
                fontWeight: 600,
                fontSize: "9px",
                color: "#4A5568",
                letterSpacing: "0.12em",
                marginBottom: "8px",
              }}
            >
              AGENT TRUST SCORES
            </div>
            {trustScores.map((ts) => (
              <div
                key={ts.agentName}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  marginBottom: "5px",
                }}
              >
                <span
                  style={{
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontWeight: 400,
                    fontSize: "9px",
                    color: "#8A9BB0",
                    width: "60px",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                  }}
                >
                  {ts.agentName}
                </span>
                <div
                  style={{
                    flex: 1,
                    height: "3px",
                    background: "#111820",
                    borderRadius: "1px",
                  }}
                >
                  <div
                    style={{
                      height: "100%",
                      width: `${ts.score}%`,
                      borderRadius: "1px",
                      background:
                        ts.score > 75 ? "#00C896" : ts.score > 50 ? "#FFB800" : "#FF2D2D",
                      transition: "width 500ms ease",
                    }}
                  />
                </div>
                <span
                  style={{
                    fontFamily: "'Orbitron', monospace",
                    fontWeight: 700,
                    fontSize: "10px",
                    color: ts.score > 75 ? "#00C896" : ts.score > 50 ? "#FFB800" : "#FF2D2D",
                    width: "30px",
                    textAlign: "right",
                  }}
                >
                  {ts.score}%
                </span>
              </div>
            ))}
          </div>
        )}
      </div>}
    </div>
  );
}

// --- Crisis Posture ---

export type PostureLevel = 1 | 2 | 3 | 4 | 5;

export interface PostureAxis {
  label: string;
  value: number; // 0-100
  status: "CONT" | "ELEV" | "HIGH" | "CRIT";
  subMetric: string;
  trend: "UP" | "DOWN" | "STABLE";
}

interface CrisisPostureProps {
  level?: PostureLevel;
  label?: string;
  detail?: string;
  axes?: PostureAxis[];
}

export function CrisisPosture({ level = 1, label = "", detail = "", axes = [] }: CrisisPostureProps) {
  const [open, setOpen] = useState(true);

  // Mock axes if none provided to follow design spec
  const displayAxes: PostureAxis[] = axes.length > 0 ? axes : [
    { label: "PUBLIC EXPOSURE", value: level * 20 - 10, status: level >= 4 ? "CRIT" : level >= 3 ? "HIGH" : "CONT", subMetric: "Viral velocity: RISING", trend: "UP" },
    { label: "LEGAL EXPOSURE", value: level * 15, status: level >= 5 ? "CRIT" : level >= 3 ? "ELEV" : "CONT", subMetric: "Liability scan active", trend: "STABLE" },
    { label: "INTERNAL STABILITY", value: 100 - level * 10, status: level >= 4 ? "HIGH" : "CONT", subMetric: "Team alignment nominal", trend: "DOWN" },
  ];

  return (
    <div
      style={{
        background: "#0D1117",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: "36px",
          padding: "0 12px",
          borderBottom: open ? "1px solid #1E2D3D" : "none",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setOpen((o) => !o)}
      >
        <span
          style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 600,
            fontSize: "11px",
            color: "#8A9BB0",
            letterSpacing: "0.12em",
          }}
        >
          CRISIS POSTURE
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          {label && (
            <span
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: "9px",
                padding: "2px 6px",
                background: "rgba(255,107,0,0.2)",
                color: "#FF6B00",
                border: "1px solid #FF6B00",
              }}
            >
              {label}
            </span>
          )}
          <span style={{ color: "#4A5568", fontSize: "10px", transition: "transform 150ms ease", display: "inline-block", transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}>▼</span>
        </div>
      </div>

      {open && <div className="wr-scrollbar" style={{ flex: 1, overflowY: "auto", maxHeight: "200px" }}>
        {displayAxes.map((axis) => {
          const statusColor =
            axis.status === "CRIT"
              ? "#FF2D2D"
              : axis.status === "HIGH"
                ? "#FF6B00"
                : axis.status === "ELEV"
                  ? "#FFB800"
                  : "#00C896";

          return (
            <div
              key={axis.label}
              style={{
                padding: "8px 12px",
                borderBottom: "1px solid #1E2D3D",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "4px",
                }}
              >
                <span
                  style={{
                    fontFamily: "'Barlow Condensed', sans-serif",
                    fontWeight: 600,
                    fontSize: "10px",
                    letterSpacing: "0.08em",
                    color: "#8A9BB0",
                  }}
                >
                  {axis.label}
                </span>
                <span
                  style={{
                    fontFamily: "'Barlow Condensed', sans-serif",
                    fontWeight: 600,
                    fontSize: "9px",
                    padding: "2px 6px",
                    background: `${statusColor}33`,
                    border: `1px solid ${statusColor}`,
                    color: statusColor,
                  }}
                >
                  {axis.status}
                </span>
              </div>
              <div
                style={{
                  height: "5px",
                  background: "#111820",
                  margin: "4px 0",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${axis.value}%`,
                    background: `linear-gradient(90deg, ${statusColor}, ${statusColor}aa)`,
                    transition: "width 800ms ease",
                  }}
                />
              </div>
              <div
                style={{
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontWeight: 400,
                  fontSize: "9px",
                  color: "#4A5568",
                }}
              >
                {axis.subMetric} • {axis.trend === "UP" ? "↑ RISING" : axis.trend === "DOWN" ? "↓ FALLING" : "→ STABLE"}
              </div>
            </div>
          );
        })}
        {detail && (
          <div style={{ padding: "8px 12px", fontFamily: "'IBM Plex Mono', monospace", fontSize: "10px", color: "#8A9BB0", fontStyle: "italic" }}>
            {detail}
          </div>
        )}
      </div>}
    </div>
  );
}

// --- Resolution Score ---

export interface ScoreContributor {
  label: string;
  value: number;
  positive: boolean;
}

interface ResolutionScoreProps {
  score: number;
  delta?: number;
  contributors?: ScoreContributor[];
  trend?: "IMPROVING" | "FALLING" | "STABLE";
  targetText?: string;
  keyDriver?: string;
  nextEscalation?: string;
}

export function ResolutionScore({
  score,
  delta = 0,
  contributors = [],
  trend,
  targetText = "70+ to avoid fallout",
  keyDriver = "Team Alignment",
  nextEscalation = "04:59",
}: ResolutionScoreProps) {
  const [open, setOpen] = useState(true);
  const color =
    score >= 70
      ? "#00C896"
      : score >= 40
        ? "#FFB800"
        : score >= 20
          ? "#FF6B00"
          : "#FF2D2D";

  const statusLabel =
    score >= 70
      ? "RESOLVED"
      : score >= 40
        ? "RECOVERING"
        : score >= 20
          ? "CRITICAL"
          : "MELTDOWN";

  const displayTrend = trend || (delta > 0 ? "IMPROVING" : delta < 0 ? "FALLING" : "STABLE");

  return (
    <div
      style={{
        background: "#0D1117",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: "36px",
          padding: "0 12px",
          borderBottom: open ? "1px solid #1E2D3D" : "none",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
          cursor: "pointer",
          userSelect: "none",
        }}
        onClick={() => setOpen((o) => !o)}
      >
        <span
          style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 600,
            fontSize: "11px",
            color: "#8A9BB0",
            letterSpacing: "0.12em",
          }}
        >
          RESOLUTION SCORE
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "4px" }}>
            <div className="dot-live" style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#FF2D2D" }} />
            <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 600, fontSize: "10px", color: "#FF2D2D" }}>LIVE</span>
          </div>
          <span style={{ color: "#4A5568", fontSize: "10px", transition: "transform 150ms ease", display: "inline-block", transform: open ? "rotate(0deg)" : "rotate(-90deg)" }}>▼</span>
        </div>
      </div>

      {open && <div
        className="wr-scrollbar"
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "12px",
          maxHeight: "200px",
        }}
      >
        <div
          style={{
            fontFamily: "'Orbitron', sans-serif",
            fontWeight: 900,
            fontSize: "48px",
            letterSpacing: "-0.02em",
            color: color,
            textShadow: `0 0 10px ${color}66`,
            lineHeight: 1,
            marginBottom: "4px",
          }}
        >
          {score}
        </div>
        <div
          style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 700,
            fontSize: "12px",
            letterSpacing: "0.12em",
            color: color,
            textTransform: "uppercase",
            marginBottom: "4px",
          }}
        >
          {statusLabel}
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "6px",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "9px",
            color: "#4A5568",
          }}
        >
          <span>TREND:</span>
          <span style={{ color: color, fontWeight: 500 }}>
            {displayTrend === "IMPROVING" ? "↑ IMPROVING" : displayTrend === "FALLING" ? "↓ FALLING" : "→ STABLE"}
          </span>
        </div>

        {/* Contributors (Mini Grid) */}
        <div style={{ width: "100%", marginTop: "12px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "8px" }}>
          {contributors.map((c) => (
            <div key={c.label} style={{ border: "1px solid #1E2D3D", padding: "4px", borderRadius: "1px" }}>
              <div style={{ fontSize: "8px", color: "#4A5568", whiteSpace: "nowrap", overflow: "hidden" }}>{c.label.toUpperCase()}</div>
              <div style={{ fontSize: "10px", fontWeight: 700, color: c.positive ? "#00C896" : "#FF2D2D", fontFamily: "'Orbitron', sans-serif" }}>
                {c.positive ? '+' : ''}{c.value}%
              </div>
            </div>
          ))}
        </div>
      </div>}
    </div>
  );
}
