"use client";

import { useEffect, useState } from "react";
import { getAgent, getAgentSkill } from "@/lib/api";

interface AgentDetailsOverlayProps {
    sessionId: string;
    token: string;
    agentId: string;
    onClose: () => void;
}

export default function AgentDetailsOverlay({
    sessionId,
    token,
    agentId,
    onClose
}: AgentDetailsOverlayProps) {
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [details, setDetails] = useState<any>(null);
    const [skill, setSkill] = useState<any>(null);

    useEffect(() => {
        async function fetchDetails() {
            setLoading(true);
            setError(null);
            try {
                const [agentData, skillData] = await Promise.all([
                    getAgent(sessionId, token, agentId).catch(() => null),
                    getAgentSkill(sessionId, token, agentId).catch(() => null)
                ]);

                if (agentData) setDetails(agentData);
                if (skillData) setSkill(skillData);

                if (!agentData) {
                    setError("Failed to load agent details.");
                }
            } catch (err: any) {
                setError(err.message || "An error occurred");
            } finally {
                setLoading(false);
            }
        }

        if (agentId) {
            fetchDetails();
        }
    }, [agentId, sessionId, token]);

    return (
        <div style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            background: "rgba(8, 10, 14, 0.7)",
            backdropFilter: "blur(4px)",
            zIndex: 200,
            display: "flex",
            alignItems: "center",
            justifyContent: "center"
        }}>
            <div style={{
                width: "500px",
                maxHeight: "80vh",
                background: "#0D1117",
                border: "1px solid #1E2D3D",
                boxShadow: "0 10px 40px rgba(0,0,0,0.8)",
                display: "flex",
                flexDirection: "column",
                overflow: "hidden"
            }}>
                {/* Header */}
                <div style={{
                    padding: "16px 20px",
                    borderBottom: "1px solid #1E2D3D",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    background: "rgba(255,255,255,0.02)"
                }}>
                    <div>
                        <div style={{
                            fontFamily: "'IBM Plex Mono', monospace",
                            fontSize: "10px",
                            color: "#4A9EFF",
                            letterSpacing: "0.1em",
                            textTransform: "uppercase",
                            marginBottom: "4px"
                        }}>
                            {details?.role_title || "AGENT DOSSIER"}
                        </div>
                        <h2 style={{
                            margin: 0,
                            fontFamily: "'Rajdhani', sans-serif",
                            fontWeight: 700,
                            fontSize: "20px",
                            color: "#E8EDF2",
                            letterSpacing: "0.06em",
                            textTransform: "uppercase"
                        }}>
                            {details?.character_name || agentId.toUpperCase()}
                        </h2>
                    </div>
                    <button
                        onClick={onClose}
                        style={{
                            background: "none",
                            border: "1px solid #1E2D3D",
                            color: "#8A9BB0",
                            cursor: "pointer",
                            padding: "4px 8px",
                            fontFamily: "'Barlow Condensed', sans-serif",
                            fontSize: "12px",
                            fontWeight: 600,
                            transition: "all 0.2s ease"
                        }}
                        onMouseEnter={(e) => {
                            e.currentTarget.style.color = "#FF2D2D";
                            e.currentTarget.style.borderColor = "#FF2D2D";
                        }}
                        onMouseLeave={(e) => {
                            e.currentTarget.style.color = "#8A9BB0";
                            e.currentTarget.style.borderColor = "#1E2D3D";
                        }}
                    >
                        CLOSE [X]
                    </button>
                </div>

                {/* Content */}
                <div className="wr-scrollbar" style={{ padding: "20px", overflowY: "auto", flex: 1 }}>
                    {loading ? (
                        <div style={{ fontFamily: "'IBM Plex Mono', monospace", color: "#8A9BB0", fontSize: "12px", textAlign: "center", padding: "40px" }}>
                            DECRYPTING DATA...
                        </div>
                    ) : error ? (
                        <div style={{ fontFamily: "'IBM Plex Mono', monospace", color: "#FF2D2D", fontSize: "12px" }}>
                            {error}
                        </div>
                    ) : (
                        <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
                            {/* Defining Line */}
                            {details?.defining_line && (
                                <div style={{
                                    padding: "12px",
                                    background: "rgba(74, 158, 255, 0.05)",
                                    borderLeft: "2px solid #4A9EFF",
                                    fontFamily: "'IBM Plex Mono', monospace",
                                    fontSize: "12px",
                                    color: "#E8EDF2",
                                    fontStyle: "italic"
                                }}>
                                    "{details.defining_line}"
                                </div>
                            )}

                            {/* Agenda */}
                            {details?.agenda && (
                                <div>
                                    <div style={{
                                        fontFamily: "'Barlow Condensed', sans-serif",
                                        fontSize: "12px",
                                        fontWeight: 600,
                                        color: "#8A9BB0",
                                        letterSpacing: "0.1em",
                                        marginBottom: "8px",
                                        borderBottom: "1px solid #1E2D3D",
                                        paddingBottom: "4px"
                                    }}>
                                        PRIMARY AGENDA
                                    </div>
                                    <div style={{
                                        fontFamily: "'IBM Plex Mono', monospace",
                                        fontSize: "12px",
                                        color: "#E8EDF2",
                                        lineHeight: 1.5
                                    }}>
                                        {details.agenda}
                                    </div>
                                </div>
                            )}

                            {/* Status & Stats */}
                            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px" }}>
                                <div>
                                    <div style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "10px", color: "#8A9BB0", letterSpacing: "0.1em" }}>STATUS</div>
                                    <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "12px", color: "#E8EDF2", textTransform: "uppercase" }}>{details?.status}</div>
                                </div>
                                <div>
                                    <div style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "10px", color: "#8A9BB0", letterSpacing: "0.1em" }}>TRUST SCORE</div>
                                    <div style={{ fontFamily: "'IBM Plex Mono', monospace", fontSize: "12px", color: details?.trust_score >= 70 ? "#00C896" : (details?.trust_score >= 50 ? "#FFB800" : "#FF2D2D") }}>{details?.trust_score}%</div>
                                </div>
                            </div>

                            {/* Skill MD */}
                            {skill?.skill_md && (
                                <div>
                                    <div style={{
                                        fontFamily: "'Barlow Condensed', sans-serif",
                                        fontSize: "12px",
                                        fontWeight: 600,
                                        color: "#8A9BB0",
                                        letterSpacing: "0.1em",
                                        marginBottom: "8px",
                                        borderBottom: "1px solid #1E2D3D",
                                        paddingBottom: "4px"
                                    }}>
                                        OPERATIONAL PARAMETERS
                                    </div>
                                    <pre className="wr-scrollbar" style={{
                                        fontFamily: "'IBM Plex Mono', monospace",
                                        fontSize: "11px",
                                        color: "#8A9BB0",
                                        lineHeight: 1.4,
                                        background: "#080A0E",
                                        padding: "12px",
                                        border: "1px solid #1E2D3D",
                                        whiteSpace: "pre-wrap",
                                        wordBreak: "break-word",
                                        maxHeight: "200px",
                                        overflowY: "auto"
                                    }}>
                                        {skill.skill_md}
                                    </pre>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
