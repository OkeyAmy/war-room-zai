"use client";

import { useState, useRef } from "react";

interface AgentOption {
  id: string;
  name: string;
}

interface ChairmanCommandBarProps {
  onSendCommand: (command: string) => void;
  isMicActive: boolean;
  onToggleMic: () => void;
  commandHistory: string[];
  /** Optional: display name for the Chairman (defaults to "CHAIRMAN") */
  chairmanName?: string;
  /** Optional: real agent list for the address-target dropdown */
  agents?: AgentOption[];
}

export default function ChairmanCommandBar({
  onSendCommand,
  isMicActive,
  onToggleMic,
  commandHistory,
  chairmanName = "CHAIRMAN",
  agents,
}: ChairmanCommandBarProps) {
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSend = () => {
    const cmd = (inputRef.current?.value || "").trim();
    if (cmd) {
      onSendCommand(cmd);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div
      style={{
        height: "52px",
        background: "#080A0E",
        borderTop: "1px solid #1E2D3D",
        display: "flex",
        alignItems: "center",
        padding: "0 20px",
        gap: "12px",
        position: "fixed",
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: 100,
      }}
    >
      {/* Segment 1: Address Target Selector */}
      <div style={{ position: "relative", width: "160px" }}>
        <button
          onClick={() => setShowDropdown(!showDropdown)}
          style={{
            width: "100%",
            height: "32px",
            padding: "0 12px",
            fontFamily: "'Barlow Condensed', sans-serif",
            fontWeight: 600,
            fontSize: "12px",
            letterSpacing: "0.06em",
            color: "#4A9EFF",
            background: "rgba(74,158,255,0.06)",
            border: "1px solid rgba(74,158,255,0.35)",
            cursor: "pointer",
            textAlign: "left",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span>▶ {selectedAgent ? selectedAgent.toUpperCase() : "FULL ROOM"}</span>
          <span>▼</span>
        </button>
        {showDropdown && (
          <div
            style={{
              position: "absolute",
              bottom: "100%",
              marginBottom: "4px",
              width: "100%",
              background: "#111820",
              border: "1px solid #1E2D3D",
              zIndex: 110,
            }}
          >
            {/* FULL ROOM option */}
            {["FULL ROOM", ...(agents ? agents.map(a => a.name.toUpperCase()) : ["ATLAS", "NOVA", "CIPHER", "FELIX"])].map((opt) => (
              <div
                key={opt}
                onClick={() => {
                  setSelectedAgent(opt === "FULL ROOM" ? null : opt);
                  setShowDropdown(false);
                }}
                style={{
                  padding: "8px 12px",
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "11px",
                  color: "#E8EDF2",
                  cursor: "pointer",
                  borderLeft: (selectedAgent === opt) || (opt === "FULL ROOM" && !selectedAgent) ? "2px solid #4A9EFF" : "2px solid transparent",
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#161F2A"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = "transparent"; }}
              >
                {opt}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Segment 2: Mic Button */}
      <button
        onClick={onToggleMic}
        style={{
          width: "44px",
          height: "44px",
          background: isMicActive ? "rgba(0,229,255,0.1)" : "#111820",
          border: `1px solid ${isMicActive ? "#00E5FF" : "#1E2D3D"}`,
          borderRadius: "2px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          cursor: "pointer",
          position: "relative",
          transition: "all 100ms ease",
        }}
      >
        {isMicActive && (
          <div
            className="mic-ring"
            style={{
              position: "absolute",
              inset: 0,
              border: "2px solid rgba(0,229,255,0.3)",
              borderRadius: "2px",
              pointerEvents: "none",
            }}
          />
        )}
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          fill="none"
          stroke={isMicActive ? "#00E5FF" : "#4A5568"}
          strokeWidth="2"
        >
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
          <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
          <line x1="12" y1="19" x2="12" y2="23" />
          <line x1="8" y1="23" x2="16" y2="23" />
        </svg>
      </button>

      {/* Segment 3: Voice Waveform */}
      <div style={{ display: "flex", alignItems: "center", gap: "2px", height: "28px", width: "180px" }}>
        {Array.from({ length: 20 }).map((_, i) => (
          <div
            key={i}
            className={isMicActive ? `wave-bar-${(i % 7) + 1}` : ""}
            style={{
              width: "4px",
              background: isMicActive ? "#00E5FF" : "#111820",
              height: isMicActive ? "100%" : "2px",
              transition: "height 100ms ease",
            }}
          />
        ))}
      </div>

      {/* Segment 4: Live Transcript / Input */}
      <div
        style={{
          flex: 1,
          height: "32px",
          background: "#111820",
          border: "1px solid #1E2D3D",
          padding: "0 12px",
          display: "flex",
          alignItems: "center",
          overflow: "hidden",
        }}
      >
        <span
          style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontWeight: 600,
            fontSize: "11px",
            color: "#FFD700",
            marginRight: "8px",
          }}
        >
          {chairmanName.toUpperCase()}:
        </span>
        <input
          ref={inputRef}
          type="text"
          placeholder={isMicActive ? "Listening..." : "Type or speak command..."}
          onKeyDown={(e) => e.key === "Enter" && handleSend()}
          style={{
            flex: 1,
            background: "none",
            border: "none",
            outline: "none",
            fontFamily: "'IBM Plex Mono', monospace",
            fontSize: "12px",
            color: "#E8EDF2",
          }}
        />
      </div>

      {/* Segment 5: Action Buttons */}
      <div style={{ display: "flex", gap: "6px" }}>
        {[
          { label: "🗳️ FORCE VOTE", onClick: () => onSendCommand("CALL VOTE") },
          { label: "❌ DISMISS", disabled: !selectedAgent, onClick: () => onSendCommand(`DISMISS ${selectedAgent}`) },
          { label: "⏸️ PAUSE", onClick: () => onSendCommand("PAUSE ROOM") },
        ].map((btn) => (
          <button
            key={btn.label}
            onClick={btn.onClick}
            disabled={btn.disabled}
            style={{
              height: "32px",
              padding: "0 10px",
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 500,
              fontSize: "10px",
              letterSpacing: "0.06em",
              border: "1px solid #1E2D3D",
              background: "transparent",
              color: "#8A9BB0",
              cursor: btn.disabled ? "default" : "pointer",
              opacity: btn.disabled ? 0.4 : 1,
              transition: "all 150ms ease",
            }}
            onMouseEnter={(e) => { if (!btn.disabled) (e.currentTarget as HTMLButtonElement).style.background = "#161F2A"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
          >
            {btn.label}
          </button>
        ))}
      </div>
    </div>
  );
}
