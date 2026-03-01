"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { createSession, pollUntilReady, type AssemblyLogEntry } from "@/lib/api";
import { saveSession } from "@/lib/sessionStore";

// ─── Assembly Loading Screen ────────────────────────────────────────────────

function AssemblingScreen({ log }: { log: AssemblyLogEntry[] }) {
  // Always show 4 phases; fill from real log, animate the rest
  const phases = [
    "Initializing scenario analysis:",
    "Extracting crisis domain:",
    "Generating tactical cast:",
    "Formulating opening brief:",
    "Establishing secure connection:",
  ];

  return (
    <div className="war-room-app flex items-center justify-center bg-[#080A0E]">
      <div className="text-center space-y-12 max-w-2xl px-6">
        <div className="relative">
          <div className="absolute inset-0 blur-3xl bg-blue-500/10 animate-pulse rounded-full" />
          <h2 className="text-5xl font-black tracking-tight cinematic-glow mb-2 uppercase italic">
            Assembling your crisis team...
          </h2>
          <p className="text-blue-500/60 font-mono text-xs tracking-[0.3em] uppercase">
            Initializing Secure Tactical Environment
          </p>
        </div>

        <div className="space-y-4 text-left font-mono text-sm border-l-2 border-blue-500/30 pl-8 py-6 bg-blue-500/[0.02]">
          {phases.map((phase, i) => {
            const entry = log.find((l) => l.line === phase);
            const isVisible = log.length > i || entry;
            const isComplete = entry?.status === "complete";
            const value = entry?.value ?? "...";

            return (
              <p
                key={phase}
                className={`item-new opacity-0`}
                style={{ animationDelay: `${i * 0.5}s` }}
              >
                <span className="text-blue-400">[INTEL]</span>{" "}
                {phase}{" "}
                {isVisible && (
                  <span className={isComplete ? "text-green-400" : "text-yellow-400 animate-pulse"}>
                    {value}
                  </span>
                )}
              </p>
            );
          })}
        </div>

        <div className="flex justify-center space-x-3">
          {[0, 150, 300].map((delay) => (
            <div
              key={delay}
              className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce"
              style={{ animationDelay: `${delay}ms` }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Landing Page ───────────────────────────────────────────────────────────

export default function LandingPage() {
  const [crisisDescription, setCrisisDescription] = useState("");
  const [chairmanName, setChairmanName] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(30);
  const [showOptions, setShowOptions] = useState(false);

  const [isAssembling, setIsAssembling] = useState(false);
  const [assemblyLog, setAssemblyLog] = useState<AssemblyLogEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const router = useRouter();

  // Reveal chairman options once crisis input is substantial
  useEffect(() => {
    setShowOptions(crisisDescription.trim().length >= 10);
  }, [crisisDescription]);

  const handleStart = async (e: React.FormEvent) => {
    e.preventDefault();
    if (crisisDescription.trim().length < 10) return;

    setError(null);
    setIsAssembling(true);
    setAssemblyLog([]);

    try {
      // 1. Create session → get session_id + chairman_token immediately
      const session = await createSession(
        crisisDescription.trim(),
        chairmanName.trim() || "DIRECTOR",
        durationMinutes
      );

      // 2. Persist to cookie for the war-room page
      saveSession({
        sessionId: session.session_id,
        token: session.chairman_token,
        chairmanName: chairmanName.trim() || "DIRECTOR",
      });

      // 3. Poll until scenario_ready, updating the log live
      await pollUntilReady(
        session.session_id,
        session.chairman_token,
        (log) => setAssemblyLog([...log]),
        1500,
        90_000
      );

      // 4. Navigate to the war room (protected route)
      router.push(`/war-room/${session.session_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
      setIsAssembling(false);
    }
  };

  if (isAssembling) {
    return <AssemblingScreen log={assemblyLog} />;
  }

  return (
    <div className="war-room-app flex flex-col items-center justify-center p-6 bg-[#080A0E]">
      <div className="max-w-2xl w-full space-y-8 text-center">
        <p className="text-sm font-mono tracking-[0.25em] uppercase text-blue-500/60">
          What&apos;s the crisis?
        </p>

        <form onSubmit={handleStart} className="w-full space-y-6">
          {/* Crisis description */}
          <div className="relative group">
            <div className="absolute -inset-1 bg-gradient-to-b from-blue-600/20 to-transparent rounded-lg blur-lg opacity-25 group-focus-within:opacity-100 transition duration-1000" />
            <textarea
              autoFocus
              value={crisisDescription}
              onChange={(e) => setCrisisDescription(e.target.value)}
              placeholder="Describe your crisis. Anything. Real or fictional."
              className="relative w-full bg-[#0D1117]/80 backdrop-blur-sm border border-blue-900/30 rounded-lg p-8 text-2xl font-mono text-blue-100 placeholder:text-blue-900 focus:outline-none focus:border-blue-500/50 min-h-[200px] resize-none transition-all shadow-2xl"
            />
            <div className="absolute bottom-4 right-4 text-[10px] font-mono text-blue-900 uppercase tracking-widest pointer-events-none">
              Terminal Input Active
            </div>
          </div>

          {/* Chairman options — revealed once enough text is entered */}
          <div
            className="overflow-hidden transition-all duration-500"
            style={{ maxHeight: showOptions ? "200px" : "0px", opacity: showOptions ? 1 : 0 }}
          >
            <div className="grid grid-cols-2 gap-4 pt-2">
              {/* Chairman name */}
              <div className="text-left">
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-blue-500/60 mb-2">
                  Chairman Callsign
                </label>
                <input
                  type="text"
                  value={chairmanName}
                  onChange={(e) => setChairmanName(e.target.value)}
                  placeholder="DIRECTOR"
                  maxLength={20}
                  className="w-full bg-[#0D1117]/80 border border-blue-900/30 rounded px-4 py-3 text-sm font-mono text-blue-100 placeholder:text-blue-900/50 focus:outline-none focus:border-blue-500/40 transition-all"
                />
              </div>

              {/* Duration */}
              <div className="text-left">
                <label className="block text-[10px] font-mono tracking-[0.2em] uppercase text-blue-500/60 mb-2">
                  Session Duration — {durationMinutes} min
                </label>
                <input
                  type="range"
                  min={5}
                  max={120}
                  step={5}
                  value={durationMinutes}
                  onChange={(e) => setDurationMinutes(Number(e.target.value))}
                  className="w-full accent-blue-500 cursor-pointer mt-3"
                />
                <div className="flex justify-between text-[9px] font-mono text-blue-900 mt-1">
                  <span>5m</span>
                  <span>2h</span>
                </div>
              </div>
            </div>
          </div>

          {/* Error */}
          {error && (
            <p className="text-xs font-mono text-red-400 bg-red-900/10 border border-red-900/30 px-4 py-3 rounded text-left">
              ⚠ {error}
            </p>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={crisisDescription.trim().length < 10}
            className="group relative px-12 py-5 bg-blue-600 hover:bg-blue-500 disabled:opacity-20 disabled:cursor-not-allowed text-white font-black uppercase tracking-[0.3em] italic rounded transition-all transform hover:scale-[1.02] active:scale-[0.98]"
          >
            <span className="relative z-10">Assemble Team</span>
            <div className="absolute inset-0 bg-blue-400 blur-xl opacity-0 group-hover:opacity-20 transition-opacity" />
          </button>
        </form>
      </div>
    </div>
  );
}
