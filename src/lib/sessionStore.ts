/**
 * WAR ROOM — Session Store
 *
 * Persists session credentials so the war-room page can read them after
 * navigation. Uses cookies (not sessionStorage) so they survive:
 *   - Hard refreshes
 *   - Production deployments (SSR-readable on the server side)
 *   - Switching between dev and production
 *
 * The cookie is scoped to the current path and expires in 2 hours.
 */

const COOKIE_NAME = "wr_session";
const COOKIE_MAX_AGE = 60 * 60 * 2; // 2 hours

export interface SessionCredentials {
    sessionId: string;
    token: string;
    chairmanName: string;
}

function serialize(data: SessionCredentials): string {
    return encodeURIComponent(JSON.stringify(data));
}

function deserialize(raw: string): SessionCredentials | null {
    try {
        return JSON.parse(decodeURIComponent(raw)) as SessionCredentials;
    } catch {
        return null;
    }
}

/** Save session credentials to a cookie. */
export function saveSession(creds: SessionCredentials): void {
    if (typeof document === "undefined") return;
    const value = serialize(creds);
    document.cookie = `${COOKIE_NAME}=${value}; path=/; max-age=${COOKIE_MAX_AGE}; SameSite=Strict`;
}

/** Load session credentials from the cookie. Returns null if not found. */
export function loadSession(): SessionCredentials | null {
    if (typeof document === "undefined") return null;
    const match = document.cookie
        .split("; ")
        .find((c) => c.startsWith(`${COOKIE_NAME}=`));
    if (!match) return null;
    const raw = match.slice(COOKIE_NAME.length + 1);
    return deserialize(raw);
}

/** Clear the session cookie (e.g., after DELETE /api/sessions). */
export function clearSession(): void {
    if (typeof document === "undefined") return;
    document.cookie = `${COOKIE_NAME}=; path=/; max-age=0; SameSite=Strict`;
}

/** Returns true if a valid session cookie exists. Used for route protection. */
export function hasSession(): boolean {
    return loadSession() !== null;
}
