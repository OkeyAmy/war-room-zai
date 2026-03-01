"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter, useParams } from "next/navigation";
import TopCommandBar from "@/components/war-room/TopCommandBar";
import AgentRoster, { type Agent } from "@/components/war-room/AgentRoster";
import CrisisBoard, {
    type DecisionItem,
    type ConflictItem,
    type IntelItem,
    type EscalationEvent,
} from "@/components/war-room/CrisisBoard";
import CrisisFeed, { type FeedItem } from "@/components/war-room/CrisisFeed";
import AgentVoicePods from "@/components/war-room/AgentVoicePods";
import {
    RoomIntelligence,
    CrisisPosture,
    ResolutionScore,
    type IntelligenceItem,
    type PostureLevel,
    type PostureAxis,
    type ScoreContributor,
    type IntelAlert,
    type TrustScore,
} from "@/components/war-room/RightPanels";
import ChairmanCommandBar from "@/components/war-room/ChairmanCommandBar";
import {
    getSessionState,
    getScenario,
    patchSession,
    deleteSession,
    getAgents,
    patchAgent,
    summonAgent,
    sendChairmanCommand,
    getBoard,
    getFeed,
    getIntel,
    getTrustScores,
    getPosture,
    getScore,
    getWorld,
    getCommandHistory,
    patchActiveVoiceAgent,
    getVoicePods,
    patchVoicePod,
    type ScenarioAgent,
    type AgentListItem,
    type VoicePodState,
} from "@/lib/api";
import { loadSession, clearSession } from "@/lib/sessionStore";
import {
    useWarRoomSocket,
    useAudioPlayer,
    type WSEvent,
} from "@/lib/hooks/useWarRoomSocket";
import { useChairmanMic } from "@/lib/hooks/useChairmanMic";

// ─── Simulation Seed Data (FALLBACK — only used when API fails) ──────────────

const SIMULATION_AGENTS: Agent[] = [
    { id: "a1", name: "ATLAS", surname: "Strategic", role: "Strategic Analyst", status: "speaking", trustScore: 87, lastWords: "Containment window is closing fast" },
    { id: "a2", name: "NOVA", surname: "Legal", role: "Legal Counsel", status: "thinking", trustScore: 92, lastWords: "We need to verify liability exposure" },
    { id: "a3", name: "CIPHER", surname: "Intel", role: "Intelligence Officer", status: "listening", trustScore: 78, lastWords: "Signal intercept confirmed", conflictWith: "ATLAS" },
    { id: "a4", name: "FELIX", surname: "Ops", role: "Field Operations", status: "conflicted", trustScore: 65, lastWords: "Deploy now, ask later", conflictWith: "NOVA" },
    { id: "a5", name: "ORACLE", surname: "Data", role: "Data Analyst", status: "silent", trustScore: 81, lastWords: "Probability of escalation: 74%" },
    { id: "a6", name: "VANGUARD", surname: "Comms", role: "Communications Lead", status: "listening", trustScore: 73, lastWords: "Media is already aware" },
];

const INITIAL_DECISIONS: DecisionItem[] = [
    { id: "d1", text: "Activate secondary containment protocol and isolate affected nodes immediately.", time: "14:32:01", proposedBy: "ATLAS" },
    { id: "d2", text: "Brief external stakeholders with prepared statement by 15:00 UTC.", time: "14:28:44", proposedBy: "VANGUARD" },
];

const INITIAL_CONFLICTS: ConflictItem[] = [
    { id: "c1", description: "FELIX insists on immediate field deployment; NOVA flags legal risk of unauthorized action in jurisdiction.", agentA: "FELIX", agentB: "NOVA" },
];

const INITIAL_INTEL: IntelItem[] = [
    { id: "i1", text: "External actor attempted perimeter breach at 14:29 UTC. Three vectors confirmed. Origin: indeterminate.", source: "CIPHER / SIGINT" },
    { id: "i2", text: "Internal audit log shows anomalous access pattern starting 13:54 UTC. User token: revoked.", source: "ORACLE / SIEM" },
];

const INITIAL_FEED: FeedItem[] = [];

const INITIAL_INTEL_ITEMS: IntelligenceItem[] = [
    { id: "ri1", label: "Agents Active", value: "6 / 6", trend: "neutral" },
    { id: "ri2", label: "Conflicts Open", value: "1", trend: "neutral", critical: false },
    { id: "ri3", label: "Decisions Locked", value: "2", trend: "up" },
    { id: "ri4", label: "Intel Items", value: "2", trend: "up" },
    { id: "ri5", label: "Session Health", value: "NOMINAL", trend: "neutral" },
];

const INITIAL_ALERTS: IntelAlert[] = [
    { id: "ra1", type: "CONTRADICTION", text: "ATLAS claims containment is stable, but CIPHER reports perimeter breach.", timestamp: "14:35:12", meta: "ATLAS vs CIPHER" },
    { id: "ra2", type: "ALLIANCE", text: "NOVA and CIPHER are aligning on legal-intel data protocol.", timestamp: "14:34:45" },
    { id: "ra3", type: "BLIND_SPOT", text: "No response plan for public data leak in European markets.", timestamp: "14:33:20" },
];

const INITIAL_TRUST: TrustScore[] = [
    { agentName: "ATLAS", score: 87 },
    { agentName: "NOVA", score: 92 },
    { agentName: "CIPHER", score: 78 },
    { agentName: "FELIX", score: 65 },
    { agentName: "ORACLE", score: 81 },
    { agentName: "VANGUARD", score: 73 },
];

const INITIAL_CONTRIBUTORS: ScoreContributor[] = [
    { label: "Team Alignment", value: 62, positive: true },
    { label: "Decision Velocity", value: 78, positive: true },
    { label: "Open Conflicts", value: 40, positive: false },
    { label: "Intel Coverage", value: 85, positive: true },
];

// ─── Simulation fallback speeches ─────────────────────────────────────────────

const SIMULATION_SPEECHES = [
    { agent: "ATLAS", category: "INTERNAL" as const, text: "We need to accelerate the decision cycle. Every second of delay compounds risk." },
    { agent: "NOVA", category: "LEGAL" as const, text: "I can compress the legal review to 90 seconds if we narrow scope. Give me the parameters." },
    { agent: "CIPHER", category: "INTERNAL" as const, text: "New signal intercept uploaded to secure channel. Priority: HIGH." },
    { agent: "ORACLE", category: "INTERNAL" as const, text: "Scenario delta updated. Probability of full escalation now at 81%." },
    { agent: "FELIX", category: "INTERNAL" as const, text: "Field team is standing by. We are burning time." },
    { agent: "VANGUARD", category: "MEDIA" as const, text: "Media silence will break in approximately 4 minutes. I recommend immediate release." },
];
const SIMULATION_INTEL = [
    { text: "Thermal imaging detects unauthorized personnel at coordinates redacted. Count: 3.", source: "FIELD / SAT-4" },
    { text: "Dark web chatter references operation codename matching our incident. Confidence: medium.", source: "CIPHER / OSINT" },
];
const SIMULATION_DECISIONS = [
    { text: "Authorize FELIX for limited perimeter deployment under executive mandate. Duration: 30 minutes.", proposedBy: "ATLAS" },
    { text: "Issue public statement draft B — non-confirmatory. Release via VANGUARD at 15:00 UTC.", proposedBy: "VANGUARD" },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function timestamp(): string {
    const now = new Date();
    return `${String(now.getUTCHours()).padStart(2, "0")}:${String(now.getUTCMinutes()).padStart(2, "0")}:${String(now.getUTCSeconds()).padStart(2, "0")}`;
}

function nextFeedId() { return `f-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`; }
let decisionCounter = 10;
function nextDecisionId() { return `d${++decisionCounter}`; }
let intelCounter = 10;
function nextIntelId() { return `i${++intelCounter}`; }

function threatStringToPosture(level: string): PostureLevel {
    switch (level?.toLowerCase()) {
        case "meltdown": return 5;
        case "critical": return 4;
        case "elevated": return 3;
        case "guarded": return 2;
        case "contained": return 1;
        default: return 3;
    }
}

function threatStringToLabel(level: string): "CONTAINED" | "ELEVATED" | "CRITICAL" | "MELTDOWN" {
    switch (level?.toLowerCase()) {
        case "critical": return "CRITICAL";
        case "elevated": return "ELEVATED";
        case "meltdown": return "MELTDOWN";
        default: return "CONTAINED";
    }
}

function mapPostureAxes(axesData: Record<string, any>): PostureAxis[] {
    const labelMap: Record<string, string> = {
        public_exposure: "PUBLIC EXPOSURE",
        legal_exposure: "LEGAL EXPOSURE",
        internal_stability: "INTERNAL STABILITY"
    };
    const order = ["public_exposure", "legal_exposure", "internal_stability"];

    return Object.entries(axesData)
        .sort(([a], [b]) => order.indexOf(a) - order.indexOf(b))
        .map(([key, data]) => {
            const rawStatus = String(data?.status || "contained").toLowerCase();
            const statusMap: Record<string, PostureAxis["status"]> = {
                critical: "CRIT", high: "HIGH", elevated: "ELEV", contained: "CONT", meltdown: "CRIT"
            };
            let rawTrend = String(data?.trend || "stable").toLowerCase();
            if (rawTrend.includes("falling")) rawTrend = "falling";
            if (rawTrend.includes("rising")) rawTrend = "rising";

            const trendMap: Record<string, PostureAxis["trend"]> = {
                rising: "UP", stable: "STABLE", falling: "DOWN"
            };
            let subMetric = String(data?.sub_metric || data?.driver || "");
            if (subMetric.includes(" • ")) {
                subMetric = subMetric.split(" • ")[0];
            }
            return {
                label: labelMap[key] || key.replace(/_/g, " ").toUpperCase(),
                value: Number(data?.value) || 50,
                status: statusMap[rawStatus] || "CONT",
                subMetric: subMetric,
                trend: trendMap[rawTrend] || "STABLE"
            };
        });
}

/** Convert an AgentListItem from the backend API into the Agent type used by AgentRoster */
function apiAgentToRosterAgent(a: AgentListItem): Agent {
    const statusMap: Record<string, Agent["status"]> = {
        speaking: "speaking", thinking: "thinking", conflicted: "conflicted",
        listening: "listening", silent: "silent", idle: "listening", dismissed: "dismissed",
    };
    return {
        id: a.agent_id,
        name: a.character_name.split(" ").pop()?.toUpperCase() ?? a.agent_id.toUpperCase(),
        surname: a.character_name.split(" ")[0] ?? "",
        role: a.role_title,
        status: statusMap[a.status] ?? "listening",
        trustScore: a.trust_score,
        lastWords: a.last_statement || undefined,
        conflictWith: a.conflict_with?.[0] ?? undefined,
        identityColor: a.identity_color,
        voiceName: a.voice_name,
    };
}

/** Fallback converter — only used when getAgents() fails */
function scenarioAgentToRosterAgent(a: ScenarioAgent, idx: number): Agent {
    const statuses: Agent["status"][] = ["listening", "thinking", "silent", "listening", "speaking"];
    return {
        id: a.agent_id,
        name: a.character_name.split(" ").pop()?.toUpperCase() ?? a.role_key.toUpperCase(),
        surname: a.role_key,
        role: a.role_title,
        status: statuses[idx % statuses.length],
        trustScore: 75,
        lastWords: a.defining_line,
    };
}

// ─── Main War Room Page ───────────────────────────────────────────────────────

export default function WarRoomPage() {
    const router = useRouter();
    const params = useParams<{ session_id: string }>();

    // ── Session credentials ───────────────────────────────────────────────────
    const [sessionId, setSessionId] = useState<string | null>(null);
    const [token, setToken] = useState<string | null>(null);
    const [chairmanName, setChairmanName] = useState("DIRECTOR");
    const [crisisTitle, setCrisisTitle] = useState("OPERATION BLACKSITE — SECTOR 7 BREACH");
    const [threatLevel, setThreatLevel] =
        useState<"CONTAINED" | "ELEVATED" | "CRITICAL" | "MELTDOWN">("CRITICAL");

    // ── Room state ────────────────────────────────────────────────────────────
    const [agents, setAgents] = useState<Agent[]>([]);
    const [decisions, setDecisions] = useState<DecisionItem[]>([]);
    const [conflicts, setConflicts] = useState<ConflictItem[]>([]);
    const [intel, setIntel] = useState<IntelItem[]>([]);
    const [feed, setFeed] = useState<FeedItem[]>(INITIAL_FEED);
    const [escalation, setEscalation] = useState<EscalationEvent | null>(null);
    const activeAgentsCount = agents.filter(a => a.status !== "dismissed").length;
    const dynamicIntelItems: IntelligenceItem[] = [
        { id: "ri1", label: "Agents Active", value: `${activeAgentsCount} / ${Math.max(agents.length, 1)}`, trend: "neutral" },
        { id: "ri2", label: "Conflicts Open", value: `${conflicts.length}`, trend: conflicts.length > 0 ? "up" : "neutral", critical: conflicts.length > 0 },
        { id: "ri3", label: "Decisions Locked", value: `${decisions.length}`, trend: decisions.length > 0 ? "up" : "neutral" },
        { id: "ri4", label: "Intel Items", value: `${intel.length}`, trend: intel.length > 0 ? "up" : "neutral" },
        { id: "ri5", label: "Session Health", value: threatLevel === "CONTAINED" ? "NOMINAL" : threatLevel, trend: threatLevel === "CRITICAL" || threatLevel === "MELTDOWN" ? "down" : "neutral" },
    ];
    const [intelAlerts, setIntelAlerts] = useState<IntelAlert[]>([]);
    const [trustScores, setTrustScores] = useState<TrustScore[]>([]);
    const [postureLevel, setPostureLevel] = useState<PostureLevel>(3);
    const [postureAxes, setPostureAxes] = useState<PostureAxis[]>([]);
    const [resolutionScore, setResolutionScore] = useState(42);
    const [scoreDelta, setScoreDelta] = useState(+3);
    const [scoreTrend, setScoreTrend] = useState<"IMPROVING" | "FALLING" | "STABLE">("STABLE");
    const [scoreDriver, setScoreDriver] = useState("Team Alignment");
    const [scoreTargetText, setScoreTargetText] = useState("70+ to avoid fallout");
    const [nextEscalationDisplay, setNextEscalationDisplay] = useState("04:59");

    const avgTrust = Math.round(trustScores.reduce((sum, t) => sum + t.score, 0) / Math.max(trustScores.length, 1)) || 62;
    const dynamicContributors: ScoreContributor[] = [
        { label: "Team Alignment", value: avgTrust, positive: true },
        { label: "Decision Velocity", value: Math.min(100, decisions.length * 15 + 20), positive: true },
        { label: "Open Conflicts", value: Math.min(100, conflicts.length * 20), positive: false },
        { label: "Intel Coverage", value: Math.min(100, intel.length * 12 + 25), positive: true },
    ];
    const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
    const [voicePods, setVoicePods] = useState<VoicePodState[]>([]);
    const [connectedPodAgents, setConnectedPodAgents] = useState<Set<string>>(new Set());
    const [activeSpeakerId, setActiveSpeakerId] = useState<string | null>(null);
    const [sessionTimeLeft, setSessionTimeLeft] = useState(5400);
    const [sessionPaused, setSessionPaused] = useState(false);
    const [sessionEnding, setSessionEnding] = useState(false);
    const [commandHistory, setCommandHistory] = useState<string[]>([]);
    const [liveTranscripts, setLiveTranscripts] = useState<Record<string, string>>({});

    // ── Data source tracking ──────────────────────────────────────────────────
    const [usingRealAgents, setUsingRealAgents] = useState(false);
    const wsReceivedEvents = useRef(false);

    // ── Summon modal state ────────────────────────────────────────────────────
    const [showSummonModal, setShowSummonModal] = useState(false);
    const [summonInput, setSummonInput] = useState("");
    const [summoning, setSummoning] = useState(false);

    // Layout states
    const [leftSidebarWidth, setLeftSidebarWidth] = useState(240);
    const [rightSidebarWidth, setRightSidebarWidth] = useState(240);
    const [bottomHeight, setBottomHeight] = useState(220);
    const [leftCollapsed, setLeftCollapsed] = useState(false);
    const [bottomCollapsed, setBottomCollapsed] = useState(false);

    const containerRef = useRef<HTMLDivElement>(null);
    const resizingSide = useRef<"left" | "right" | "bottom" | null>(null);
    const speechIdx = useRef(0);
    const intelIdx = useRef(0);
    const decisionIdx = useRef(0);

    // ── Audio player for agent voices ─────────────────────────────────────────
    const { playChunk, stopAgent, stopAll: stopAllAgents, ensureContext } = useAudioPlayer();
    const audioInitializedRef = useRef(false);

    // Ref that mirrors activeSpeakerId — used in audio chunk handler
    // to avoid stale closures (useCallback would capture old state otherwise).
    const activeSpeakerRef = useRef<string | null>(null);

    // Initialize AudioContext on FIRST user gesture (browser security requirement)
    // Per voice.md §3.5: must be a click/touch before any audio plays.
    const initAudioOnGesture = useCallback(() => {
        if (!audioInitializedRef.current) {
            ensureContext();
            audioInitializedRef.current = true;
        }
    }, [ensureContext]);

    // ── WebSocket event handler ───────────────────────────────────────────────
    const handleWSEvent = useCallback((event: WSEvent) => {
        wsReceivedEvents.current = true;
        const p = event.payload;

        switch (event.event_type) {
            case "agent_status_change": {
                const agentId = p.agent_id as string;
                const newStatus = p.status as string;
                setAgents(prev => prev.map(a =>
                    a.id === agentId
                        ? { ...a, status: (newStatus === "idle" ? "listening" : newStatus) as Agent["status"] }
                        : a
                ));
                // Only promote to active speaker if no one else owns the gate
                if (newStatus === "speaking" && !activeSpeakerRef.current) {
                    setActiveSpeakerId(agentId);
                    activeSpeakerRef.current = agentId;
                }
                break;
            }
            case "agent_speaking_start": {
                const agentId = p.agent_id as string;
                // Only update if this agent is the active speaker
                // (turn_started already set the gate — this is a confirmation)
                if (!activeSpeakerRef.current || activeSpeakerRef.current === agentId) {
                    setAgents(prev => prev.map(a =>
                        a.id === agentId ? { ...a, status: "speaking" as const } : a
                    ));
                    setActiveSpeakerId(agentId);
                    activeSpeakerRef.current = agentId;
                    setLiveTranscripts(prev => ({ ...prev, [agentId]: "" }));
                }
                break;
            }
            case "agent_speaking_chunk": {
                const agentId = p.agent_id as string;
                const text = p.transcript_chunk as string;
                if (text) {
                    setLiveTranscripts(prev => ({
                        ...prev,
                        [agentId]: (prev[agentId] || "") + text,
                    }));
                }
                break;
            }
            case "agent_speaking_end": {
                const agentId = p.agent_id as string;
                const fullText = p.full_transcript as string;
                // Do not force-stop playback here; let queued audio finish naturally.
                setAgents(prev => prev.map(a =>
                    a.id === agentId ? { ...a, status: "listening" as const, lastWords: fullText || a.lastWords } : a
                ));
                if (activeSpeakerRef.current === agentId) {
                    setActiveSpeakerId(null);
                    activeSpeakerRef.current = null;
                }
                // Add to feed
                const agentName = agents.find(a => a.id === agentId)?.name ?? agentId;
                setFeed(prev => [{
                    id: nextFeedId(), timestamp: timestamp(), source: agentName,
                    text: fullText || "", category: "INTERNAL" as const, isNew: true,
                }, ...prev].slice(0, 80));
                break;
            }
            case "agent_interrupted": {
                const agentId = p.agent_id as string;
                // Stop audio immediately — voice.md §3.6
                stopAgent(agentId);
                setAgents(prev => prev.map(a =>
                    a.id === agentId ? { ...a, status: "listening" as const } : a
                ));
                break;
            }
            case "chairman_taking_floor": {
                // Chairman is speaking — silence all agents immediately
                stopAllAgents();
                setAgents(prev => prev.map(a =>
                    a.status === "speaking" ? { ...a, status: "listening" as const } : a
                ));
                setActiveSpeakerId(null);
                activeSpeakerRef.current = null;
                break;
            }
            case "trust_score_update": {
                const agentId = p.agent_id as string;
                const score = p.new_score as number;
                setTrustScores(prev => prev.map(t =>
                    t.agentName === agentId || agents.find(a => a.id === agentId)?.name === t.agentName
                        ? { ...t, score } : t
                ));
                setAgents(prev => prev.map(a =>
                    a.id === agentId ? { ...a, trustScore: score } : a
                ));
                break;
            }
            case "observer_insight": {
                const insightType = (p.type || p.insight_type) as string;
                const text = (p.body || p.text) as string;
                let meta = undefined;
                if (Array.isArray(p.agents_referenced) && p.agents_referenced.length > 0) {
                    const names = p.agents_referenced.map(id => typeof id === 'string' ? id.split('_')[0].toUpperCase() : '');
                    const iType = (insightType || "").toLowerCase();
                    meta = names.filter(Boolean).join(iType === "alliance" ? " & " : " vs ");
                }
                setIntelAlerts(prev => [{
                    id: (p.insight_id as string) || `ws-${Date.now()}`,
                    type: insightType?.toUpperCase() === "CONTRADICTION" ? "CONTRADICTION"
                        : insightType?.toUpperCase() === "ALLIANCE" ? "ALLIANCE" : "BLIND_SPOT",
                    text: text || "",
                    timestamp: timestamp(),
                    meta,
                }, ...prev].slice(0, 20));
                break;
            }
            case "crisis_escalation": {
                const text = p.event_text as string || p.text as string;
                setEscalation({ id: `esc-${Date.now()}`, text: text || "Escalation event", time: timestamp(), visible: true });
                setFeed(prev => [{
                    id: nextFeedId(), timestamp: timestamp(), source: "WORLD AGENT",
                    text: `⚠ ESCALATION: ${text}`, category: "WORLD" as const, isNew: true, isBreaking: true,
                }, ...prev].slice(0, 80));
                setPostureLevel(prev => Math.min(5, prev + 1) as PostureLevel);
                setTimeout(() => setEscalation(null), 8000);
                break;
            }
            case "score_update": {
                const score = (p.score ?? p.resolution_score) as number;
                const threat = p.threat_level as string;
                if (score !== undefined) {
                    setScoreDelta(score - resolutionScore);
                    setResolutionScore(score);
                }
                if (threat) {
                    setThreatLevel(threatStringToLabel(threat));
                    setPostureLevel(threatStringToPosture(threat));
                }
                if (p.trend) {
                    const t = (p.trend as string).toUpperCase();
                    setScoreTrend(t === "IMPROVING" ? "IMPROVING" : t === "DECLINING" ? "FALLING" : "STABLE");
                }
                if (p.driver) setScoreDriver(p.driver as string);
                if (p.target_label) setScoreTargetText(p.target_label as string);
                if (p.next_escalation?.formatted) setNextEscalationDisplay(p.next_escalation.formatted as string);
                break;
            }
            case "posture_update": {
                const level = p.level as string;
                if (level) setPostureLevel(threatStringToPosture(level));
                if (p.axes) {
                    setPostureAxes(mapPostureAxes(p.axes as Record<string, any>));
                }
                break;
            }
            case "feed_item": {
                setFeed(prev => [{
                    id: nextFeedId(), timestamp: timestamp(),
                    source: p.source as string || "SYSTEM",
                    text: p.text as string || "",
                    category: (p.category as string || "INTERNAL") as FeedItem["category"],
                    isNew: true,
                    isBreaking: p.is_breaking as boolean || false,
                }, ...prev].slice(0, 80));
                break;
            }
            case "agent_ready": {
                // New agent was summoned and is ready — refresh agents from API
                if (sessionId && token) {
                    getAgents(sessionId, token).then(res => {
                        setAgents(res.agents.slice(0, 4).map(apiAgentToRosterAgent));
                        setTrustScores(res.agents.map(a => ({
                            agentName: a.character_name.split(" ").pop() ?? a.agent_id,
                            score: a.trust_score,
                        })));
                    }).catch(err => console.warn("[WAR ROOM] Failed to refresh agents after summon:", err));
                }
                break;
            }
            case "decision_agreed": {
                const text = p.text as string || "";
                const proposedBy = p.proposed_by as string || p.agent_id as string || "SYSTEM";
                setDecisions(prev => [{
                    id: (p.decision_id as string) || `wd-${Date.now()}`,
                    text, time: timestamp(), proposedBy, isNew: true,
                }, ...prev].slice(0, 30));
                clearNewFlags();
                break;
            }
            case "conflict_opened": {
                const desc = p.description as string || "";
                const agents_inv = (p.agents_involved as string[]) || [];
                setConflicts(prev => [{
                    id: (p.conflict_id as string) || `wc-${Date.now()}`,
                    description: desc,
                    agentA: agents_inv[0] ?? "AGENT A",
                    agentB: agents_inv[1] ?? "AGENT B",
                    isNew: true,
                }, ...prev].slice(0, 20));
                clearNewFlags();
                break;
            }
            case "conflict_resolved": {
                const conflictId = p.conflict_id as string;
                if (conflictId) {
                    setConflicts(prev => prev.filter(c => c.id !== conflictId));
                }
                break;
            }
            case "intel_dropped": {
                const text = p.text as string || "";
                const source = p.source as string || "INTERNAL";
                setIntel(prev => [{
                    id: (p.intel_id as string) || `wi-${Date.now()}`,
                    text, source, isNew: true,
                }, ...prev].slice(0, 30));
                clearNewFlags();
                break;
            }
            // ── TURN MANAGEMENT: backend TurnManager events ──────────────────
            case "turn_started": {
                // The TurnManager says THIS agent now has the floor.
                // Hard-stop only if another agent is actively marked speaking.
                // This avoids clipping the natural tail of just-finished playback.
                const agentId = p.agent_id as string;
                const current = activeSpeakerRef.current;
                if (
                    current &&
                    current !== agentId &&
                    agents.some(a => a.id === current && a.status === "speaking")
                ) {
                    stopAllAgents();
                }
                setActiveSpeakerId(agentId);
                activeSpeakerRef.current = agentId;
                setAgents(prev => prev.map(a => ({
                    ...a,
                    status: a.id === agentId
                        ? "speaking" as const
                        : (a.status === "dismissed" ? "dismissed" : "listening"),
                })));
                setLiveTranscripts(prev => ({ ...prev, [agentId]: "" }));
                break;
            }
            case "turn_ended": {
                const agentId = p.agent_id as string;
                if (activeSpeakerRef.current === agentId) {
                    setActiveSpeakerId(null);
                    activeSpeakerRef.current = null;
                }
                setAgents(prev => prev.map(a =>
                    a.id === agentId ? { ...a, status: "listening" as const } : a
                ));
                break;
            }
            default:
                break;
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [agents, resolutionScore, sessionId, token, stopAgent]);

    // ── Audio chunk handler ───────────────────────────────────────────────────
    // AUDIO GATE: Only play audio from the active speaker.
    // All other chunks are silently dropped to prevent voice leakage.
    const handleAudioChunk = useCallback((agentId: string, audioBase64: string) => {
        // Pod routing gate: play audio only from connected pod agents.
        if (connectedPodAgents.size > 0 && !connectedPodAgents.has(agentId)) {
            return;
        }
        const currentSpeaker = activeSpeakerRef.current;
        // If no active speaker yet (first chunk), allow it
        if (currentSpeaker !== null && currentSpeaker !== agentId) {
            // Different agent owns the gate — drop this chunk
            return;
        }
        if (currentSpeaker === null) {
            // First chunk from this agent while gate is free — claim it
            activeSpeakerRef.current = agentId;
            setActiveSpeakerId(agentId);
        }
        playChunk(agentId, audioBase64);
    }, [playChunk, connectedPodAgents]);

    // ── WebSocket connection ──────────────────────────────────────────────────
    const { connected: wsConnected, sendMessage } = useWarRoomSocket({
        sessionId,
        token,
        onEvent: handleWSEvent,
        onAudioChunk: handleAudioChunk,
    });

    // ── Route protection + session hydration ────────────────────────────────

    useEffect(() => {
        const creds = loadSession();

        if (!creds || (params?.session_id && creds.sessionId !== params.session_id)) {
            router.replace("/");
            return;
        }

        setSessionId(creds.sessionId);
        setToken(creds.token);
        setChairmanName(creds.chairmanName || "DIRECTOR");

        const hydrate = async () => {
            // 1. Get session state
            try {
                const state = await getSessionState(creds.sessionId, creds.token);
                if (state.crisis_title) setCrisisTitle(state.crisis_title);
                if (state.threat_level) setThreatLevel(threatStringToLabel(state.threat_level));
                if (state.resolution_score) {
                    setResolutionScore(state.resolution_score);
                    setScoreDelta(0);
                }
                if (state.timer?.remaining_seconds) setSessionTimeLeft(state.timer.remaining_seconds);
                if (state.threat_level) setPostureLevel(threatStringToPosture(state.threat_level));
            } catch (err) {
                console.warn("[WAR ROOM] ⚠️ getSessionState API failed — using simulated session state:", err);
            }

            // 2. Get agents from the REAL agent API (not scenario)
            try {
                const agentRes = await getAgents(creds.sessionId, creds.token);
                if (agentRes.agents?.length) {
                    const realAgents = agentRes.agents.slice(0, 4).map(apiAgentToRosterAgent);
                    setAgents(realAgents);
                    setUsingRealAgents(true);

                    setTrustScores(agentRes.agents.map(a => ({
                        agentName: a.character_name.split(" ").pop() ?? a.agent_id,
                        score: a.trust_score,
                    })));

                    console.log(`[WAR ROOM] ✅ Loaded ${agentRes.agents.length} real agents from API`);
                }
            } catch (err) {
                console.warn("[WAR ROOM] ⚠️ getAgents API failed — using simulated agent data:", err);

                // Fallback to scenario API
                try {
                    const scenario = await getScenario(creds.sessionId, creds.token);
                    if (scenario.scenario_ready) {
                        const full = scenario as import("@/lib/api").ScenarioResponse;
                        if (full.agents?.length) {
                            setAgents(full.agents.slice(0, 4).map(scenarioAgentToRosterAgent));
                            setTrustScores(full.agents.map(a => ({
                                agentName: a.character_name.split(" ").pop() ?? a.role_key,
                                score: 75,
                            })));
                            console.warn("[WAR ROOM] ⚠️ Fell back to scenario API for agents — using simulated statuses");
                        }
                        if (full.initial_intel?.length) {
                            setIntel(full.initial_intel.map((item, idx) => ({
                                id: `real-i${idx}`, text: item.text, source: item.source,
                            })));
                        }
                        if (full.initial_conflicts?.length) {
                            setConflicts(full.initial_conflicts.map((c, idx) => ({
                                id: `real-c${idx}`, description: c.description,
                                agentA: c.agents_involved[0] ?? "AGENT A",
                                agentB: c.agents_involved[1] ?? "AGENT B",
                            })));
                        }
                    }
                } catch (err2) {
                    console.warn("[WAR ROOM] ⚠️ getScenario API also failed — using full simulated data:", err2);
                }
            }

            // 3. Crisis Board (decisions, conflicts, intel)
            try {
                const boardRes = await getBoard(creds.sessionId, creds.token);
                if (boardRes?.agreed_decisions?.length) {
                    setDecisions(boardRes.agreed_decisions.map((d: Record<string, unknown>, idx: number) => ({
                        id: (d.decision_id as string) || `bd-${idx}`,
                        text: (d.text as string) || "",
                        time: ((d.agreed_at as string) || "").slice(11, 19) || timestamp(),
                        proposedBy: (d.proposed_by as string) || "SYSTEM",
                        locked: (d.locked as boolean) || false,
                    })));
                }
                if (boardRes?.open_conflicts?.length) {
                    setConflicts(boardRes.open_conflicts.map((c: Record<string, unknown>, idx: number) => ({
                        id: (c.conflict_id as string) || `bc-${idx}`,
                        description: (c.description as string) || "",
                        agentA: ((c.agents_involved as string[]) || [])[0] ?? "AGENT A",
                        agentB: ((c.agents_involved as string[]) || [])[1] ?? "AGENT B",
                    })));
                }
                if (boardRes?.critical_intel) {
                    const intelArray = Array.isArray(boardRes.critical_intel) ? boardRes.critical_intel : [];
                    setIntel(intelArray.map((i: Record<string, unknown>, idx: number) => ({
                        id: (i.intel_id as string) || `bi-${idx}`,
                        text: (i.text as string) || "",
                        source: (i.source as string) || "INTERNAL",
                    })));
                }
                console.log("[WAR ROOM] \u2705 Board data loaded from API");
            } catch (err) {
                console.warn("[WAR ROOM] \u26a0\ufe0f getBoard API failed \u2014 using fallback:", err);
            }

            // 4. Crisis Feed
            try {
                const feedRes = await getFeed(creds.sessionId, creds.token);
                if (feedRes?.items?.length) {
                    setFeed(feedRes.items.map((item: Record<string, unknown>, idx: number) => ({
                        id: (item.item_id as string) || `ff-${idx}`,
                        timestamp: ((item.timestamp as string) || "").slice(11, 19) || timestamp(),
                        source: (item.source as string) || "SYSTEM",
                        text: (item.text as string) || "",
                        category: ((item.category as string) || "INTERNAL") as FeedItem["category"],
                        isBreaking: (item.is_breaking as boolean) || false,
                    })));
                    console.log(`[WAR ROOM] \u2705 Loaded ${feedRes.items.length} feed items from API`);
                }
            } catch (err) {
                console.warn("[WAR ROOM] \u26a0\ufe0f getFeed API failed \u2014 using fallback:", err);
            }

            // 5. Room Intelligence + Trust Scores
            try {
                const intelRes = await getIntel(creds.sessionId, creds.token);
                if (intelRes?.insights?.length) {
                    setIntelAlerts(intelRes.insights.map((ins: Record<string, unknown>) => {
                        let meta = undefined;
                        if (Array.isArray(ins.agents_referenced) && ins.agents_referenced.length > 0) {
                            const names = ins.agents_referenced.map(id => typeof id === 'string' ? id.split('_')[0].toUpperCase() : '');
                            const type = ((ins.type || ins.insight_type) as string || "").toLowerCase();
                            meta = names.filter(Boolean).join(type === "alliance" ? " & " : " vs ");
                        }
                        return {
                            id: (ins.insight_id as string) || `ri-${Date.now()}`,
                            type: (((ins.type || ins.insight_type) as string) || "BLIND_SPOT").toUpperCase() as "CONTRADICTION" | "ALLIANCE" | "BLIND_SPOT",
                            text: ((ins.body || ins.text) as string) || "",
                            timestamp: (((ins.detected_at || ins.timestamp) as string) || "").slice(11, 19) || timestamp(),
                            meta,
                        };
                    }));
                }
            } catch { /* keep fallback */ }

            try {
                const trustRes = await getTrustScores(creds.sessionId, creds.token);
                if (trustRes?.trust_scores) {
                    setTrustScores(trustRes.trust_scores.map((ts: any) => ({
                        agentName: ts.character_name?.split(" ").pop() ?? ts.agent_id ?? "AGENT",
                        score: ts.score ?? 70,
                    })));
                }
            } catch { /* keep fallback */ }

            // 6. Crisis Posture
            try {
                const postureRes = await getPosture(creds.sessionId, creds.token);
                if (postureRes?.axes) {
                    const axes = postureRes.axes as Record<string, { value: number }>;
                    const avgValue = Object.values(axes).reduce(
                        (sum, ax) => sum + (ax?.value || 50), 0
                    ) / Math.max(Object.keys(axes).length, 1);
                    setPostureLevel(threatStringToPosture(
                        avgValue >= 70 ? "meltdown" : avgValue >= 55 ? "critical"
                            : avgValue >= 40 ? "elevated" : "contained"
                    ));
                    setPostureAxes(mapPostureAxes(axes));
                }
            } catch { /* keep fallback */ }

            // 7. Resolution Score
            try {
                const scoreRes = await getScore(creds.sessionId, creds.token);
                if (scoreRes?.score !== undefined) {
                    setResolutionScore(scoreRes.score as number);
                    setScoreDelta((scoreRes.delta_last_change as number) ?? 0);
                    if (scoreRes.label) {
                        setThreatLevel(threatStringToLabel(scoreRes.label as string));
                    }
                    if (scoreRes.trend) {
                        const t = (scoreRes.trend as string).toUpperCase();
                        setScoreTrend(t === "IMPROVING" ? "IMPROVING" : t === "DECLINING" ? "FALLING" : "STABLE");
                    }
                    if (scoreRes.driver) setScoreDriver(scoreRes.driver as string);
                    if (scoreRes.target_label) setScoreTargetText(scoreRes.target_label as string);
                    if (scoreRes.next_escalation?.formatted) setNextEscalationDisplay(scoreRes.next_escalation.formatted as string);
                }
            } catch { /* keep fallback */ }

            // 8. Voice pods (fixed 4 + summon slot)
            try {
                const podsRes = await getVoicePods(creds.sessionId, creds.token);
                setVoicePods(podsRes.pods);
                setConnectedPodAgents(new Set(
                    podsRes.pods
                        .filter(p => p.connected && !!p.agent_id)
                        .map(p => p.agent_id as string)
                ));
            } catch { /* ignore */ }
        };

        hydrate();

        // Periodic refresh every 30s
        const refreshInterval = setInterval(async () => {
            try {
                const state = await getSessionState(creds.sessionId, creds.token);
                if (state.timer?.remaining_seconds !== undefined) setSessionTimeLeft(state.timer.remaining_seconds);
                if (state.resolution_score !== undefined) setResolutionScore(state.resolution_score);
                if (state.threat_level) {
                    setThreatLevel(threatStringToLabel(state.threat_level));
                    setPostureLevel(threatStringToPosture(state.threat_level));
                }
            } catch { /* silently ignore refresh errors */ }

            try {
                const postureRes = await getPosture(creds.sessionId, creds.token);
                if (postureRes?.axes) {
                    setPostureAxes(mapPostureAxes(postureRes.axes as Record<string, any>));
                }
            } catch { /* ignore */ }

            // Also refresh agents periodically
            try {
                const agentRes = await getAgents(creds.sessionId, creds.token);
                if (agentRes.agents?.length) {
                    setAgents(agentRes.agents.slice(0, 4).map(apiAgentToRosterAgent));
                    setTrustScores(agentRes.agents.map(a => ({
                        agentName: a.character_name.split(" ").pop() ?? a.agent_id,
                        score: a.trust_score,
                    })));
                }
            } catch { /* silently ignore */ }

            try {
                const podsRes = await getVoicePods(creds.sessionId, creds.token);
                setVoicePods(podsRes.pods);
                setConnectedPodAgents(new Set(
                    podsRes.pods
                        .filter(p => p.connected && !!p.agent_id)
                        .map(p => p.agent_id as string)
                ));
            } catch { /* ignore */ }

            // Polling for World Agent / Resolution Score / Chairman sync
            try {
                const scoreRes = await getScore(creds.sessionId, creds.token);
                if (scoreRes?.score !== undefined) {
                    setResolutionScore(scoreRes.score as number);
                    setScoreDelta((scoreRes.delta_last_change as number) ?? 0);
                    if (scoreRes.trend) setScoreTrend((scoreRes.trend as string).toUpperCase() as "IMPROVING" | "FALLING" | "STABLE");
                    if (scoreRes.next_escalation?.formatted) setNextEscalationDisplay(scoreRes.next_escalation.formatted as string);
                }
            } catch { /* ignore */ }

            try {
                const worldRes = await getWorld(creds.sessionId, creds.token);
                if (worldRes?.next_escalation?.in_seconds !== undefined) {
                    // We only need getWorld to sync any specific world agent state not covered by getScore
                    // getScore.next_escalation provides the formatted string, but we can call getWorld to ensure
                    // the world events feed is up to date if they were missed by WS
                }
            } catch { /* ignore */ }

            try {
                const historyRes = await getCommandHistory(creds.sessionId, creds.token);
                if (historyRes?.commands) {
                    setCommandHistory(historyRes.commands.map((c: any) => c.text));
                }
            } catch { /* ignore */ }
        }, 30_000);

        return () => clearInterval(refreshInterval);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ── Resize logic ─────────────────────────────────────────────────────────

    const handleMouseDown = (side: "left" | "right" | "bottom") => {
        resizingSide.current = side;
        document.addEventListener("mousemove", handleMouseMove);
        document.addEventListener("mouseup", handleMouseUp);
        document.body.style.cursor = side === "bottom" ? "row-resize" : "col-resize";
    };

    const handleMouseMove = useCallback((e: MouseEvent) => {
        if (!resizingSide.current) return;
        if (resizingSide.current === "left") setLeftSidebarWidth(Math.max(160, Math.min(400, e.clientX)));
        else if (resizingSide.current === "right") setRightSidebarWidth(Math.max(160, Math.min(400, window.innerWidth - e.clientX)));
        else if (resizingSide.current === "bottom") setBottomHeight(Math.max(100, Math.min(400, window.innerHeight - e.clientY - 60)));
    }, []);

    const handleMouseUp = useCallback(() => {
        resizingSide.current = null;
        document.removeEventListener("mousemove", handleMouseMove);
        document.removeEventListener("mouseup", handleMouseUp);
        document.body.style.cursor = "default";
    }, [handleMouseMove]);

    // ── Session countdown — auto-ends when timer reaches 0 ───────────────────

    const sessionEndingRef = useRef(false);

    useEffect(() => {
        const t = setInterval(() => {
            setSessionTimeLeft(s => {
                const next = Math.max(0, s - 1);
                if (next === 0 && !sessionEndingRef.current) {
                    // Time's up — auto-dismiss all agents and end session
                    sessionEndingRef.current = true;
                    setSessionEnding(true);
                    stopAllAgents();
                    setAgents(prev => prev.map(a => ({ ...a, status: "dismissed" as const })));
                    setActiveSpeakerId(null);
                    if (sessionId && token) {
                        deleteSession(sessionId, token).catch(() => { });
                    }
                    clearSession();
                    setTimeout(() => router.replace("/"), 3000);
                }
                return next;
            });
        }, 1000);
        return () => clearInterval(t);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [sessionId, token]);

    // ── Remove "isNew" flags after 4 seconds ──────────────────────────────────

    const clearNewFlags = useCallback(() => {
        setTimeout(() => {
            setFeed(f => f.map(e => ({ ...e, isNew: false })));
            setDecisions(d => d.map(e => ({ ...e, isNew: false })));
            setConflicts(c => c.map(e => ({ ...e, isNew: false })));
            setIntel(i => i.map(e => ({ ...e, isNew: false })));
        }, 4000);
    }, []);

    // ── Feed helper ───────────────────────────────────────────────────────────

    const addFeedEntry = useCallback((entry: Omit<FeedItem, "id" | "timestamp" | "isNew">) => {
        const newEntry: FeedItem = { ...entry, id: nextFeedId(), timestamp: timestamp(), isNew: true };
        setFeed(f => [newEntry, ...f].slice(0, 80));
        clearNewFlags();
    }, [clearNewFlags]);

    // ── Simulation tick (ONLY runs when WS is disconnected and no real agents) ─

    const rotateAgentStatuses = useCallback(() => {
        const statusCycle: Array<Agent["status"]> = ["speaking", "thinking", "listening", "silent", "listening"];
        setAgents(prev => {
            const updated = [...prev];
            const idx = Math.floor(Math.random() * updated.length);
            const current = updated[idx].status;
            const nextStatus = statusCycle[(statusCycle.indexOf(current) + 1) % statusCycle.length];
            updated[idx] = { ...updated[idx], status: nextStatus };
            const speaking = updated.find(a => a.status === "speaking");
            setActiveSpeakerId(speaking?.id ?? null);
            return updated;
        });
    }, []);

    useEffect(() => {
        // Disabled: synthetic simulation fallback can conflict with real-time voice UX.
        return;
    }, []);

    // ── Dismiss agent (uses PATCH API) ────────────────────────────────────────

    const handleDismissAgent = useCallback(async (agentId: string, agentName: string) => {
        // Visual feedback immediately
        setAgents(prev => prev.map(a => a.id === agentId ? { ...a, status: "dismissed" as const } : a));
        addFeedEntry({ source: "SYSTEM", category: "INTERNAL", text: `// Agent ${agentName} dismissed by chairman.` });

        if (sessionId && token) {
            try {
                const result = await patchAgent(sessionId, token, agentId, "dismiss");
                console.log(`[WAR ROOM] ✅ Agent dismissed: ${result.effect}`);
                addFeedEntry({ source: "SYSTEM", category: "INTERNAL", text: result.effect });
            } catch (err) {
                console.warn("[WAR ROOM] ⚠️ patchAgent(dismiss) API failed:", err);
            }
        }
    }, [addFeedEntry, sessionId, token]);

    // ── Silence agent ─────────────────────────────────────────────────────────

    const handleSilenceAgent = useCallback(async (agentId: string, durationSeconds: number = 60) => {
        setAgents(prev => prev.map(a => a.id === agentId ? { ...a, status: "silent" as const } : a));
        const agentName = agents.find(a => a.id === agentId)?.name ?? agentId;
        addFeedEntry({ source: "SYSTEM", category: "INTERNAL", text: `// Agent ${agentName} silenced for ${durationSeconds}s.` });

        if (sessionId && token) {
            try {
                const result = await patchAgent(sessionId, token, agentId, "silence", durationSeconds);
                console.log(`[WAR ROOM] ✅ Agent silenced: ${result.effect}`);
            } catch (err) {
                console.warn("[WAR ROOM] ⚠️ patchAgent(silence) API failed:", err);
            }
        }
    }, [addFeedEntry, agents, sessionId, token]);

    // ── Address agent ─────────────────────────────────────────────────────────

    const handleAddressAgent = useCallback(async (agentId: string) => {
        setAgents(prev => prev.map(a => a.id === agentId ? { ...a, status: "listening" as const } : a));

        if (sessionId && token) {
            try {
                await patchAgent(sessionId, token, agentId, "address");
                await patchActiveVoiceAgent(sessionId, token, agentId);
            } catch (err) {
                console.warn("[WAR ROOM] ⚠️ patchAgent(address) API failed:", err);
            }
        }
    }, [sessionId, token]);

    // ── Summon agent ──────────────────────────────────────────────────────────

    const handleSummon = useCallback(async () => {
        if (!summonInput.trim() || !sessionId || !token) return;
        setSummoning(true);

        try {
            const result = await summonAgent(sessionId, token, summonInput.trim());
            console.log(`[WAR ROOM] ✅ Summon initiated: ${result.message}`);
            addFeedEntry({ source: "SYSTEM", category: "INTERNAL", text: `// Summoning new agent: "${summonInput.trim()}"... ETA ~${result.estimated_seconds}s` });
            setShowSummonModal(false);
            setSummonInput("");
        } catch (err) {
            console.warn("[WAR ROOM] ⚠️ summonAgent API failed:", err);
            addFeedEntry({ source: "SYSTEM", category: "INTERNAL", text: `// Summon failed: ${err}` });
        } finally {
            setSummoning(false);
        }
    }, [addFeedEntry, sessionId, summonInput, token]);

    // ── Chairman mic (real audio capture) ─────────────────────────────────────

    const chairmanMic = useChairmanMic({
        sessionId,
        token,
        targetAgentId: selectedAgentId,
    });
    const { isActive: isChairmanMicActive, stopMic: stopChairmanMic } = chairmanMic;

    // Prevent audio feedback loops:
    // when an agent starts speaking, stop chairman mic capture immediately.
    useEffect(() => {
        if (activeSpeakerId && isChairmanMicActive) {
            stopChairmanMic();
        }
    }, [activeSpeakerId, isChairmanMicActive, stopChairmanMic]);

    // ── Chairman command ──────────────────────────────────────────────────────

    const handleCommand = useCallback(async (cmd: string) => {
        setCommandHistory(h => [...h, cmd]);
        addFeedEntry({ source: "CHAIRMAN", category: "INTERNAL", text: `[CMD] ${cmd}` });
        const upper = cmd.toUpperCase();

        // Determine if this is a structural command or free-text
        const STRUCTURAL_COMMANDS = [
            "PAUSE", "RESUME", "END SESSION", "CLOSE SESSION",
            "ESCALATE", "DEESCALATE", "DANGER LEVEL",
            "LOCK", "FORCE VOTE", "DISMISS", "STATUS"
        ];
        const isStructural = STRUCTURAL_COMMANDS.some(sc => upper.startsWith(sc) || upper.includes(sc));

        // Free-text chairman speech: silence any speaking agent immediately
        if (!isStructural) {
            const speaking = agents.filter(a => a.status === "speaking");
            speaking.forEach(a => stopAgent(a.id));
        }

        if (isStructural) {
            // Structural commands → type 'command' → chairman_handler.py
            sendMessage({ type: "command", command: cmd });
        } else {
            // Free-text → type 'chairman_speech' → agents' Gemini Live sessions
            if (wsConnected) {
                sendMessage({
                    type: "chairman_speech",
                    text: cmd,
                    target_agent_id: selectedAgentId ?? undefined,
                });
            } else if (sessionId && token) {
                // Fallback path when WS is down.
                sendChairmanCommand(
                    sessionId,
                    token,
                    cmd,
                    selectedAgentId ?? undefined,
                    "directive",
                ).catch((err) => {
                    console.warn("[WAR ROOM] Chairman command fallback failed:", err);
                });
            }
        }

        if (upper === "PAUSE ROOM" || upper === "PAUSE" || upper === "RESUME") {
            const nowPaused = !sessionPaused;
            setSessionPaused(nowPaused);
            addFeedEntry({ source: "SYSTEM", category: "INTERNAL", text: nowPaused ? "// Session PAUSED by chairman" : "// Session RESUMED by chairman" });
            if (sessionId && token) {
                try { await patchSession(sessionId, token, { paused: nowPaused }); } catch { /* non-critical */ }
            }
        }

        if (upper.includes("ESCALATE") || upper.includes("DANGER LEVEL UP")) {
            const levels = ["contained", "guarded", "elevated", "critical", "meltdown"];
            setPostureLevel(p => {
                const next = Math.min(5, p + 1) as PostureLevel;
                if (sessionId && token) patchSession(sessionId, token, { threat_level: levels[next - 1] }).catch(() => { });
                return next;
            });
        }
        if (upper.includes("DEESCALATE") || upper.includes("DANGER LEVEL DOWN")) {
            const levels = ["contained", "guarded", "elevated", "critical", "meltdown"];
            setPostureLevel(p => {
                const next = Math.max(1, p - 1) as PostureLevel;
                if (sessionId && token) patchSession(sessionId, token, { threat_level: levels[next - 1] }).catch(() => { });
                return next;
            });
        }

        if (upper === "END SESSION" || upper === "CLOSE SESSION") {
            if (sessionEnding) return;
            setSessionEnding(true);
            // Stop all agent audio immediately
            stopAllAgents();
            setAgents(prev => prev.map(a => ({ ...a, status: "dismissed" as const })));
            setActiveSpeakerId(null);
            addFeedEntry({ source: "SYSTEM", category: "INTERNAL", text: "// Session termination initiated. Releasing agents..." });
            if (sessionId && token) {
                try { await deleteSession(sessionId, token); } catch { /* proceed anyway */ }
            }
            clearSession();
            setTimeout(() => router.replace("/"), 2000);
            return;
        }

        if (upper.includes("LOCK DECISION") || upper.includes("LOCK")) {
            setResolutionScore(s => Math.min(100, s + 6));
            setScoreDelta(6);
        }
        if (upper.includes("CALL VOTE")) {
            addFeedEntry({ source: "SYSTEM", category: "INTERNAL", text: "// vote initiated by chairman — awaiting agent responses" });
        }
        if (upper.includes("BRIEF ALL")) {
            setAgents(prev => prev.map(ag => ag.status !== "dismissed" ? { ...ag, status: "listening" } : ag));
        }
        if (upper.includes("STATUS REPORT")) {
            addFeedEntry({ source: "ORACLE", category: "INTERNAL", text: `Status: ${agents.filter(a => a.status !== "silent" && a.status !== "dismissed").length} agents active. Posture level ${postureLevel}/5. Resolution score: ${resolutionScore}.` });
        }
        if (upper.startsWith("DISMISS ")) {
            const name = cmd.slice(8).trim();
            const target = agents.find(a => a.name.toUpperCase() === name.toUpperCase());
            if (target) handleDismissAgent(target.id, target.name);
        }
    }, [addFeedEntry, agents, handleDismissAgent, postureLevel, resolutionScore, router, sendMessage, sessionEnding, sessionId, sessionPaused, token, wsConnected, selectedAgentId, stopAgent, stopAllAgents]);

    // ── Ensure AudioContext on first user interaction ──────────────────────────
    useEffect(() => {
        const activate = () => { ensureContext(); document.removeEventListener("click", activate); };
        document.addEventListener("click", activate);
        return () => document.removeEventListener("click", activate);
    }, [ensureContext]);

    // ─── Render ───────────────────────────────────────────────────────────────

    return (
        <div
            ref={containerRef}
            className="war-room-app"
            style={{ display: "flex", flexDirection: "column", height: "100vh", overflow: "hidden" }}
        >
            {/* ── Top Command Bar ─────────────────────────────────── */}
            <TopCommandBar
                crisisTitle={crisisTitle}
                threatLevel={threatLevel}
                micActive={chairmanMic.isActive}
                sessionTimeLeft={sessionTimeLeft}
            />

            {/* ── Main Body ────────────────────────────────────────── */}
            <div style={{ flex: 1, display: "flex", overflow: "hidden", minHeight: 0 }}>

                {/* Left: Agent Roster (collapsible) */}
                <div
                    style={{
                        width: leftCollapsed ? "36px" : `${leftSidebarWidth}px`,
                        flexShrink: 0, display: "flex", flexDirection: "column", overflow: "hidden",
                        transition: "width 200ms ease", background: "#0D1117", borderRight: "1px solid #1E2D3D",
                    }}
                >
                    <div style={{
                        height: "36px", display: "flex", alignItems: "center",
                        justifyContent: leftCollapsed ? "center" : "flex-end",
                        padding: leftCollapsed ? "0" : "0 8px", borderBottom: "1px solid #1E2D3D", flexShrink: 0,
                    }}>
                        <button
                            onClick={() => setLeftCollapsed(c => !c)}
                            title={leftCollapsed ? "Expand panel" : "Collapse panel"}
                            style={{ background: "none", border: "none", cursor: "pointer", color: "#4A5568", fontSize: "14px", lineHeight: 1, padding: "4px", display: "flex", alignItems: "center", justifyContent: "center", borderRadius: "2px", transition: "color 150ms ease" }}
                            onMouseEnter={e => (e.currentTarget.style.color = "#4A9EFF")}
                            onMouseLeave={e => (e.currentTarget.style.color = "#4A5568")}
                        >
                            {leftCollapsed ? "›" : "‹"}
                        </button>
                    </div>
                    {!leftCollapsed && (
                        <div style={{ flex: 1, overflow: "hidden" }}>
                            <AgentRoster
                                agents={agents}
                                selectedAgentId={selectedAgentId}
                                onSelectAgent={(id) => {
                                    setSelectedAgentId(id);
                                    if (id) handleAddressAgent(id);
                                }}
                                onDismissAgent={handleDismissAgent}
                                onSilenceAgent={handleSilenceAgent}
                            />
                            {/* Summon Agent Button */}
                            <button
                                onClick={() => setShowSummonModal(true)}
                                style={{
                                    width: "100%", height: "48px", border: "1px dashed #1E2D3D",
                                    background: "transparent", cursor: "pointer", display: "flex",
                                    alignItems: "center", justifyContent: "center", gap: "6px",
                                    fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 600,
                                    fontSize: "11px", letterSpacing: "0.08em", color: "#4A5568",
                                    transition: "all 200ms ease",
                                }}
                                onMouseEnter={e => { e.currentTarget.style.borderColor = "#4A9EFF"; e.currentTarget.style.color = "#4A9EFF"; e.currentTarget.style.background = "rgba(74,158,255,0.04)"; }}
                                onMouseLeave={e => { e.currentTarget.style.borderColor = "#1E2D3D"; e.currentTarget.style.color = "#4A5568"; e.currentTarget.style.background = "transparent"; }}
                            >
                                + SUMMON AGENT
                            </button>
                        </div>
                    )}
                </div>

                {/* Resizer Left */}
                {!leftCollapsed && (
                    <div
                        onMouseDown={() => handleMouseDown("left")}
                        style={{ width: "4px", background: "#1E2D3D", cursor: "col-resize", zIndex: 50, transition: "background 150ms ease" }}
                        onMouseEnter={e => (e.currentTarget.style.background = "#4A9EFF")}
                        onMouseLeave={e => (e.currentTarget.style.background = "#1E2D3D")}
                    />
                )}

                {/* Center Column */}
                <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
                    <div style={{ flex: 1, overflow: "hidden", minHeight: 0 }}>
                        <CrisisBoard decisions={decisions} conflicts={conflicts} intel={intel} escalation={escalation} />
                    </div>

                    {/* Bottom Resizer + Collapse Toggle */}
                    <div
                        style={{ height: "4px", background: "#1E2D3D", cursor: bottomCollapsed ? "default" : "row-resize", zIndex: 50, display: "flex", alignItems: "center", justifyContent: "center", position: "relative", transition: "background 150ms ease" }}
                        onMouseDown={e => { const target = e.target as HTMLElement; if (target.tagName !== "BUTTON") handleMouseDown("bottom"); }}
                        onMouseEnter={e => { if (!bottomCollapsed) e.currentTarget.style.background = "#4A9EFF"; }}
                        onMouseLeave={e => (e.currentTarget.style.background = "#1E2D3D")}
                    >
                        <button
                            onClick={() => setBottomCollapsed(c => !c)}
                            title={bottomCollapsed ? "Expand bottom panel" : "Collapse bottom panel"}
                            style={{ position: "absolute", transform: bottomCollapsed ? "translateY(-16px)" : "none", background: "#1E2D3D", border: "1px solid #2A3D50", borderRadius: "2px", color: "#4A5568", fontSize: "11px", lineHeight: 1, padding: "2px 6px", cursor: "pointer", zIndex: 60, transition: "all 150ms ease" }}
                            onMouseEnter={e => { e.currentTarget.style.color = "#4A9EFF"; e.currentTarget.style.borderColor = "#4A9EFF"; }}
                            onMouseLeave={e => { e.currentTarget.style.color = "#4A5568"; e.currentTarget.style.borderColor = "#2A3D50"; }}
                        >
                            {bottomCollapsed ? "∧" : "∨"}
                        </button>
                    </div>

                    {!bottomCollapsed && (
                        <div style={{ height: `${bottomHeight}px`, flexShrink: 0, display: "flex", overflow: "hidden" }}>
                            <div style={{ width: "260px", flexShrink: 0, borderRight: "1px solid #1E2D3D", overflow: "hidden" }}>
                                <CrisisFeed items={feed} />
                            </div>
                            <div style={{ flex: 1, overflow: "hidden" }}>
                                <AgentVoicePods
                                    agents={agents}
                                    liveTranscripts={liveTranscripts}
                                    activeSpeakerId={activeSpeakerId}
                                    onSummon={() => setShowSummonModal(true)}
                                />
                            </div>
                        </div>
                    )}
                </div>

                {/* Resizer Right */}
                <div
                    onMouseDown={() => handleMouseDown("right")}
                    style={{ width: "4px", background: "#1E2D3D", cursor: "col-resize", zIndex: 50, transition: "background 150ms ease" }}
                    onMouseEnter={e => (e.currentTarget.style.background = "#4A9EFF")}
                    onMouseLeave={e => (e.currentTarget.style.background = "#1E2D3D")}
                />

                {/* Right: Panel Stack */}
                <div style={{ width: `${rightSidebarWidth}px`, flexShrink: 0, display: "flex", flexDirection: "column", overflow: "hidden", background: "#0D1117" }}>
                    <div className="wr-scrollbar" style={{ flex: 1, overflowY: "auto" }}>
                        <RoomIntelligence items={dynamicIntelItems} alerts={intelAlerts} trustScores={trustScores} />
                        <div style={{ borderTop: "1px solid #1E2D3D" }}>
                            <CrisisPosture
                                level={postureLevel}
                                label=""
                                axes={postureAxes}
                                detail={
                                    postureLevel <= 1 ? "Situation under control. Monitoring."
                                        : postureLevel <= 2 ? "Elevated activity. Enhanced vigilance."
                                            : postureLevel <= 3 ? "Active threat confirmed. Response ongoing."
                                                : postureLevel <= 4 ? "Critical breach in progress. All hands."
                                                    : "MELTDOWN — cascading failure. Extreme measures."
                                }
                            />
                        </div>
                        <div style={{ borderTop: "1px solid #1E2D3D" }}>
                            <ResolutionScore
                                score={resolutionScore}
                                delta={scoreDelta}
                                contributors={dynamicContributors}
                                trend={scoreTrend}
                                keyDriver={scoreDriver}
                                targetText={scoreTargetText}
                                nextEscalation={nextEscalationDisplay}
                            />
                        </div>
                    </div>
                </div>
            </div>

            {/* ── Chairman Command Bar ─────────────────────────────── */}
            <ChairmanCommandBar
                onSendCommand={handleCommand}
                isMicActive={chairmanMic.isActive}
                onToggleMic={async () => {
                    if (chairmanMic.isActive) {
                        chairmanMic.stopMic();
                    } else {
                        await chairmanMic.startMic();
                    }
                }}
                commandHistory={commandHistory}
                chairmanName={chairmanName}
                agents={agents.map(a => ({ id: a.id, name: a.name }))}
            />

            {/* ── Summon Agent Modal ───────────────────────────────── */}
            {showSummonModal && (
                <div
                    style={{
                        position: "fixed", inset: 0, zIndex: 200,
                        background: "rgba(0,0,0,0.7)", display: "flex",
                        alignItems: "center", justifyContent: "center",
                    }}
                    onClick={() => { if (!summoning) setShowSummonModal(false); }}
                >
                    <div
                        onClick={e => e.stopPropagation()}
                        style={{
                            background: "#111820", border: "1px solid #1E2D3D",
                            padding: "24px", width: "420px", maxWidth: "90vw",
                        }}
                    >
                        <div style={{
                            fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 600,
                            fontSize: "14px", letterSpacing: "0.12em", color: "#4A9EFF",
                            marginBottom: "16px",
                        }}>
                            SUMMON NEW AGENT
                        </div>
                        <div style={{
                            fontFamily: "'IBM Plex Mono', monospace", fontSize: "11px",
                            color: "#8A9BB0", marginBottom: "12px",
                        }}>
                            Describe the role or expertise needed. The AI will generate a new agent with appropriate skills.
                        </div>
                        <input
                            type="text"
                            value={summonInput}
                            onChange={e => setSummonInput(e.target.value)}
                            onKeyDown={e => { if (e.key === "Enter") handleSummon(); }}
                            placeholder="e.g. Cybersecurity Expert, Crisis Negotiator..."
                            disabled={summoning}
                            autoFocus
                            style={{
                                width: "100%", padding: "10px 12px", marginBottom: "16px",
                                background: "#0D1117", border: "1px solid #1E2D3D",
                                color: "#E8EDF2", fontFamily: "'IBM Plex Mono', monospace",
                                fontSize: "12px", outline: "none",
                            }}
                        />
                        <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
                            <button
                                onClick={() => setShowSummonModal(false)}
                                disabled={summoning}
                                style={{
                                    padding: "8px 16px", background: "transparent",
                                    border: "1px solid #1E2D3D", color: "#8A9BB0",
                                    fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 500,
                                    fontSize: "11px", letterSpacing: "0.06em", cursor: "pointer",
                                }}
                            >
                                CANCEL
                            </button>
                            <button
                                onClick={handleSummon}
                                disabled={summoning || !summonInput.trim()}
                                style={{
                                    padding: "8px 16px",
                                    background: summoning ? "rgba(74,158,255,0.15)" : "rgba(74,158,255,0.1)",
                                    border: "1px solid #4A9EFF", color: "#4A9EFF",
                                    fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 600,
                                    fontSize: "11px", letterSpacing: "0.06em",
                                    cursor: summoning ? "wait" : "pointer",
                                    opacity: !summonInput.trim() ? 0.4 : 1,
                                }}
                            >
                                {summoning ? "GENERATING..." : "SUMMON"}
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── WS Connection Status (debug) ─────────────────────── */}
            <div style={{
                position: "fixed", bottom: "56px", right: "8px", zIndex: 150,
                fontFamily: "'IBM Plex Mono', monospace", fontSize: "9px",
                color: wsConnected ? "#00C896" : "#4A5568", letterSpacing: "0.06em",
            }}>
                {wsConnected ? "● WS LIVE" : "○ WS OFFLINE"}
            </div>
        </div>
    );
}
