# Frontend Mock/Stimulated Data Analysis

## Overview

This document identifies all frontend components that use simulated/mocked data instead of fetching from the backend, and discusses the integration status for each.

---

## 1. ChairmanCommandBar.tsx

### Location
`src/components/war-room/ChairmanCommandBar.tsx`

### Mock Data Found

**Lines 39-48** - Mock transcript phrases when mic is active:
```typescript
const mockPhrases = [
  "Status report on hospital servers.",
  "Authorize perimeter team deployment.",
  "Lock decision 4 immediately.",
  "Brief all agents on legal risk.",
  "What is the current resolution score?"
];
```

**Line 119** - Fallback agent list:
```typescript
...(agents ? agents.map(a => a.name.toUpperCase()) : ["ATLAS", "NOVA", "CIPHER", "FELIX"])
```

### Backend Integration Status
| Endpoint | Status |
|----------|--------|
| `/api/sessions/{session_id}/agents` | ✅ INTEGRATED |

The backend provides the agent list. The frontend correctly falls back to mock data only when no agents prop is provided.

---

## 2. RightPanels.tsx

### Location
`src/components/war-room/RightPanels.tsx`

### Mock Data Found

**Lines 270-274** - Mock axes for Crisis Posture:
```typescript
const displayAxes: PostureAxis[] = axes.length > 0 ? axes : [
  { label: "PUBLIC EXPOSURE", value: level * 20 - 10, status: "CRIT" | "HIGH" | "CONT", subMetric: "Viral velocity: RISING", trend: "UP" },
  { label: "LEGAL EXPOSURE", value: level * 15, status: "CRIT" | "ELEV" | "CONT", subMetric: "Liability scan active", trend: "STABLE" },
  { label: "INTERNAL STABILITY", value: 100 - level * 10, status: "HIGH" | "CONT", subMetric: "Team alignment nominal", trend: "DOWN" },
];
```

### Backend Integration Status
| Endpoint | Status |
|----------|--------|
| `/api/sessions/{session_id}/posture` | ✅ INTEGRATED |

The backend provides posture data. The mock is only used as fallback when no axes prop is passed.

---

## 3. [session_id]/page.tsx (Main War Room Page)

### Location
`src/app/war-room/[session_id]/page.tsx`

### Mock Data Found (Extensive)

The page contains extensive simulation seed data as **fallback only** (see comment on line 52: "FALLBACK — only used when API fails"):

| Mock Data Variable | Lines | Description |
|-------------------|-------|-------------|
| `SIMULATION_AGENTS` | 54-61 | 6 agents (ATLAS, NOVA, CIPHER, FELIX, ORACLE, VANGUARD) |
| `INITIAL_DECISIONS` | 63-66 | 2 initial decisions |
| `INITIAL_CONFLICTS` | 68-70 | 1 initial conflict |
| `INITIAL_INTEL` | 72-75 | 2 initial intel items |
| `INITIAL_FEED` | 77-83 | 5 initial feed items |
| `INITIAL_INTEL_ITEMS` | 85-91 | 5 room intelligence items |
| `INITIAL_ALERTS` | 93-97 | 3 intel alerts (contradictions, alliances) |
| `INITIAL_TRUST` | 99-106 | Trust scores for 6 agents |
| `INITIAL_CONTRIBUTORS` | 108-113 | Score contributors |
| `SIMULATION_SPEECHES` | 117-124 | Fallback agent speeches |
| `SIMULATION_INTEL` | 125-128 | Fallback intel items |
| `SIMULATION_DECISIONS` | 129-132 | Fallback decisions |

### Backend Integration Status

| Frontend Data Need | Backend Endpoint | Status |
|--------------------|------------------|--------|
| Agents list | `/api/sessions/{sid}/agents` | ✅ INTEGRATED |
| Decisions | `/api/sessions/{sid}/board/decisions` | ✅ INTEGRATED |
| Conflicts | `/api/sessions/{sid}/board/conflicts` | ✅ INTEGRATED |
| Intel | `/api/sessions/{sid}/board/intel` | ✅ INTEGRATED |
| Feed | `/api/sessions/{sid}/feed` | ✅ INTEGRATED |
| Trust Scores | `/api/sessions/{sid}/intel/trust` | ✅ INTEGRATED |
| Posture | `/api/sessions/{sid}/posture` | ✅ INTEGRATED |
| Score | `/api/sessions/{sid}/score` | ✅ INTEGRATED |
| Room Intelligence | `/api/sessions/{sid}/intel` | ✅ INTEGRATED |

---

## Summary

### Integration Status: COMPLETE

The backend has **comprehensive API coverage** for all the data that the frontend needs:

- **Session Management**: `/api/sessions`, `/api/sessions/{id}`
- **Scenario**: `/api/sessions/{id}/scenario`
- **Agents**: `/api/sessions/{id}/agents`, `/api/sessions/{id}/agents/{agent_id}`
- **Crisis Board**: `/api/sessions/{id}/board`, `/board/decisions`, `/board/conflicts`, `/board/intel`
- **Feed**: `/api/sessions/{id}/feed`, `/feed/world`
- **Intelligence**: `/api/sessions/{id}/intel`, `/intel/trust`
- **Posture**: `/api/sessions/{id}/posture`
- **Score**: `/api/sessions/{id}/score`
- **World**: `/api/sessions/{id}/world`
- **Voice**: `/voice/token`, `/voice/status`, `/voice/chairman`
- **Chairman**: `/chairman/command`, `/chairman/vote`, `/chairman/commands`

### Mock Data Usage Pattern

All mock data in the frontend is properly implemented as **fallback only**:
1. The code attempts to fetch from the backend API first
2. Only when the API call fails, the mock data is used as a fallback
3. This is the correct pattern for development/demo purposes

### Recommendations

1. **No immediate integration needed** - All backend endpoints exist and are integrated
2. **Monitor for API failures** - The fallback mechanism should only be active during:
   - Development without backend running
   - Network connectivity issues
   - Backend service outages
3. **Future consideration**: Consider removing the fallback mock data in production builds to reduce bundle size, or keep for graceful degradation

---

*Generated: February 2026*
