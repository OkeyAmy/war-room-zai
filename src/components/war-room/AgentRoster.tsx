"use client";

import { useState } from "react";

export type AgentStatus = "speaking" | "thinking" | "conflicted" | "listening" | "silent" | "dismissed";

export interface Agent {
  id: string;
  name: string;
  surname: string;
  role: string;
  status: AgentStatus;
  trustScore: number;
  lastWords?: string;
  conflictWith?: string;
  identityColor?: string;
  voiceName?: string;
}

interface AgentRosterProps {
  agents: Agent[];
  selectedAgentId: string | null;
  onSelectAgent: (id: string | null) => void;
  /** Called when the Chairman dismisses an agent via the stop icon */
  onDismissAgent?: (agentId: string, agentName: string) => void;
  /** Called when the Chairman silences an agent */
  onSilenceAgent?: (agentId: string, durationSeconds?: number) => void;
}

function SpeakingAnimation() {
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: "2px", height: "14px" }}>
      {[1, 2, 3, 4, 5, 6, 7].map((i) => (
        <div
          key={i}
          className={`wave-bar-${(i % 7) + 1}`}
          style={{ width: "2px", background: "#00E5FF", borderRadius: "1px", height: "100%" }}
        />
      ))}
    </div>
  );
}

/** Stop (dismiss) icon — a square inside a circle, styled as a soft warning */
function DismissIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style={{ pointerEvents: "none" }}>
      <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
      <rect x="5" y="5" width="6" height="6" rx="1" fill="currentColor" />
    </svg>
  );
}

export default function AgentRoster({
  agents,
  selectedAgentId,
  onSelectAgent,
  onDismissAgent,
  onSilenceAgent,
}: AgentRosterProps) {
  const [silenceHoveredId, setSilenceHoveredId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [dismissHoveredId, setDismissHoveredId] = useState<string | null>(null);
  const [dismissingId, setDismissingId] = useState<string | null>(null);

  const handleDismiss = (e: React.MouseEvent, agent: Agent) => {
    e.stopPropagation(); // don't select the agent when clicking dismiss
    if (dismissingId) return; // prevent double-click
    setDismissingId(agent.id);
    onDismissAgent?.(agent.id, agent.name);
    // Reset so the button doesn't get permanently stuck if re-rendered
    setTimeout(() => setDismissingId(null), 1500);
  };

  return (
    <div
      className="wr-scrollbar"
      style={{ width: "100%", height: "100%", background: "#0D1117", display: "flex", flexDirection: "column", overflowY: "auto" }}
    >
      {agents.map((agent) => {
        const isSelected = selectedAgentId === agent.id;
        const isHovered = hoveredId === agent.id;
        const isSpeaking = agent.status === "speaking";
        const isDismissed = agent.status === "dismissed";
        const isDismissHovered = dismissHoveredId === agent.id;
        const isDismissing = dismissingId === agent.id;

        return (
          <div
            key={agent.id}
            onClick={() => !isDismissed && onSelectAgent(isSelected ? null : agent.id)}
            onMouseEnter={() => setHoveredId(agent.id)}
            onMouseLeave={() => setHoveredId(null)}
            style={{
              padding: "14px 16px 14px 20px",
              borderBottom: "1px solid #1E2D3D",
              background: isDismissed
                ? "rgba(255,45,45,0.04)"
                : isSelected
                  ? "rgba(74, 158, 255, 0.1)"
                  : isHovered
                    ? "rgba(255, 255, 255, 0.02)"
                    : "transparent",
              cursor: isDismissed ? "default" : "pointer",
              transition: "all 200ms ease",
              borderLeft: isDismissed
                ? "2px solid rgba(255,45,45,0.3)"
                : isSelected
                  ? "2px solid #4A9EFF"
                  : "2px solid transparent",
              opacity: isDismissed ? 0.45 : 1,
              position: "relative",
            }}
          >
            {/* Name row */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "5px" }}>
              <span
                style={{
                  fontFamily: "'Rajdhani', sans-serif",
                  fontWeight: 700,
                  fontSize: "15px",
                  letterSpacing: "0.06em",
                  color: isDismissed ? "#4A5568" : isSelected ? "#4A9EFF" : "#E8EDF2",
                  textTransform: "uppercase",
                  textDecoration: isDismissed ? "line-through" : "none",
                }}
              >
                {agent.name}
              </span>

              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                {isSpeaking && <SpeakingAnimation />}

                {/* Silence button */}
                {!isDismissed && onSilenceAgent && agent.status !== "silent" && (
                  <button
                    onClick={(e) => { e.stopPropagation(); onSilenceAgent(agent.id, 60); }}
                    onMouseEnter={() => setSilenceHoveredId(agent.id)}
                    onMouseLeave={() => setSilenceHoveredId(null)}
                    title={`Silence ${agent.name} (60s)`}
                    style={{
                      background: "none", border: "none", cursor: "pointer", padding: "2px",
                      color: silenceHoveredId === agent.id ? "#FFB800" : "#2A3D50",
                      transition: "color 150ms ease", display: "flex", alignItems: "center", lineHeight: 1,
                    }}
                  >
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style={{ pointerEvents: "none" }}>
                      <path d="M8 1v10M5 4v4M11 3v6M3 6v2M13 5v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                      <line x1="2" y1="14" x2="14" y2="14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
                    </svg>
                  </button>
                )}

                {/* Dismiss button — hidden for already-dismissed agents */}
                {!isDismissed && onDismissAgent && (
                  <button
                    onClick={(e) => handleDismiss(e, agent)}
                    onMouseEnter={() => setDismissHoveredId(agent.id)}
                    onMouseLeave={() => setDismissHoveredId(null)}
                    title={`Dismiss ${agent.name}`}
                    disabled={!!isDismissing}
                    style={{
                      background: "none",
                      border: "none",
                      cursor: isDismissing ? "wait" : "pointer",
                      padding: "2px",
                      color: isDismissing
                        ? "#FF6B6B"
                        : isDismissHovered
                          ? "#FF2D2D"
                          : "#2A3D50",
                      transition: "color 150ms ease",
                      display: "flex",
                      alignItems: "center",
                      lineHeight: 1,
                    }}
                  >
                    <DismissIcon />
                  </button>
                )}

                {isDismissed && (
                  <span style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "8px", color: "#FF2D2D", letterSpacing: "0.1em" }}>
                    DISMISSED
                  </span>
                )}
              </div>
            </div>

            {/* Role */}
            <div
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontWeight: 500,
                fontSize: "10px",
                color: isDismissed ? "#2A3D50" : isSelected ? "#4A9EFF" : "#4A5568",
                textTransform: "uppercase",
                letterSpacing: "0.1em",
              }}
            >
              {agent.role}
            </div>
          </div>
        );
      })}
    </div>
  );
}
