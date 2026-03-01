/**
 * WAR ROOM — useChairmanMic Hook
 * Captures chairman microphone audio and streams it to the backend
 * via the dedicated audio WebSocket (/ws/{session_id}/audio).
 *
 * Audio format: PCM 16-bit, 16kHz, mono
 * Sent as binary frames on the WebSocket.
 */

"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const SAMPLE_RATE = 16000;
const BUFFER_SIZE = 4096;

interface UseChairmanMicOptions {
    sessionId: string | null;
    token: string | null;
    targetAgentId?: string | null;
}

interface UseChairmanMicReturn {
    /** Whether the mic is currently capturing audio */
    isActive: boolean;
    /** Whether the audio WebSocket is connected */
    isConnected: boolean;
    /** Start capturing and streaming mic audio */
    startMic: () => Promise<void>;
    /** Stop capturing and close the stream */
    stopMic: () => void;
    /** Set which agent receives the audio */
    setTarget: (agentId: string | null) => void;
    /** Error message if mic failed */
    error: string | null;
}

/**
 * Hook that captures chairman's microphone audio and streams it
 * to the backend audio WebSocket for routing to agents.
 */
export function useChairmanMic({
    sessionId,
    token,
    targetAgentId,
}: UseChairmanMicOptions): UseChairmanMicReturn {
    const [isActive, setIsActive] = useState(false);
    const [isConnected, setIsConnected] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const wsRef = useRef<WebSocket | null>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const contextRef = useRef<AudioContext | null>(null);
    const processorRef = useRef<ScriptProcessorNode | null>(null);
    const muteGainRef = useRef<GainNode | null>(null);

    // Build WS URL
    const getWsUrl = useCallback(() => {
        const base = process.env.NEXT_PUBLIC_WS_URL
            ?? process.env.NEXT_PUBLIC_API_URL?.replace(/^http/, "ws")
            ?? "ws://localhost:8000";
        return `${base.replace(/\/$/, "")}/ws/${sessionId}/audio`;
    }, [sessionId]);

    // Connect the audio WebSocket
    const connectAudioWs = useCallback(() => {
        if (!sessionId) return null;

        // Close any existing WebSocket to prevent cycling
        if (wsRef.current) {
            if (wsRef.current.readyState === WebSocket.OPEN ||
                wsRef.current.readyState === WebSocket.CONNECTING) {
                wsRef.current.close();
            }
            wsRef.current = null;
        }

        const url = getWsUrl();
        const ws = new WebSocket(url);
        ws.binaryType = "arraybuffer";

        ws.onopen = () => {
            setIsConnected(true);
            setError(null);
            console.log("[MIC] Audio WebSocket connected");

            // Set target agent if specified
            if (targetAgentId) {
                ws.send(JSON.stringify({
                    type: "set_target",
                    agent_id: targetAgentId,
                }));
            }
        };

        ws.onclose = () => {
            setIsConnected(false);
            // Only log if this is still the active WS (prevents stale close logs)
            if (wsRef.current === ws) {
                console.log("[MIC] Audio WebSocket disconnected");
            }
        };

        ws.onerror = (e) => {
            console.error("[MIC] Audio WebSocket error:", e);
            setError("Audio connection failed");
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === "vad_speech_start") {
                    console.log("[MIC] VAD: speech started");
                } else if (data.type === "vad_speech_end") {
                    console.log("[MIC] VAD: speech ended");
                } else if (data.type === "transcript") {
                    console.log("[MIC] Transcript:", data.text);
                } else if (data.type === "routed_to") {
                    console.log("[MIC] Audio routed to:", data.agent_id);
                }
            } catch {
                // Binary response or non-JSON
            }
        };

        return ws;
    }, [sessionId, getWsUrl, targetAgentId]);

    // Convert Float32 audio samples to Int16 PCM bytes
    const float32ToInt16 = (buffer: Float32Array): ArrayBuffer => {
        const int16 = new Int16Array(buffer.length);
        for (let i = 0; i < buffer.length; i++) {
            const s = Math.max(-1, Math.min(1, buffer[i]));
            int16[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        return int16.buffer;
    };

    // Downsample audio from source sample rate to 16kHz
    const downsample = (
        buffer: Float32Array,
        inputRate: number,
        outputRate: number
    ): Float32Array => {
        if (inputRate === outputRate) return buffer;
        const ratio = inputRate / outputRate;
        const newLength = Math.round(buffer.length / ratio);
        const result = new Float32Array(newLength);
        for (let i = 0; i < newLength; i++) {
            const idx = Math.round(i * ratio);
            result[i] = buffer[idx] ?? 0;
        }
        return result;
    };

    /** Start capturing and streaming mic audio */
    const startMic = useCallback(async () => {
        if (isActive) return;
        setError(null);

        try {
            // Request microphone access
            const stream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: SAMPLE_RATE,
                    channelCount: 1,
                    echoCancellation: true,
                    noiseSuppression: true,
                    autoGainControl: true,
                },
            });
            streamRef.current = stream;

            // Connect audio WebSocket
            const ws = connectAudioWs();
            if (!ws) {
                stream.getTracks().forEach(t => t.stop());
                setError("No session to connect to");
                return;
            }
            wsRef.current = ws;

            // Set up AudioContext for processing
            const audioCtx = new AudioContext({ sampleRate: SAMPLE_RATE });
            contextRef.current = audioCtx;

            const source = audioCtx.createMediaStreamSource(stream);
            const processor = audioCtx.createScriptProcessor(BUFFER_SIZE, 1, 1);
            processorRef.current = processor;
            const muteGain = audioCtx.createGain();
            muteGain.gain.value = 0;
            muteGainRef.current = muteGain;

            processor.onaudioprocess = (e) => {
                if (ws.readyState !== WebSocket.OPEN) return;

                const input = e.inputBuffer.getChannelData(0);

                // Downsample if browser sample rate differs
                const downsampled = downsample(
                    input,
                    audioCtx.sampleRate,
                    SAMPLE_RATE
                );

                // Convert to PCM16 bytes and send
                const pcmBytes = float32ToInt16(downsampled);
                ws.send(pcmBytes);
            };

            // Important: do not route mic audio to speakers.
            // Using a zero-gain node keeps processing alive without feedback.
            source.connect(processor);
            processor.connect(muteGain);
            muteGain.connect(audioCtx.destination);

            setIsActive(true);
            console.log("[MIC] Capturing started");
        } catch (err) {
            const msg = err instanceof Error ? err.message : "Mic access denied";
            setError(msg);
            console.error("[MIC] Start failed:", msg);
        }
    }, [isActive, connectAudioWs]);

    /** Stop capturing and close everything */
    const stopMic = useCallback(() => {
        // Stop audio processing
        if (processorRef.current) {
            processorRef.current.disconnect();
            processorRef.current = null;
        }
        if (muteGainRef.current) {
            muteGainRef.current.disconnect();
            muteGainRef.current = null;
        }

        // Close AudioContext
        if (contextRef.current?.state !== "closed") {
            contextRef.current?.close();
        }
        contextRef.current = null;

        // Stop media stream tracks
        streamRef.current?.getTracks().forEach(t => t.stop());
        streamRef.current = null;

        // Close audio WebSocket
        if (wsRef.current) {
            wsRef.current.close();
            wsRef.current = null;
        }

        setIsActive(false);
        setIsConnected(false);
        console.log("[MIC] Stopped");
    }, []);

    /** Update target agent on the audio WebSocket */
    const setTarget = useCallback((agentId: string | null) => {
        if (wsRef.current?.readyState === WebSocket.OPEN) {
            if (agentId) {
                wsRef.current.send(JSON.stringify({
                    type: "set_target",
                    agent_id: agentId,
                }));
            } else {
                wsRef.current.send(JSON.stringify({ type: "clear_target" }));
            }
        }
    }, []);

    // Clean up on unmount
    useEffect(() => {
        return () => {
            stopMic();
        };
    }, [stopMic]);

    // Update target when prop changes
    useEffect(() => {
        if (targetAgentId !== undefined) {
            setTarget(targetAgentId ?? null);
        }
    }, [targetAgentId, setTarget]);

    return {
        isActive,
        isConnected,
        startMic,
        stopMic,
        setTarget,
        error,
    };
}
