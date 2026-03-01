"use client";

import { useEffect, useState, useRef } from "react";

type ThreatLevel = "CONTAINED" | "ELEVATED" | "CRITICAL" | "MELTDOWN";

interface TopCommandBarProps {
  crisisTitle: string;
  crisisDomain?: string;
  crisisBrief?: string;
  threatLevel: ThreatLevel;
  micActive: boolean;
  sessionTimeLeft: number; // seconds
}

function getThreatStyle(level: ThreatLevel) {
  switch (level) {
    case "CONTAINED":
      return {
        color: "#00C896",
        borderColor: "#00C896",
        bg: "rgba(0,200,150,0.1)",
      };
    case "ELEVATED":
      return {
        color: "#FFB800",
        borderColor: "#FFB800",
        bg: "rgba(255,184,0,0.1)",
      };
    case "CRITICAL":
      return {
        color: "#FF2D2D",
        borderColor: "#FF2D2D",
        bg: "rgba(255,45,45,0.1)",
      };
    case "MELTDOWN":
      return {
        color: "#FF2D2D",
        borderColor: "#FF2D2D",
        bg: "rgba(255,45,45,0.2)",
      };
  }
}

function formatTime(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

export default function TopCommandBar({
  crisisTitle,
  crisisDomain,
  crisisBrief,
  threatLevel,
  micActive,
  sessionTimeLeft,
}: TopCommandBarProps) {
  const [utcTime, setUtcTime] = useState("");
  const [gearHovered, setGearHovered] = useState(false);
  const [showDetails, setShowDetails] = useState(false);
  const detailsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (detailsRef.current && !detailsRef.current.contains(event.target as Node)) {
        setShowDetails(false);
      }
    }
    if (showDetails) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [showDetails]);

  useEffect(() => {
    const update = () => {
      const now = new Date();
      const days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
      const months = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
      const day = days[now.getUTCDay()];
      const date = String(now.getUTCDate()).padStart(2, "0");
      const month = months[now.getUTCMonth()];
      const year = now.getUTCFullYear();
      const time = `${String(now.getUTCHours()).padStart(2, "0")}:${String(now.getUTCMinutes()).padStart(2, "0")}:${String(now.getUTCSeconds()).padStart(2, "0")}`;
      setUtcTime(`${day}, ${date} ${month} ${year}  •  ${time} UTC`);
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, []);

  const threatStyle = getThreatStyle(threatLevel);
  const timerCritical = sessionTimeLeft < 600;
  const timerBlink = sessionTimeLeft < 300;
  const isMeltdown = threatLevel === "MELTDOWN";

  return (
    <div
      style={{
        height: "48px",
        background: "#080A0E",
        borderBottom: "1px solid #1E2D3D",
        display: "flex",
        alignItems: "center",
        padding: "0 20px",
        gap: "0",
        flexShrink: 0,
        position: "relative",
        zIndex: 50,
      }}
    >
      {/* Left Section */}
      <div style={{ display: "flex", alignItems: "center", gap: "12px", width: "280px", flexShrink: 0 }}>
        {/* Logo crosshair */}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="4" stroke="#4A9EFF" strokeWidth="1.5" />
          <line x1="12" y1="2" x2="12" y2="8" stroke="#4A9EFF" strokeWidth="1.5" />
          <line x1="12" y1="16" x2="12" y2="22" stroke="#4A9EFF" strokeWidth="1.5" />
          <line x1="2" y1="12" x2="8" y2="12" stroke="#4A9EFF" strokeWidth="1.5" />
          <line x1="16" y1="12" x2="22" y2="12" stroke="#4A9EFF" strokeWidth="1.5" />
        </svg>
        <span
          style={{
            fontFamily: "'Rajdhani', sans-serif",
            fontWeight: 700,
            fontSize: "14px",
            letterSpacing: "0.12em",
            color: "#E8EDF2",
          }}
        >
          WAR ROOM
        </span>
        <div
          style={{
            width: "1px",
            height: "20px",
            background: "#1E2D3D",
            flexShrink: 0,
          }}
        />
        <div style={{ position: "relative" }} ref={detailsRef}>
          <div
            onClick={() => setShowDetails(!showDetails)}
            style={{
              overflow: "hidden",
              cursor: "pointer",
              padding: "4px 8px 4px 0",
              borderRadius: "4px",
              transition: "background 200ms ease",
              background: showDetails ? "rgba(255,255,255,0.05)" : "transparent"
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = "rgba(255,255,255,0.02)"}
            onMouseLeave={(e) => e.currentTarget.style.background = showDetails ? "rgba(255,255,255,0.05)" : "transparent"}
          >
            <div
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontWeight: 400,
                fontSize: "9px",
                color: "#4A5568",
                letterSpacing: "0.04em",
                lineHeight: 1,
              }}
            >
              CRISIS:
            </div>
            <div
              style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontWeight: 500,
                fontSize: "11px",
                color: "#8A9BB0",
                maxWidth: "160px",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                lineHeight: 1.3,
              }}
            >
              {crisisTitle}
            </div>
          </div>

          {showDetails && (
            <div style={{
              position: "absolute",
              top: "100%",
              left: 0,
              marginTop: "8px",
              width: "360px",
              background: "#0D1117",
              border: "1px solid #1E2D3D",
              zIndex: 100,
              boxShadow: "0 8px 32px rgba(0,0,0,0.5)",
              display: "flex",
              flexDirection: "column",
            }}>
              <div style={{
                padding: "12px 16px",
                borderBottom: "1px solid #1E2D3D",
                background: "rgba(255,255,255,0.02)"
              }}>
                <h3 style={{
                  margin: 0,
                  fontFamily: "'Rajdhani', sans-serif",
                  fontWeight: 700,
                  fontSize: "16px",
                  color: "#E8EDF2",
                  letterSpacing: "0.06em",
                  textTransform: "uppercase"
                }}>{crisisTitle}</h3>
                {crisisDomain && (
                  <div style={{
                    marginTop: "4px",
                    fontFamily: "'IBM Plex Mono', monospace",
                    fontSize: "10px",
                    color: "#4A9EFF",
                    letterSpacing: "0.1em",
                    textTransform: "uppercase"
                  }}>
                    DOMAIN: {crisisDomain}
                  </div>
                )}
              </div>
              <div style={{ padding: "16px" }}>
                <p style={{
                  margin: 0,
                  fontFamily: "'IBM Plex Mono', monospace",
                  fontSize: "12px",
                  color: "#8A9BB0",
                  lineHeight: 1.5
                }}>
                  {crisisBrief || "No briefing details available for this crisis."}
                </p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Center Section */}
      <div
        style={{
          flex: 1,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
        }}
      >
        <span
          style={{
            fontFamily: "'IBM Plex Mono', monospace",
            fontWeight: 400,
            fontSize: "12px",
            color: "#4A5568",
            letterSpacing: "0.02em",
          }}
        >
          {utcTime}
        </span>
      </div>

      {/* Right Section */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "16px",
          paddingRight: "0px",
          flexShrink: 0,
        }}
      >
        {/* Mic Status */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div
            className={micActive ? "dot-mic" : ""}
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: micActive ? "#00E5FF" : "#4A5568",
              filter: micActive ? "drop-shadow(0 0 3px #00E5FF)" : "none",
            }}
          />
          <span
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 500,
              fontSize: "10px",
              letterSpacing: "0.08em",
              color: micActive ? "#00E5FF" : "#4A5568",
            }}
          >
            {micActive ? "MIC ACTIVE" : "MIC MUTED"}
          </span>
        </div>

        {/* Live Badge */}
        <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
          <div
            className="dot-live"
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              background: "#FF2D2D",
            }}
          />
          <span
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 600,
              fontSize: "11px",
              letterSpacing: "0.12em",
              color: "#FF2D2D",
            }}
          >
            LIVE
          </span>
        </div>

        {/* Threat Level */}
        <div
          style={{
            padding: "4px 10px",
            border: `1px solid ${threatStyle.borderColor}`,
            background: threatStyle.bg,
            animation: isMeltdown ? "statusPulse 1s ease-in-out infinite" : "none",
          }}
        >
          <span
            style={{
              fontFamily: "'Barlow Condensed', sans-serif",
              fontWeight: 600,
              fontSize: "11px",
              letterSpacing: "0.12em",
              color: threatStyle.color,
            }}
          >
            THREAT: {threatLevel}
          </span>
        </div>

        {/* Countdown Timer */}
        <span
          className={timerBlink ? "timer-blink" : ""}
          style={{
            fontFamily: "'Orbitron', monospace",
            fontWeight: 700,
            fontSize: "14px",
            color: timerCritical ? "#FF2D2D" : "#FFB800",
            letterSpacing: "0.04em",
          }}
        >
          {formatTime(sessionTimeLeft)}
        </span>

        {/* Settings Gear */}
        <button
          onMouseEnter={() => setGearHovered(true)}
          onMouseLeave={() => setGearHovered(false)}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: "4px",
            color: gearHovered ? "#8A9BB0" : "#4A5568",
            transition: "color 300ms ease",
            display: "flex",
            alignItems: "center",
          }}
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            style={{
              transition: "transform 300ms ease",
              transform: gearHovered ? "rotate(60deg)" : "rotate(0deg)",
            }}
          >
            <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </button>
      </div>
    </div>
  );
}
