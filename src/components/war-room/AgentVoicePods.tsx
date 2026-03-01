"use client";

import { type Agent, type AgentStatus } from "./AgentRoster";

interface AgentVoicePodsProps {
  agents: Agent[];
  liveTranscripts?: Record<string, string>;
  activeSpeakerId?: string | null;
  onSummon?: () => void;
}

function Waveform({ status }: { status: AgentStatus }) {
  const isSpeaking = status === "speaking";
  const isConflicted = status === "conflicted";
  const bars = isSpeaking ? [1, 2, 3, 4, 5, 6, 7] : [1, 2, 3, 4, 5];

  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: "2px", height: "28px", marginBottom: "6px" }}>
      {bars.map((i) => (
        <div
          key={i}
          className={isSpeaking ? `wave-bar-${i}` : isConflicted ? `wave-bar-conflict-${i}` : ""}
          style={{
            width: "3px",
            background: isSpeaking ? "#00E5FF" : isConflicted ? "#FF2D2D" : "#111820",
            borderRadius: "1px",
            height: isSpeaking || isConflicted ? "100%" : "2px",
            transition: "all 200ms ease",
          }}
        />
      ))}
    </div>
  );
}

export default function AgentVoicePods({ agents, liveTranscripts = {}, activeSpeakerId = null, onSummon }: AgentVoicePodsProps) {
  return (
    <div
      style={{
        flex: 1,
        height: "100%",
        background: "#080A0E",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Panel Header */}
      <div
        style={{
          height: "36px",
          padding: "0 16px",
          borderBottom: "1px solid #1E2D3D",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          background: "#0D1117",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 600,
            fontSize: "11px",
            letterSpacing: "0.12em",
            color: "#8A9BB0",
          }}
        >
          AGENT FEEDS
        </span>
        <div style={{ display: "flex", gap: "8px" }}>
          {["ALL", "ACTIVE", "CONFLICTED"].map((tab, idx) => (
            <button
              key={tab}
              style={{
                fontFamily: "'Barlow Condensed', sans-serif",
                fontWeight: 500,
                fontSize: "10px",
                padding: "6px 8px",
                background: "none",
                border: "none",
                borderBottom: idx === 0 ? "2px solid #4A9EFF" : "2px solid transparent",
                color: idx === 0 ? "#4A9EFF" : "#4A5568",
                cursor: "pointer",
              }}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Pod Grid */}
      <div
        className="wr-scrollbar"
        style={{
          flex: 1,
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))",
          gap: "4px",
          padding: "8px",
          overflowY: "auto",
        }}
      >
        {agents.map((agent) => {
          // Derive display state from activeSpeakerId:
          // If another agent is the active speaker, force this pod to 'listening'
          const isActiveAgent = activeSpeakerId === agent.id;
          const someoneElseSpeaking = activeSpeakerId !== null && !isActiveAgent;
          const effectiveStatus = someoneElseSpeaking ? "listening" : agent.status;

          const isSpeaking = effectiveStatus === "speaking";
          const isThinking = effectiveStatus === "thinking";
          const isConflicted = effectiveStatus === "conflicted";
          // Dim non-active pods when someone else is speaking
          const podOpacity = someoneElseSpeaking ? 0.5 : 1;

          return (
            <div
              key={agent.id}
              style={{
                background: "#0D1117",
                border: "1px solid",
                borderColor: isSpeaking ? "rgba(0,229,255,0.45)" : isThinking ? "rgba(255,184,0,0.3)" : isConflicted ? "rgba(255,45,45,0.5)" : "#1E2D3D",
                borderRadius: "2px",
                padding: "12px",
                minHeight: "110px",
                display: "flex",
                flexDirection: "column",
                boxShadow: isSpeaking ? "0 0 14px rgba(0,229,255,0.15)" : isConflicted ? "0 0 12px rgba(255,45,45,0.1)" : "none",
                transition: "all 200ms ease",
              }}
            >
              <div
                style={{
                  fontFamily: "'Rajdhani', sans-serif",
                  fontWeight: 600,
                  fontSize: "12px",
                  color: "#E8EDF2",
                  marginBottom: "2px",
                }}
              >
                {agent.name}
              </div>
              <div
                style={{
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontWeight: 400,
                  fontSize: "9px",
                  color: "#8A9BB0",
                  marginBottom: "8px",
                }}
              >
                {agent.role}
              </div>

              <Waveform status={agent.status} />

              <div
                style={{
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontWeight: 500,
                  fontSize: "10px",
                  color: isSpeaking ? "#00E5FF" : isThinking ? "#FFB800" : isConflicted ? "#FF2D2D" : "#4A5568",
                  marginTop: "auto",
                  display: "flex",
                  alignItems: "center",
                  gap: "4px",
                }}
              >
                {isSpeaking ? "🎙️ SPEAKING" : isThinking ? "💭 PROCESSING" : isConflicted ? "⚡ CONFLICTING" : "👂 LISTENING"}
                {isThinking && (
                  <span style={{ display: "flex", gap: "2px" }}>
                    <span className="thinking-dot-1">.</span>
                    <span className="thinking-dot-2">.</span>
                    <span className="thinking-dot-3">.</span>
                  </span>
                )}
              </div>

              {(isSpeaking && liveTranscripts[agent.id]) ? (
                <div
                  style={{
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontWeight: 400,
                    fontSize: "10px",
                    color: "#00E5FF",
                    marginTop: "4px",
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                  }}
                >
                  {liveTranscripts[agent.id]}
                </div>
              ) : agent.lastWords && (
                <div
                  style={{
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontWeight: 400,
                    fontSize: "10px",
                    color: "#4A5568",
                    fontStyle: "italic",
                    marginTop: "4px",
                    overflow: "hidden",
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                  }}
                >
                  {agent.lastWords}
                </div>
              )}
            </div>
          );
        })}

        {/* Summon Pod */}
        <div
          style={{
            background: "transparent",
            border: "1px dashed #1E2D3D",
            borderRadius: "2px",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            cursor: "pointer",
            minHeight: "110px",
          }}
          onClick={onSummon}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLDivElement).style.borderColor = "#4A9EFF";
            (e.currentTarget as HTMLDivElement).style.background = "rgba(74,158,255,0.04)";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLDivElement).style.borderColor = "#1E2D3D";
            (e.currentTarget as HTMLDivElement).style.background = "transparent";
          }}
        >
          <span style={{ fontFamily: "'Rajdhani', sans-serif", fontWeight: 700, fontSize: "24px", color: "#4A5568" }}>+</span>
          <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 600, fontSize: "11px", color: "#4A5568" }}>SUMMON</span>
          <span style={{ fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 600, fontSize: "11px", color: "#4A5568" }}>AGENT</span>
        </div>
      </div>
    </div>
  );
}
