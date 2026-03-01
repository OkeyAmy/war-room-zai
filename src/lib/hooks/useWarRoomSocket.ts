"use client";
/**
 * WAR ROOM — WebSocket + Voice Hook
 *
 * Connects to the backend gateway WebSocket at ws://host/ws/{session_id}
 * and dispatches events to update the war room state.
 *
 * Audio pipeline (per voice.md §3):
 *   WS event.payload.audio_b64  ← raw PCM 24kHz 16-bit mono (base64-encoded)
 *   → atob() → Uint8Array → Int16Array → Float32Array
 *   → AudioContext.createBuffer(1, samples, 24000)
 *   → AudioBufferSourceNode.start(scheduledTime)
 *   → 🔊 speakers
 */

import { useEffect, useRef, useCallback, useState } from "react";

const WS_BASE =
    process.env.NEXT_PUBLIC_WS_URL?.replace(/\/$/, "") ??
    process.env.NEXT_PUBLIC_API_URL?.replace(/^http/, "ws")?.replace(/\/$/, "") ??
    "ws://localhost:8000";

export interface WSEvent {
    event_type: string;
    event_id?: string;
    timestamp?: string;
    payload: Record<string, unknown>;
}

export type WSEventHandler = (event: WSEvent) => void;

interface UseWarRoomSocketOptions {
    sessionId: string | null;
    token: string | null;
    onEvent: WSEventHandler;
    onAudioChunk?: (agentId: string, audioBase64: string) => void;
}

export function useWarRoomSocket({
    sessionId,
    token,
    onEvent,
    onAudioChunk,
}: UseWarRoomSocketOptions) {
    const wsRef = useRef<WebSocket | null>(null);
    const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const manualCloseRef = useRef(false);
    const connectingRef = useRef(false);
    const [connected, setConnected] = useState(false);
    const [lastEventAt, setLastEventAt] = useState<number>(0);
    const onEventRef = useRef(onEvent);
    const onAudioRef = useRef(onAudioChunk);

    // Keep refs fresh
    onEventRef.current = onEvent;
    onAudioRef.current = onAudioChunk;

    const connect = useCallback(() => {
        if (!sessionId || !token) return;
        if (connectingRef.current) return;
        if (
            wsRef.current?.readyState === WebSocket.OPEN ||
            wsRef.current?.readyState === WebSocket.CONNECTING
        ) {
            return;
        }
        if (reconnectRef.current) {
            clearTimeout(reconnectRef.current);
            reconnectRef.current = null;
        }
        manualCloseRef.current = false;
        connectingRef.current = true;

        const url = `${WS_BASE}/ws/${sessionId}`;
        console.log(`[WAR ROOM WS] Connecting to ${url}...`);

        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
            if (wsRef.current !== ws) {
                ws.close();
                return;
            }
            connectingRef.current = false;
            console.log("[WAR ROOM WS] Connected ✅");
            setConnected(true);

            // Send auth token as first message
            ws.send(
                JSON.stringify({ type: "auth", chairman_token: token })
            );
        };

        ws.onmessage = (msg) => {
            if (wsRef.current !== ws) return;
            try {
                const data = JSON.parse(msg.data);
                setLastEventAt(Date.now());

                // ── AUDIO CHUNK: play agent voice ─────────────────────
                // Backend sends audio_b64 (per voice.md publish_event spec)
                // Check both field names for compatibility
                if (data.event_type === "agent_audio_chunk") {
                    const audioB64 =
                        (data.payload?.audio_b64 as string) ||
                        (data.payload?.audio_base64 as string);
                    if (audioB64) {
                        onAudioRef.current?.(
                            data.payload.agent_id as string,
                            audioB64
                        );
                        return; // Don't also process in event handler
                    }
                }

                // ── ALL OTHER EVENTS: update UI state ─────────────────
                onEventRef.current(data as WSEvent);
            } catch {
                // Non-JSON message — ignore
            }
        };

        ws.onclose = (e) => {
            if (wsRef.current === ws) {
                wsRef.current = null;
            }
            connectingRef.current = false;
            console.warn(
                `[WAR ROOM WS] Disconnected (code=${e.code}). Reconnecting in 3s...`
            );
            setConnected(false);
            if (!manualCloseRef.current) {
                reconnectRef.current = setTimeout(connect, 3000);
            }
        };

        ws.onerror = (err) => {
            if (wsRef.current !== ws) return;
            console.error("[WAR ROOM WS] Error:", err);
            ws.close();
        };
    }, [sessionId, token]);

    // Connect on mount, cleanup on unmount
    useEffect(() => {
        connect();
        return () => {
            if (reconnectRef.current) clearTimeout(reconnectRef.current);
            reconnectRef.current = null;
            manualCloseRef.current = true;
            connectingRef.current = false;
            if (
                wsRef.current?.readyState === WebSocket.OPEN ||
                wsRef.current?.readyState === WebSocket.CONNECTING
            ) {
                wsRef.current.close();
            }
            wsRef.current = null;
        };
    }, [connect]);

    // Ping every 30s to keep alive
    useEffect(() => {
        if (!connected) return;
        const ping = setInterval(() => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send(JSON.stringify({ type: "ping" }));
            }
        }, 30_000);
        return () => clearInterval(ping);
    }, [connected]);

    // Send a message to the backend (e.g., chairman audio / commands)
    const sendMessage = useCallback(
        (data: Record<string, unknown>) => {
            if (wsRef.current?.readyState === WebSocket.OPEN) {
                wsRef.current.send(JSON.stringify(data));
            }
        },
        []
    );

    return { connected, sendMessage, lastEventAt };
}

// ── Audio Playback Hook ────────────────────────────────────────────────────────

/**
 * Per voice.md §3.2 — The AudioManager.
 *
 * Manages ONE AudioContext for the page. Plays base64-encoded PCM16 audio
 * chunks from Gemini Live (24kHz, 16-bit, mono).
 *
 * KEY DESIGN — GLOBAL ACTIVE-SPEAKER GATE (voice overlap fix):
 *   The audio player tracks which agent currently "owns" the audio output.
 *   Any chunk arriving from a different agent is immediately discarded.
 *   This prevents voices from mixing even if backend TurnManager drops a
 *   turn AFTER the first audio chunk was already sent over the WebSocket.
 *
 *   Gate lifecycle:
 *     - playChunk(agentX) when gate free → agentX becomes activeSpeaker.
 *     - playChunk(agentY) while agentX speaks → chunk silently dropped.
 *     - Last buffer for agentX ends → gate auto-clears (activeSpeaker=null).
 *     - stopAgent(agentX) / stopAll() → gate clears immediately.
 *
 * MUST call ensureContext() from a user gesture before audio plays.
 */
export function useAudioPlayer() {
    const ctxRef = useRef<AudioContext | null>(null);

    // ── GLOBAL GATE ────────────────────────────────────────────────────
    // Only the agent in activeSpeakerRef may play audio output right now.
    const activeSpeakerRef = useRef<string | null>(null);

    // Per-agent scheduled end times (voice.md §3.2 nextPlayTime)
    const nextStartMap = useRef<Record<string, number>>({});
    // Per-agent active source nodes for interrupt support (voice.md §3.6)
    const activeSourcesMap = useRef<Record<string, AudioBufferSourceNode[]>>({});

    /** Initialize AudioContext — MUST be called from a user gesture. */
    const ensureContext = useCallback((): AudioContext => {
        if (!ctxRef.current || ctxRef.current.state === "closed") {
            ctxRef.current = new AudioContext({ sampleRate: 24000 });
        }
        // iOS Safari suspends AudioContext — resume on every call
        if (ctxRef.current.state === "suspended") {
            ctxRef.current.resume().catch(() => { });
        }
        return ctxRef.current;
    }, []);

    /**
     * Play a PCM16 audio chunk for a specific agent.
     *
     * GATE: if another agent currently owns audio output, this chunk is
     * silently dropped — no scheduling, no playback, no mixing.
     */
    const playChunk = useCallback(
        (agentId: string, audioBase64: string) => {
            // ── GATE CHECK ───────────────────────────────────────────────
            const currentSpeaker = activeSpeakerRef.current;
            if (currentSpeaker !== null && currentSpeaker !== agentId) {
                // A different agent owns the output — drop this chunk
                return;
            }
            if (currentSpeaker === null) {
                // First chunk from this agent — claim the gate
                activeSpeakerRef.current = agentId;
            }
            // ─────────────────────────────────────────────────────────────

            try {
                const ctx = ensureContext();

                // Base64 → Uint8Array
                const raw = atob(audioBase64);
                const bytes = new Uint8Array(raw.length);
                for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);

                // Uint8Array → PCM16 signed integers
                const int16 = new Int16Array(bytes.buffer);

                // PCM16 → Float32 (-1.0 to 1.0)
                const float32 = new Float32Array(int16.length);
                for (let i = 0; i < int16.length; i++) float32[i] = int16[i] / 32768.0;

                // AudioBuffer at 24kHz
                const buffer = ctx.createBuffer(1, float32.length, 24000);
                buffer.copyToChannel(float32, 0);

                // Source node
                const source = ctx.createBufferSource();
                source.buffer = buffer;
                source.connect(ctx.destination);

                // Schedule seamlessly (voice.md §3.2)
                const now = ctx.currentTime;
                const lastEnd = nextStartMap.current[agentId] ?? now;
                const startAt = Math.max(now, lastEnd);
                source.start(startAt);
                nextStartMap.current[agentId] = startAt + buffer.duration;

                // Track for interrupt support (voice.md §3.6)
                if (!activeSourcesMap.current[agentId]) {
                    activeSourcesMap.current[agentId] = [];
                }
                activeSourcesMap.current[agentId].push(source);

                source.onended = () => {
                    activeSourcesMap.current[agentId] =
                        activeSourcesMap.current[agentId]?.filter(s => s !== source) ?? [];
                    // Last buffer for active speaker done → release gate
                    if (
                        activeSpeakerRef.current === agentId &&
                        (activeSourcesMap.current[agentId]?.length ?? 0) === 0
                    ) {
                        activeSpeakerRef.current = null;
                    }
                };

            } catch (err) {
                console.warn("[WAR ROOM AUDIO] Failed to play chunk:", err);
            }
        },
        [ensureContext]
    );

    /**
     * Stop all pending audio for an agent and clear the gate.
     * Call on agent_speaking_end or agent_interrupted events.
     */
    const stopAgent = useCallback((agentId: string) => {
        const sources = activeSourcesMap.current[agentId] ?? [];
        sources.forEach(src => { try { src.stop(); } catch { /* ok */ } });
        activeSourcesMap.current[agentId] = [];
        nextStartMap.current[agentId] = ctxRef.current?.currentTime ?? 0;
        if (activeSpeakerRef.current === agentId) {
            activeSpeakerRef.current = null;
        }
    }, []);

    /**
     * Stop ALL agent audio immediately and reset the gate.
     * Call on chairman interrupt or session end.
     */
    const stopAll = useCallback(() => {
        Object.keys(activeSourcesMap.current).forEach(agentId => {
            const sources = activeSourcesMap.current[agentId] ?? [];
            sources.forEach(src => { try { src.stop(); } catch { /* ok */ } });
            activeSourcesMap.current[agentId] = [];
            nextStartMap.current[agentId] = ctxRef.current?.currentTime ?? 0;
        });
        activeSpeakerRef.current = null;
    }, []);

    // Cleanup on unmount
    useEffect(() => {
        return () => { ctxRef.current?.close(); };
    }, []);

    return { playChunk, stopAgent, stopAll, ensureContext };
}
