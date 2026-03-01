/**
 * WAR ROOM — API Client
 * Typed fetch wrappers for all implemented backend endpoints.
 * 
 * Base URL resolves from NEXT_PUBLIC_API_URL env var.
 * Works in development (localhost:8000) and production.
 */

const API_BASE =
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

// ── Types (mirror backend Pydantic models) ────────────────────────────────────

export interface CreateSessionResponse {
    session_id: string;
    chairman_token: string;
    status: string;
    ws_url: string;
    created_at: string;
    message: string;
}

export interface TimerInfo {
    session_duration_seconds: number;
    elapsed_seconds: number;
    remaining_seconds: number;
    formatted: string;
}

export interface SessionStateResponse {
    session_id: string;
    status: string;
    crisis_title: string;
    crisis_domain: string;
    crisis_brief: string;
    threat_level: string;
    resolution_score: number;
    created_at: string | null;
    timer: TimerInfo | null;
    chairman_name: string;
    agent_count: number;
}

export interface AssemblyLogEntry {
    line: string;
    value: string;
    status: "in_progress" | "complete";
}

export interface ScenarioAgent {
    agent_id: string;
    role_key: string;
    role_title: string;
    character_name: string;
    defining_line: string;
    identity_color: string;
    voice_name: string;
    status: string;
}

export interface ScenarioResponse {
    session_id: string;
    crisis_title: string;
    crisis_domain: string;
    crisis_brief: string;
    threat_level_initial: string;
    resolution_score_initial: number;
    agents: ScenarioAgent[];
    initial_intel: Array<{ text: string; source: string }>;
    initial_conflicts: Array<{ description: string; agents_involved: string[] }>;
    escalation_schedule: Array<{ delay_minutes: number; event_text: string; type: string }>;
    assembly_log: AssemblyLogEntry[];
    scenario_ready: boolean;
}

export interface ScenarioPollingResponse {
    scenario_ready: false;
    assembly_log: AssemblyLogEntry[];
    message: string;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function authHeaders(token: string): HeadersInit {
    return {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
    };
}

async function handle<T>(res: Response): Promise<T> {
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`API error ${res.status}: ${body}`);
    }
    return res.json() as Promise<T>;
}

// ── Session routes ─────────────────────────────────────────────────────────────

/**
 * POST /api/sessions
 * Creates a new crisis session. Returns immediately while bootstrap runs async.
 */
export async function createSession(
    crisisInput: string,
    chairmanName: string = "DIRECTOR",
    sessionDurationMinutes: number = 30
): Promise<CreateSessionResponse> {
    const res = await fetch(`${API_BASE}/api/sessions`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            crisis_input: crisisInput,
            chairman_name: chairmanName,
            session_duration_minutes: sessionDurationMinutes,
        }),
    });
    return handle<CreateSessionResponse>(res);
}

/**
 * GET /api/sessions/{session_id}
 * Returns full session state with timer.
 */
export async function getSessionState(
    sessionId: string,
    token: string
): Promise<SessionStateResponse> {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
        headers: authHeaders(token),
    });
    return handle<SessionStateResponse>(res);
}

/**
 * PATCH /api/sessions/{session_id}
 * Update session-level settings (pause, status, threat).
 */
export async function patchSession(
    sessionId: string,
    token: string,
    patch: { status?: string; paused?: boolean; threat_level?: string }
): Promise<{ session_id: string; updated_fields: string[]; current_state: object }> {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
        method: "PATCH",
        headers: authHeaders(token),
        body: JSON.stringify(patch),
    });
    return handle(res);
}

/**
 * DELETE /api/sessions/{session_id}
 * End session and release agents.
 */
export async function deleteSession(
    sessionId: string,
    token: string
): Promise<{ session_id: string; closed_at: string; agents_released: number }> {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}`, {
        method: "DELETE",
        headers: authHeaders(token),
    });
    return handle(res);
}

// ── Scenario routes ────────────────────────────────────────────────────────────

/**
 * GET /api/sessions/{session_id}/scenario
 * Returns 200 with full spec when ready, 202 with partial assembly_log while assembling.
 */
export async function getScenario(
    sessionId: string,
    token: string
): Promise<ScenarioResponse | ScenarioPollingResponse> {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/scenario`, {
        headers: authHeaders(token),
    });

    if (res.status === 202) {
        return res.json() as Promise<ScenarioPollingResponse>;
    }
    if (!res.ok) {
        const body = await res.text();
        throw new Error(`Scenario poll error ${res.status}: ${body}`);
    }
    return res.json() as Promise<ScenarioResponse>;
}

/**
 * Poll getScenario until scenario_ready=true.
 * Calls onLog with each updated assembly_log for the loading screen.
 * Returns the full ScenarioResponse.
 */
export async function pollUntilReady(
    sessionId: string,
    token: string,
    onLog: (log: AssemblyLogEntry[]) => void,
    intervalMs: number = 1500,
    timeoutMs: number = 90_000
): Promise<ScenarioResponse> {
    const deadline = Date.now() + timeoutMs;

    while (Date.now() < deadline) {
        const result = await getScenario(sessionId, token);
        onLog(result.assembly_log);

        if (result.scenario_ready) {
            return result as ScenarioResponse;
        }

        await new Promise((r) => setTimeout(r, intervalMs));
    }

    throw new Error("Scenario assembly timed out after 90 seconds");
}

// ── Agent types ────────────────────────────────────────────────────────────────

export interface AgentListItem {
    agent_id: string;
    character_name: string;
    role_title: string;
    identity_color: string;
    voice_name: string;
    livekit_room?: string | null;
    livekit_identity?: string | null;
    pod_id?: string;
    pod_connected?: boolean;
    status: string;
    trust_score: number;
    last_spoke_at: string | null;
    last_statement: string;
    conflict_with: string[];
    silence_duration_seconds: number;
}

export interface AgentListResponse {
    session_id: string;
    agents: AgentListItem[];
    active_count: number;
    silent_count: number;
    conflict_count: number;
}

export interface AgentDetailResponse extends AgentListItem {
    public_positions: Record<string, unknown>;
    statement_count: number;
    contradiction_count: number;
    defining_line?: string;
    agenda?: string;
}

export interface SkillResponse {
    skill_md: string;
}

export interface VoicePodState {
    pod_id: string;
    agent_id: string | null;
    connected: boolean;
    livekit_room?: string | null;
    livekit_identity?: string | null;
}

export interface VoicePodsResponse {
    session_id: string;
    pods: VoicePodState[];
    updated_at: string;
}

export interface AgentActionResponse {
    agent_id: string;
    action_applied: string;
    applied_at: string;
    effect: string;
}

export interface SummonResponse {
    request_id: string;
    status: string;
    message: string;
    estimated_seconds: number;
}

export interface TranscriptStatement {
    statement_id: string;
    text: string;
    spoken_at: string;
    duration_seconds: number;
    was_interrupted: boolean;
    interrupted_by: string | null;
    triggered_conflict: string | null;
    triggered_decision: string | null;
}

export interface TranscriptResponse {
    agent_id: string;
    character_name: string;
    statements: TranscriptStatement[];
    total_statements: number;
    total_words: number;
}

export interface PodItem {
    agent_id: string;
    character_name: string;
    role_title: string;
    identity_color: string;
    status: string;
    transcript_snippet: string;
    conflict_with_name: string | null;
    waveform_active: boolean;
    last_audio_at: string | null;
}

export interface PodListResponse {
    session_id: string;
    filter_applied: string;
    pods: PodItem[];
    active_count: number;
    conflicted_count: number;
    thinking_count: number;
    silent_count: number;
}

export interface PodDetailResponse {
    agent_id: string;
    character_name: string;
    role_title: string;
    identity_color: string;
    voice_name: string;
    status: string;
    conflict_with: Array<{ agent_id: string; name: string }>;
    recent_transcript: string[];
    waveform_active: boolean;
    trust_score: number;
    statements_today: number;
    interrupted_count: number;
    interruption_count: number;
}

// ── Agent routes ───────────────────────────────────────────────────────────────

/** GET /api/sessions/{sid}/agents — List all agents with live status. */
export async function getAgents(
    sessionId: string,
    token: string,
    statusFilter?: string
): Promise<AgentListResponse> {
    const qs = statusFilter ? `?status_filter=${statusFilter}` : "";
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/agents${qs}`, {
        headers: authHeaders(token),
    });
    return handle<AgentListResponse>(res);
}

/** GET /api/sessions/{sid}/agents/{aid} — Single agent detail. */
export async function getAgent(
    sessionId: string,
    token: string,
    agentId: string
): Promise<AgentDetailResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/agents/${agentId}`,
        { headers: authHeaders(token) }
    );
    return handle<AgentDetailResponse>(res);
}

/** PATCH /api/sessions/{sid}/agents/{aid} — Dismiss / silence / address. */
export async function patchAgent(
    sessionId: string,
    token: string,
    agentId: string,
    action: "dismiss" | "silence" | "address",
    durationSeconds?: number
): Promise<AgentActionResponse> {
    const body: Record<string, unknown> = { action };
    if (durationSeconds) body.duration_seconds = durationSeconds;
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/agents/${agentId}`,
        { method: "PATCH", headers: authHeaders(token), body: JSON.stringify(body) }
    );
    return handle<AgentActionResponse>(res);
}

/** POST /api/sessions/{sid}/agents/summon — Summon new agent mid-session. */
export async function summonAgent(
    sessionId: string,
    token: string,
    roleDescription: string
): Promise<SummonResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/agents/summon`,
        {
            method: "POST",
            headers: authHeaders(token),
            body: JSON.stringify({ role_description: roleDescription }),
        }
    );
    return handle<SummonResponse>(res);
}

/** GET /api/sessions/{sid}/agents/{aid}/transcript — Agent statement history. */
export async function getAgentTranscript(
    sessionId: string,
    token: string,
    agentId: string,
    limit: number = 20,
    before?: string
): Promise<TranscriptResponse> {
    const params = new URLSearchParams({ limit: String(limit) });
    if (before) params.set("before", before);
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/agents/${agentId}/transcript?${params}`,
        { headers: authHeaders(token) }
    );
    return handle<TranscriptResponse>(res);
}

/** GET /api/sessions/{sid}/scenario/skill/{agent_id} */
export async function getAgentSkill(
    sessionId: string,
    token: string,
    agentId: string
): Promise<SkillResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/scenario/skill/${agentId}`,
        { headers: authHeaders(token) }
    );
    return handle<SkillResponse>(res);
}

// ── Pod routes ─────────────────────────────────────────────────────────────────

/** GET /api/sessions/{sid}/pods — All pod states. */
export async function getPods(
    sessionId: string,
    token: string,
    filter: "all" | "active" | "conflicted" = "all"
): Promise<PodListResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/pods?filter=${filter}`,
        { headers: authHeaders(token) }
    );
    return handle<PodListResponse>(res);
}

/** GET /api/sessions/{sid}/pods/{aid} — Single pod detail. */
export async function getPod(
    sessionId: string,
    token: string,
    agentId: string
): Promise<PodDetailResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/pods/${agentId}`,
        { headers: authHeaders(token) }
    );
    return handle<PodDetailResponse>(res);
}

// ── Voice types ────────────────────────────────────────────────────────────────

export interface VoiceTokenResponse {
    token: string;
    expires_at: string;
    ws_audio_url: string;
    transport: "websocket" | "livekit";
    sample_rate: number;
    channels: number;
    format: string;
    livekit_room?: string | null;
    livekit_identity?: string | null;
}

export interface AgentVoiceSession {
    agent_id: string;
    voice_active: boolean;
    voice_name: string;
    latency_ms: number;
    health: string;
}

export interface VoiceStatusResponse {
    chairman_mic: string;
    agent_sessions: AgentVoiceSession[];
    all_healthy: boolean;
    active_agent_id?: string | null;
}

export interface ChairmanMicResponse {
    chairman_mic: string;
    applied_at: string;
}

export interface ChairmanCommandResponse {
    command_id: string;
    text: string;
    target_agent_id: string | null;
    routed_to: string[];
    issued_at: string;
}

export interface ActiveVoiceAgentResponse {
    active_agent_id: string | null;
    updated_at: string;
}

// ── Voice routes ───────────────────────────────────────────────────────────────

/** POST /api/sessions/{sid}/voice/token — Get ephemeral token for chairman audio WS. */
export async function getVoiceToken(
    sessionId: string,
    token: string
): Promise<VoiceTokenResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/voice/token`,
        { method: "POST", headers: authHeaders(token) }
    );
    return handle<VoiceTokenResponse>(res);
}

/** GET /api/sessions/{sid}/voice/status — Check voice session health. */
export async function getVoiceStatus(
    sessionId: string,
    token: string
): Promise<VoiceStatusResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/voice/status`,
        { headers: authHeaders(token) }
    );
    return handle<VoiceStatusResponse>(res);
}

/** PATCH /api/sessions/{sid}/voice/chairman — Mute/unmute chairman mic. */
export async function patchChairmanMic(
    sessionId: string,
    token: string,
    muted: boolean
): Promise<ChairmanMicResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/voice/chairman`,
        { method: "PATCH", headers: authHeaders(token), body: JSON.stringify({ muted }) }
    );
    return handle<ChairmanMicResponse>(res);
}

/** PATCH /api/sessions/{sid}/voice/active-agent — Set active responder agent. */
export async function patchActiveVoiceAgent(
    sessionId: string,
    token: string,
    agentId: string | null
): Promise<ActiveVoiceAgentResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/voice/active-agent`,
        {
            method: "PATCH",
            headers: authHeaders(token),
            body: JSON.stringify({ agent_id: agentId }),
        }
    );
    return handle<ActiveVoiceAgentResponse>(res);
}

/** GET /api/sessions/{sid}/voice/pods — fixed pod mapping (4 + summon slot). */
export async function getVoicePods(
    sessionId: string,
    token: string
): Promise<VoicePodsResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/voice/pods`,
        { headers: authHeaders(token) }
    );
    return handle<VoicePodsResponse>(res);
}

/** PATCH /api/sessions/{sid}/voice/pods/{pod_id} — connect/disconnect pod voice. */
export async function patchVoicePod(
    sessionId: string,
    token: string,
    podId: string,
    connected: boolean
): Promise<VoicePodsResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/voice/pods/${podId}`,
        {
            method: "PATCH",
            headers: authHeaders(token),
            body: JSON.stringify({ connected }),
        }
    );
    return handle<VoicePodsResponse>(res);
}

// ── Chairman routes ────────────────────────────────────────────────────────────

/** POST /api/sessions/{sid}/chairman/command — Send text directive to agent(s). */
export async function sendChairmanCommand(
    sessionId: string,
    token: string,
    text: string,
    targetAgentId?: string,
    commandType: string = "question"
): Promise<ChairmanCommandResponse> {
    const res = await fetch(
        `${API_BASE}/api/sessions/${sessionId}/chairman/command`,
        {
            method: "POST",
            headers: authHeaders(token),
            body: JSON.stringify({
                text,
                target_agent_id: targetAgentId ?? null,
                command_type: commandType,
            }),
        }
    );
    return handle<ChairmanCommandResponse>(res);
}

// ── Crisis Board routes ────────────────────────────────────────────────────────

/** GET /api/sessions/{sid}/board — Full crisis board state. */
export async function getBoard(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/board`, { headers: authHeaders(token) });
    return handle(res);
}

/** GET /api/sessions/{sid}/board/decisions */
export async function getDecisions(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/board/decisions`, { headers: authHeaders(token) });
    return handle(res);
}

/** POST /api/sessions/{sid}/board/decisions — Pin a decision. */
export async function createDecision(sessionId: string, token: string, text: string, lock = false) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/board/decisions`, {
        method: "POST", headers: authHeaders(token), body: JSON.stringify({ text, lock }),
    });
    return handle(res);
}

/** PATCH /api/sessions/{sid}/board/decisions/{did} — Lock/unlock. */
export async function lockDecision(sessionId: string, token: string, decisionId: string, locked: boolean) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/board/decisions/${decisionId}`, {
        method: "PATCH", headers: authHeaders(token), body: JSON.stringify({ locked }),
    });
    return handle(res);
}

/** GET /api/sessions/{sid}/board/conflicts */
export async function getConflicts(sessionId: string, token: string, status = "open") {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/board/conflicts?status=${status}`, { headers: authHeaders(token) });
    return handle(res);
}

/** PATCH /api/sessions/{sid}/board/conflicts/{cid} — Resolve. */
export async function resolveConflict(sessionId: string, token: string, conflictId: string, resolution: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/board/conflicts/${conflictId}`, {
        method: "PATCH", headers: authHeaders(token), body: JSON.stringify({ resolution }),
    });
    return handle(res);
}

/** GET /api/sessions/{sid}/board/intel */
export async function getBoardIntel(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/board/intel`, { headers: authHeaders(token) });
    return handle(res);
}

/** POST /api/sessions/{sid}/board/intel — Chairman injects intel. */
export async function injectIntel(sessionId: string, token: string, text: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/board/intel`, {
        method: "POST", headers: authHeaders(token), body: JSON.stringify({ text, broadcast: true }),
    });
    return handle(res);
}

/** GET /api/sessions/{sid}/board/timeline */
export async function getBoardTimeline(sessionId: string, token: string, at: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/board/timeline?at=${at}`, { headers: authHeaders(token) });
    return handle(res);
}

// ── Crisis Feed routes ─────────────────────────────────────────────────────────

/** GET /api/sessions/{sid}/feed — All feed items. */
export async function getFeed(sessionId: string, token: string, limit = 30) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/feed?limit=${limit}`, { headers: authHeaders(token) });
    return handle(res);
}

/** GET /api/sessions/{sid}/feed/world — World agent events. */
export async function getFeedWorld(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/feed/world`, { headers: authHeaders(token) });
    return handle(res);
}

// ── Room Intelligence routes ───────────────────────────────────────────────────

/** GET /api/sessions/{sid}/intel — Observer insights. */
export async function getIntel(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/intel`, { headers: authHeaders(token) });
    return handle(res);
}

/** GET /api/sessions/{sid}/intel/trust — All trust scores. */
export async function getTrustScores(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/intel/trust`, { headers: authHeaders(token) });
    return handle(res);
}

/** GET /api/sessions/{sid}/intel/trust/{aid}/history */
export async function getTrustHistory(sessionId: string, token: string, agentId: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/intel/trust/${agentId}/history`, { headers: authHeaders(token) });
    return handle(res);
}

// ── Crisis Posture routes ──────────────────────────────────────────────────────

/** GET /api/sessions/{sid}/posture */
export async function getPosture(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/posture`, { headers: authHeaders(token) });
    return handle(res);
}

/** GET /api/sessions/{sid}/posture/history */
export async function getPostureHistory(sessionId: string, token: string, axis = "public_exposure") {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/posture/history?axis=${axis}`, { headers: authHeaders(token) });
    return handle(res);
}

// ── Resolution Score routes ────────────────────────────────────────────────────

/** GET /api/sessions/{sid}/score */
export async function getScore(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/score`, { headers: authHeaders(token) });
    return handle(res);
}

/** GET /api/sessions/{sid}/score/history */
export async function getScoreHistory(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/score/history`, { headers: authHeaders(token) });
    return handle(res);
}

// ── World Agent routes ─────────────────────────────────────────────────────────

/** GET /api/sessions/{sid}/world — World agent status. */
export async function getWorld(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/world`, { headers: authHeaders(token) });
    return handle(res);
}

/** POST /api/sessions/{sid}/world/escalate — Chairman triggers escalation. */
export async function triggerEscalation(sessionId: string, token: string, eventText: string, scoreImpact = -8) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/world/escalate`, {
        method: "POST", headers: authHeaders(token),
        body: JSON.stringify({ event_text: eventText, score_impact: scoreImpact }),
    });
    return handle(res);
}

// ── Resolution routes ──────────────────────────────────────────────────────────

/** POST /api/sessions/{sid}/resolution — Call resolution. */
export async function callResolution(sessionId: string, token: string, finalDecision: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/resolution`, {
        method: "POST", headers: authHeaders(token),
        body: JSON.stringify({ final_decision: finalDecision }),
    });
    return handle(res);
}

/** GET /api/sessions/{sid}/report — After-action report. */
export async function getReport(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/report`, { headers: authHeaders(token) });
    return handle(res);
}

// ── Chairman extras ────────────────────────────────────────────────────────────

/** POST /api/sessions/{sid}/chairman/vote — Force vote. */
export async function callVote(sessionId: string, token: string, question: string, timeLimitSeconds = 120) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/chairman/vote`, {
        method: "POST", headers: authHeaders(token),
        body: JSON.stringify({ question, time_limit_seconds: timeLimitSeconds }),
    });
    return handle(res);
}

/** GET /api/sessions/{sid}/chairman/commands — Command history. */
export async function getCommandHistory(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/api/sessions/${sessionId}/chairman/commands`, { headers: authHeaders(token) });
    return handle(res);
}
