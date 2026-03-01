# ⚔️ WAR ROOM — Complete Frontend Design Specification

**Version:** 1.0 | **Status:** Ready for Development | **Theme:** Cinematic Tactical Command Center

---

## TABLE OF CONTENTS

1. Design Language & Philosophy
2. Color System
3. Typography System
4. Spacing & Grid System
5. Layout Architecture (Macro)
6. Component Specifications (Micro)
   - 6.1 Top Command Bar
   - 6.2 Left Panel — Agent Roster
   - 6.3 Center Main Panel — Crisis Board
   - 6.4 Bottom Left — Crisis Feed
   - 6.5 Bottom Center — Agent Voice Pods
   - 6.6 Bottom Right Top — Room Intelligence
   - 6.7 Bottom Right Mid — Crisis Posture
   - 6.8 Bottom Right Bottom — Resolution Score
   - 6.9 Chairman Command Bar (Persistent Footer)
7. Animation & Motion System
8. State Definitions
9. Responsive Behavior
10. Asset & Icon System

---

## 1. DESIGN LANGUAGE & PHILOSOPHY

### Concept

**"Cinematic Tactical Realism"** — The interface should feel like a real command center designed by defense contractors and then stolen by a Silicon Valley startup. Dark, dense, data-driven, but with moments of visual drama. Every element serves a purpose. Nothing is decoration.

### Emotional Goal

The user should feel: **powerful, under pressure, and consequential**. Every second on screen should feel like the room is alive and waiting for their decision.

### Aesthetic Reference Points

- Bloomberg Terminal (density, data-first)
- Nite Owl / Watchmen Situation Room (cinematic darkness)
- SpaceX Mission Control (clean but intense)
- The reference dashboard image provided (layout density, dark map, live feeds)

### Core Design Principles

- **Information first**: No wasted pixels. Every element earns its space.
- **Hierarchy through light**: The most important information glows. Everything else recedes.
- **Controlled tension**: Use color temperature (red/amber/green) as a language the user learns within seconds.
- **The room breathes**: Subtle ambient animations make the interface feel alive even when no one is speaking.

---

## 2. COLOR SYSTEM

### Background Palette

```
--bg-deepest:      #080A0E   /* True black base — page background */
--bg-surface:      #0D1117   /* Panel backgrounds */
--bg-elevated:     #111820   /* Cards, inner panels */
--bg-hover:        #161F2A   /* Hover states on interactive items */
--bg-border:       #1E2D3D   /* Panel borders, dividers */
--bg-glass:        rgba(13, 17, 23, 0.85)  /* Frosted glass overlays */
```

### Status / Threat Colors

```
--status-critical:   #FF2D2D   /* MELTDOWN state, CRIT badges */
--status-high:       #FF6B00   /* HIGH threat, conflict indicators */
--status-elevated:   #FFB800   /* ELEVATED state, warnings */
--status-contained:  #00C896   /* Safe, agreed decisions */
--status-monitoring: #4A9EFF   /* Neutral, watching */
--status-silent:     #6B7A8D   /* Inactive, offline agents */
```

### Accent & UI Colors

```
--accent-primary:    #4A9EFF   /* Primary interactive, links, cursor */
--accent-glow:       #4A9EFF33 /* Glow halos behind active elements */
--accent-voice:      #00E5FF   /* Voice waveform, mic active */
--accent-intel:      #B44DFF   /* Room Intelligence panel accent */
--accent-gold:       #FFD700   /* Chairman rank, resolution score target */
```

### Text Palette

```
--text-primary:      #E8EDF2   /* Main readable text */
--text-secondary:    #8A9BB0   /* Labels, metadata, subtitles */
--text-muted:        #4A5568   /* Timestamps, inactive labels */
--text-critical:     #FF2D2D   /* Alert text, critical values */
--text-code:         #7EE8A2   /* Monospace data, scores, percentages */
```

### Gradient Definitions

```
--gradient-critical:   linear-gradient(135deg, #FF2D2D22, #FF6B0011)
--gradient-panel:      linear-gradient(180deg, #111820, #0D1117)
--gradient-crisis-board: linear-gradient(135deg, #0D1117 0%, #111820 100%)
--gradient-scanline:   repeating-linear-gradient(
                         0deg, transparent, transparent 2px,
                         rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px
                       )  /* Subtle CRT scanline texture on main panels */
```

---

## 3. TYPOGRAPHY SYSTEM

### Font Families

```
Display (Headers, Crisis Title, Agent Names):
  Font: "Rajdhani" (Google Fonts)
  Weight: 600, 700
  Character: Military-adjacent, wide, readable at small sizes
  Use: Panel headers, agent names, threat level badges

Body (Data, labels, descriptions):
  Font: "IBM Plex Mono"
  Weight: 400, 500
  Character: Technical, terminal-like, trustworthy
  Use: All data values, timestamps, transcripts, status labels

UI Labels (buttons, tabs, nav):
  Font: "Barlow Condensed"
  Weight: 500, 600
  Character: Condensed, space-efficient
  Use: Tab labels, button text, panel section headers

Numbers / Scores:
  Font: "Orbitron"
  Weight: 700, 900
  Character: Sci-fi numeric, high visual impact
  Use: Resolution Score, countdown timer, threat percentages
```

### Type Scale

```
--text-2xs:   9px  / line-height: 1.4   /* Timestamps, minor metadata */
--text-xs:    11px / line-height: 1.4   /* Panel sub-labels */
--text-sm:    12px / line-height: 1.5   /* Body data, feed items */
--text-base:  13px / line-height: 1.5   /* Default UI text */
--text-md:    14px / line-height: 1.4   /* Agent names, section headers */
--text-lg:    16px / line-height: 1.3   /* Panel titles */
--text-xl:    20px / line-height: 1.2   /* Crisis title in top bar */
--text-2xl:   28px / line-height: 1.1   /* Resolution Score number */
--text-3xl:   48px / line-height: 1.0   /* Intro/landing screen only */
```

### Letter Spacing

```
Headers:        letter-spacing: 0.08em   (wide, command-style)
Panel Titles:   letter-spacing: 0.12em   (very wide, all-caps)
Body:           letter-spacing: 0.02em   (slight, for mono readability)
Score Numbers:  letter-spacing: -0.02em  (tight, impactful)
```

---

## 4. SPACING & GRID SYSTEM

### Base Unit

```
--space-unit: 4px
All spacing is multiples: 4, 8, 12, 16, 20, 24, 32, 40, 48
```

### Panel Padding

```
Panel outer padding:      16px (4 units)
Panel inner sections:     12px (3 units)
Panel header:             12px top/bottom, 16px left/right
Item row padding:         8px top/bottom, 12px left/right
Compact item padding:     6px top/bottom, 10px left/right
```

### Panel Gap

```
Gap between panels:       4px  (deliberate: tight, dense)
Panel border radius:      0px  (NO rounded corners — sharp, tactical)
Inner card radius:        2px  (minimal softening only for agent pods)
```

---

## 5. LAYOUT ARCHITECTURE (MACRO)

### Overall Grid

The full viewport is a strict CSS Grid. No scrolling on the main dashboard — everything visible at 1440x900 minimum.

```
VIEWPORT: 100vw × 100vh  |  overflow: hidden

ROW STRUCTURE:
  Row 1 — Top Bar:        48px  fixed
  Row 2 — Main Area:      calc(55vh - 48px)
  Row 3 — Bottom Area:    45vh
  Row 4 — Command Bar:    52px  fixed
```

### Column Structure — Row 2 (Main Area)

```
  Col A — Agent Roster:   220px  fixed
  Col B — Crisis Board:   1fr    fills remaining space
```

### Column Structure — Row 3 (Bottom Area)

```
  Col A — Crisis Feed:    260px  fixed
  Col B — Agent Pods:     1fr    fills middle
  Col C — Right Stack:    300px  fixed
```

### Right Column Stack — Col C, Row 3

```
  Top:     Room Intelligence     ~40% of column height
  Middle:  Crisis Posture        ~35% of column height
  Bottom:  Resolution Score      ~25% of column height
  (Inner borders between the three: 1px solid var(--bg-border))
```

### Visual Separation Language

```
- All panel borders:          1px solid var(--bg-border)
- Panel backgrounds:          var(--bg-surface)
- Gap between panels (4px):   shows var(--bg-deepest) — dark seams
- No box shadows between panels (borders only)
- Scanline overlay:           ::before on full viewport, pointer-events: none
```

---

## 6. COMPONENT SPECIFICATIONS

---

### 6.1 TOP COMMAND BAR

**Height:** 48px | **Background:** `#080A0E` | **Border-bottom:** `1px solid var(--bg-border)`

#### Left Section (240px)

```
[ ⚔️ WAR ROOM ]  [ CRISIS: Hospital AI Scandal ]

- Logo mark: SVG crosshair icon, color: var(--accent-primary), 18px
- "WAR ROOM": Rajdhani 700, 14px, letter-spacing 0.12em, --text-primary
- Separator: 1px solid var(--bg-border), height 20px, margin 0 12px
- Crisis label: IBM Plex Mono 400, 9px, --text-muted, "CRISIS:"
- Crisis title: IBM Plex Mono 500, 11px, --text-secondary
  Max-width: 180px, overflow: hidden, text-overflow: ellipsis
```

#### Center Section (flex: 1)

```
[ WED 25 FEB 2026  •  14:23:07 UTC ]

- Font: IBM Plex Mono 400, 12px, --text-muted
- Live clock: updates every second
- Separator dot: --text-muted
- text-align: center
```

#### Right Section (flex row, gap: 16px, padding-right: 20px)

```
Component 1 — MIC STATUS:
  Active:   [●] MIC ACTIVE — dot pulsing green, Barlow Condensed 500, 10px, --accent-voice
  Muted:    [●] MIC MUTED  — dot grey, same font, --text-muted
  Dot: 6px circle, 1.5s pulse animation (opacity 1→0.4→1)

Component 2 — SESSION LIVE BADGE:
  [🔴 LIVE]
  Dot: 6px, --status-critical, 1s pulse (opacity 1→0.3→1)
  Text: Barlow Condensed 600, 11px, --status-critical
  Letter-spacing: 0.12em

Component 3 — THREAT LEVEL BADGE:
  Text: "THREAT: [LEVEL]" — Barlow Condensed 600, 11px, letter-spacing 0.12em
  Background: var(--gradient-critical) at CRITICAL state
  Border: 1px solid [status color]
  Padding: 4px 10px
  Color changes:
    CONTAINED:  border/text --status-contained, bg rgba(0,200,150,0.1)
    ELEVATED:   border/text --status-elevated,  bg rgba(255,184,0,0.1)
    CRITICAL:   border/text --status-critical,  bg rgba(255,45,45,0.1)
    MELTDOWN:   border/text --status-critical,  bg rgba(255,45,45,0.2), flashing
  On level change: background flashes white 100ms then settles 400ms

Component 4 — COUNTDOWN TIMER:
  Format: HH:MM:SS
  Font: Orbitron 700, 14px
  Color: --status-elevated when >30min
  Color: --status-critical when <10min
  <5min: blinks (opacity 1→0.5, 0.5s infinite)

Component 5 — SETTINGS:
  Gear SVG icon, 16px, --text-muted
  Hover: rotate 60deg (transition 300ms ease), color --text-secondary
```

---

### 6.2 LEFT PANEL — AGENT ROSTER

**Width:** 220px | **Height:** full Row 2 | **Background:** `var(--bg-surface)`

#### Panel Header

```
Height: 36px
Padding: 0 16px
Border-bottom: 1px solid var(--bg-border)
Layout: flex, space-between, align-center

Left:  "CRISIS TEAM" — Barlow Condensed 600, 11px, letter-spacing 0.12em, --text-secondary
Right: "?" help icon — IBM Plex Mono 400, 11px, --text-muted, hover: --accent-primary
```

#### Agent Entry (repeating component)

```
Height: auto (min 64px)
Padding: 10px 12px
Border-bottom: 1px solid var(--bg-border)
Cursor: pointer
Transition: background 150ms ease

DEFAULT layout:
  Row 1: [STATUS DOT 8px] [AGENT NAME] 
  Row 2: [padding-left 18px] [ROLE LABEL]
  Row 3: [padding-left 18px] [STATUS LINE]

STATUS DOT (8px × 8px circle):
  SPEAKING:   #00C896, filter: drop-shadow(0 0 4px #00C896), scale pulse 1→1.3→1 at 1.5s
  THINKING:   #FFB800, steady glow, slow pulse 3s
  CONFLICTED: #FF2D2D, rapid flash opacity 1→0.3 at 0.5s
  LISTENING:  #4A9EFF, steady, no animation
  SILENT:     #4A5568, no glow, no animation

AGENT NAME:
  Rajdhani 600, 13px, letter-spacing 0.04em, --text-primary

ROLE LABEL:
  IBM Plex Mono 400, 10px, --text-secondary

STATUS LINE — varies by state:
  SPEAKING:    5 animated bars (green waveform, CSS @keyframes heights)
  THINKING:    "· · ·  processing" — dots animate in sequence, --text-muted
  CONFLICTED:  "⚡ CONFLICT: [other agent]" — --status-high, 10px
  LISTENING:   "👂 listening" — --text-muted, italic
  SILENT:      "[last 6 words spoken]..." — --text-muted, italic, truncated

HOVER STATE:
  Background: var(--bg-hover)

SELECTED STATE (user clicked to address):
  Border-left: 3px solid var(--accent-primary)
  Background: var(--bg-hover)
  Agent name color: var(--accent-primary)
  Left padding reduces by 3px to compensate for border

TRUST TOOLTIP (on hover, appears right of panel):
  Absolute positioned card, z-index 100
  "[Name] — Trust: 72%" + mini bar
  Background: var(--bg-elevated), border: 1px solid var(--bg-border)
  Padding: 8px 10px, font: IBM Plex Mono 400, 10px
  Appears 200ms after hover, disappears on mouse-out
```

#### Summon Agent Button

```
Position: after last agent entry
Height: 48px
Border: 1px dashed var(--bg-border)
Background: transparent
Content (centered):
  "+ SUMMON AGENT" — Barlow Condensed 600, 11px, letter-spacing 0.08em
  --text-muted default, --accent-primary on hover
Hover:
  Border-color: var(--accent-primary)
  Background: rgba(74,158,255,0.04)
  Transition: all 200ms ease
```

---

### 6.3 CENTER MAIN PANEL — CRISIS BOARD

**Width:** 1fr | **Height:** full Row 2 | **Background:** `var(--bg-surface)`

#### Panel Header

```
Height: 36px
Padding: 0 16px
Border-bottom: 1px solid var(--bg-border)
Layout: flex, space-between, align-center

LEFT: "CRISIS BOARD" — Barlow Condensed 600, 11px, letter-spacing 0.12em, --text-secondary

CENTER: Replay Tab Group
  [ NOW ] [ -5m ] [ -10m ] [ -20m ] [ FULL ]
  Each tab: IBM Plex Mono 400, 10px, padding 4px 8px
  Active tab: --accent-primary, border-bottom 2px solid --accent-primary
  Inactive: --text-muted
  Hover: --text-secondary
  Gap between tabs: 4px

RIGHT: Action buttons (flex row, gap 8px)
  [ 📌 PIN DECISION ] [ 🔊 BROADCAST ]
  Barlow Condensed 500, 10px
  Padding: 4px 8px
  Border: 1px solid var(--bg-border)
  Background: transparent
  Hover: var(--bg-hover)
```

#### Three-Column Board

```
Internal grid: 3 equal columns (1fr 1fr 1fr)
Column gap: 1px (--bg-deepest shows through — a seam)
Overflow-y: auto per column (custom scrollbar, thin, --bg-border track)

COLUMN 1 — AGREED DECISIONS
  Column header bar:
    Background: rgba(0,200,150,0.06)
    Border-bottom: 1px solid rgba(0,200,150,0.25)
    Padding: 8px 12px
    Text: "✓ AGREED DECISIONS" — Barlow Condensed 600, 10px, letter-spacing 0.12em, --status-contained

  Each item:
    Padding: 8px 12px
    Border-bottom: 1px solid var(--bg-border)
    Layout:
      Row 1: "✅ [Decision summary text]"
        Checkmark: --status-contained
        Text: IBM Plex Mono 400, 11px, --text-primary
      Row 2: "[HH:MM] • [Agent who proposed]"
        Font: IBM Plex Mono 400, 9px, --text-muted
    
    NEW item entrance:
      Slides from opacity:0, translateY(-4px) → visible in 250ms
      Brief left-border flash: 2px solid --status-contained → fades 600ms
      Brief background flash: rgba(0,200,150,0.12) → transparent 400ms

COLUMN 2 — OPEN CONFLICTS
  Column header bar:
    Background: rgba(255,45,45,0.06)
    Border-bottom: 1px solid rgba(255,45,45,0.25)
    Padding: 8px 12px
    Text: "⚡ OPEN CONFLICTS" — Barlow Condensed 600, 10px, --status-critical

  Each item:
    Padding: 8px 12px
    Border-bottom: 1px solid var(--bg-border)
    Border-left: 2px solid var(--status-critical)
    Background: rgba(255,45,45,0.03)
    Layout:
      Row 1: "🔥 [Conflict description]"
        Fire icon: slow flicker via opacity 1→0.7→1, 2s infinite
        Text: IBM Plex Mono 400, 11px, --text-primary
      Row 2: "[Agent A] ←→ [Agent B]"
        Font: IBM Plex Mono 500, 9px, --status-high
    
    NEW item entrance:
      Flashes red background twice (rgba(255,45,45,0.2) → transparent × 2, 300ms each)
      Then settles into permanent red-left-border style

COLUMN 3 — CRITICAL INTEL
  Column header bar:
    Background: rgba(74,158,255,0.06)
    Border-bottom: 1px solid rgba(74,158,255,0.25)
    Padding: 8px 12px
    Text: "📌 CRITICAL INTEL" — Barlow Condensed 600, 10px, --accent-primary

  Each item:
    Padding: 8px 12px
    Border-bottom: 1px solid var(--bg-border)
    Border-left: 2px solid var(--accent-primary)
    Background: rgba(74,158,255,0.03)
    Layout:
      Row 1: "📌 [Intel text]"
        Pin icon: --accent-primary
        Text: IBM Plex Mono 400, 11px, --text-primary
      Row 2: "Source: [World Agent / Agent Name]"
        Font: IBM Plex Mono 400, 9px, --text-muted
```

#### Escalation Event Banner

```
Trigger: World Agent fires an escalation event
Position: Absolutely positioned, top of Crisis Board panel, full width
Height: 48px
Z-index: 10

Styles:
  Background: rgba(255,107,0,0.12)
  Border: 1px solid var(--status-high)
  Border-left: 4px solid var(--status-high)
  Padding: 0 16px
  Layout: flex, align-center, gap: 12px

Content:
  Left:   📡 icon (18px, --status-high)
  Center: "ESCALATION: [event text]" — Rajdhani 600, 13px, --text-primary
  Right:  "[HH:MM:SS]" — IBM Plex Mono 400, 10px, --text-muted

Entrance animation: translateY(-48px)→translateY(0), 300ms cubic-bezier(0.16,1,0.3,1)
Auto-dismiss: slides back up after 8 seconds
```

---

### 6.4 BOTTOM LEFT — CRISIS FEED

**Width:** 260px | **Height:** full Row 3 | **Background:** `var(--bg-surface)`

#### Panel Header

```
Height: 36px
Padding: 0 12px
Border-bottom: 1px solid var(--bg-border)
Layout: flex, space-between, align-center

Left:  "CRISIS FEED" — Barlow Condensed 600, 11px, letter-spacing 0.12em, --text-secondary
Right: [🔴 LIVE] — 6px red dot + "LIVE", --status-critical, 10px Barlow Condensed
```

#### Category Tab Bar

```
Height: 32px
Overflow-x: scroll, scrollbar hidden
Padding: 0 8px
Border-bottom: 1px solid var(--bg-border)
Flex row, gap: 2px

Tabs: [ WORLD ] [ LEGAL ] [ MEDIA ] [ INTERNAL ] [ SOCIAL ]
  Font: Barlow Condensed 500, 10px, letter-spacing 0.08em
  Padding: 8px 10px
  Active: color --accent-primary, border-bottom 2px solid --accent-primary, bg rgba(74,158,255,0.08)
  Inactive: --text-muted
  Hover: --text-secondary, bg var(--bg-hover)
```

#### Feed Item

```
Height: auto (~56px min)
Padding: 8px 10px
Border-bottom: 1px solid var(--bg-border)
Cursor: pointer
Hover: background var(--bg-hover)

Layout:
  Row 1 (flex, space-between):
    Left:  [CATEGORY ICON 12px] [SOURCE NAME] — IBM Plex Mono 500, 10px, --text-secondary
    Right: [TIMESTAMP] — IBM Plex Mono 400, 9px, --text-muted
  Row 2:
    [Headline text] — IBM Plex Mono 400, 11px, --text-primary
    Max 2 lines, overflow: hidden, display: -webkit-box, -webkit-line-clamp: 2
  Row 3 (if viral/metric):
    [↗️ 47K impressions] — IBM Plex Mono 400, 9px, --status-critical for high numbers

Category Icons (12px emoji prefix):
  WORLD:    🌍
  LEGAL:    ⚖️
  MEDIA:    📰
  INTERNAL: 💬
  SOCIAL:   🐦

STANDARD new item:
  Background flash: rgba(74,158,255,0.12) → transparent, 500ms
  Left border: 2px solid --accent-primary → transparent, 600ms

BREAKING item special styles:
  Background: rgba(255,45,45,0.05)
  Border-left: 2px solid var(--status-critical)
  Source label replaced with: "🚨 BREAKING" in --status-critical
  On arrival: panel header briefly flashes rgba(255,45,45,0.1), 500ms
```

---

### 6.5 BOTTOM CENTER — AGENT VOICE PODS

**Width:** 1fr | **Height:** full Row 3 | **Background:** `var(--bg-deepest)`

#### Panel Header

```
Height: 36px
Padding: 0 16px
Border-bottom: 1px solid var(--bg-border)
Layout: flex, space-between, align-center

Left:  "AGENT FEEDS" — Barlow Condensed 600, 11px, letter-spacing 0.12em, --text-secondary
Right: Filter tabs: [ ALL ] [ ACTIVE ] [ CONFLICTED ]
  Barlow Condensed 500, 10px
  Active tab: --accent-primary, border-bottom 2px solid
  Inactive: --text-muted
  Tab padding: 6px 8px
```

#### Pod Grid

```
Display: grid
Grid-template-columns: repeat(auto-fill, minmax(160px, 1fr))
Gap: 4px
Padding: 8px
Overflow: hidden
```

#### Agent Pod — Base Structure

```
Background: var(--bg-surface)
Border: 1px solid var(--bg-border)
Border-radius: 2px
Padding: 12px
Min-height: 110px
Cursor: pointer
Transition: border-color 200ms, box-shadow 200ms, background 200ms

Layout (flex column):
  Row 1: Agent name — Rajdhani 600, 12px, --text-primary
  Row 2: Role — IBM Plex Mono 400, 9px, --text-secondary, margin-bottom 8px
  Row 3: Waveform area — 28px height (flex align-end, gap 2px)
  Row 4: Status label — IBM Plex Mono 500, 10px, margin-top 6px
  Row 5: Transcript snippet — IBM Plex Mono 400, 10px, --text-muted, italic, 2 lines max
```

#### Pod States

**IDLE / LISTENING:**

```
Border: 1px solid var(--bg-border)
Waveform: 5 flat bars, height 2px, --bg-elevated
Status: "👂 LISTENING" — --text-muted
```

**SPEAKING:**

```
Border: 1px solid rgba(0,229,255,0.45)
Box-shadow: 0 0 14px rgba(0,229,255,0.15), inset 0 0 20px rgba(0,229,255,0.03)
Background: var(--bg-elevated)

Waveform: 7 bars, color --accent-voice (#00E5FF)
  Bar widths: 3px each, gap 2px
  Heights: animate via @keyframes, 80ms intervals
  Heights cycle: 40%→100%→20%→80%→60% (staggered per bar)

Status: "🎙️ SPEAKING" — --accent-voice, IBM Plex Mono 500, 10px
Transcript: text rolls in word-by-word (JS typewriter effect)
```

**THINKING:**

```
Border: 1px solid rgba(255,184,0,0.3)
Waveform: flat bars, color --bg-elevated

Status: "💭 PROCESSING" — --status-elevated, IBM Plex Mono 500, 10px
  Followed by animated dots: dot 1 fades in 0s, dot 2 at 0.3s, dot 3 at 0.6s
  Loop: 1.8s infinite
```

**CONFLICTED:**

```
Border: 1px solid rgba(255,45,45,0.5)
Box-shadow: 0 0 12px rgba(255,45,45,0.1)
Background: rgba(255,45,45,0.03)

Waveform: 5 bars, color --status-critical
  Heights animate at 40ms (more agitated than speaking)

Status: "⚡ CONFLICTING" — --status-critical, IBM Plex Mono 500, 10px
Sub-status: "with [Agent Name]" — --text-muted, 9px
```

**SUMMON POD (last slot):**

```
Border: 1px dashed var(--bg-border)
Background: transparent
Content (flex column, centered):
  "+" — Rajdhani 700, 24px, --text-muted
  "SUMMON" — Barlow Condensed 600, 11px, --text-muted
  "AGENT" — Barlow Condensed 600, 11px, --text-muted
Hover:
  Border-color: --accent-primary, border-style: solid
  Text color: --accent-primary
  Background: rgba(74,158,255,0.04)
```

---

### 6.6 BOTTOM RIGHT TOP — ROOM INTELLIGENCE

**Width:** 300px | **Height:** ~40% of right column | **Background:** `var(--bg-surface)`
**Accent:** `--accent-intel` (#B44DFF)

#### Panel Header

```
Height: 36px
Padding: 0 12px
Border-bottom: 1px solid rgba(180,77,255,0.25)
Background: rgba(180,77,255,0.04)
Layout: flex, space-between, align-center

Left:  "ROOM INTELLIGENCE" — Barlow Condensed 600, 11px, --accent-intel, letter-spacing 0.12em
Right: ⓘ — IBM Plex Mono 400, 12px, --text-muted
```

#### Intelligence Items

**CONTRADICTION:**

```
Padding: 8px 10px 8px 12px
Border-bottom: 1px solid var(--bg-border)
Border-left: 2px solid var(--status-high)
Background: rgba(255,107,0,0.05)

Row 1: "⚠️ CONTRADICTION" — Barlow Condensed 600, 10px, --status-high, letter-spacing 0.08em
Row 2: [Body text] — IBM Plex Mono 400, 10px, --text-primary, 3 lines max
Row 3: "[HH:MM] vs [HH:MM]" — IBM Plex Mono 400, 9px, --text-muted
```

**ALLIANCE:**

```
Border-left: 2px solid var(--accent-primary)
Background: rgba(74,158,255,0.05)

Row 1: "🤝 ALLIANCE FORMING" — Barlow Condensed 600, 10px, --accent-primary
Row 2: [Body text] — IBM Plex Mono 400, 10px, --text-primary
```

**BLIND SPOT / UNASKED:**

```
Border-left: 2px solid var(--accent-intel)
Background: rgba(180,77,255,0.05)

Row 1: "🎯 CRITICAL UNASKED" — Barlow Condensed 600, 10px, --accent-intel
Row 2: [Body text] — IBM Plex Mono 400, 10px, --text-primary
```

#### Trust Score Section

```
Divider: 1px solid var(--bg-border)
Header: "AGENT TRUST SCORES" — Barlow Condensed 600, 9px, --text-muted, letter-spacing 0.12em
        Padding: 6px 10px

Each row (padding: 5px 10px):
  Layout: flex, space-between, align-center, gap 8px
  
  Left: [Agent surname] — IBM Plex Mono 400, 9px, --text-secondary, width 60px
  Center: Progress bar track (flex: 1, height 3px, background --bg-elevated)
    Fill bar: color depends on value, border-radius 1px
    >75%: --status-contained
    50-75%: --status-elevated
    <50%: --status-critical
    Width transition: 500ms ease on value change
  Right: "[##]%" — Orbitron 700, 10px, matching fill color, width 30px, text-align right

On trust DROP: bar briefly flashes red → settles (200ms flash, 300ms settle)
On trust RISE: bar briefly flashes brighter → settles
```

---

### 6.7 BOTTOM RIGHT MID — CRISIS POSTURE

**Width:** 300px | **Height:** ~35% of right column | **Background:** `var(--bg-surface)`

#### Panel Header

```
Height: 36px
Padding: 0 12px
Border-bottom: 1px solid var(--bg-border)
Layout: flex, space-between, align-center

Left:  "CRISIS POSTURE" — Barlow Condensed 600, 11px, letter-spacing 0.12em, --text-secondary
Right: Badge — "1 NEW UPDATE" — IBM Plex Mono 500, 9px, padding: 2px 6px
       Background: rgba(255,107,0,0.2), color: --status-high
       Border: 1px solid var(--status-high)
       Disappears after 3 seconds
```

#### Posture Axis (3 rows, each ~28px)

```
Each axis:
  Padding: 8px 12px
  Border-bottom: 1px solid var(--bg-border)

  Row 1: flex, space-between, align-center
    Left:  [AXIS LABEL] — Barlow Condensed 600, 10px, letter-spacing 0.08em, --text-secondary
    Right: [STATUS BADGE] — Barlow Condensed 600, 9px, padding 2px 6px
      CRIT: bg rgba(255,45,45,0.2),   border --status-critical, text --status-critical
      HIGH: bg rgba(255,107,0,0.2),   border --status-high,     text --status-high
      ELEV: bg rgba(255,184,0,0.2),   border --status-elevated, text --status-elevated
      CONT: bg rgba(0,200,150,0.2),   border --status-contained, text --status-contained
  
  Row 2: Progress bar (full width, height 5px, margin: 4px 0)
    Track: var(--bg-elevated)
    Fill: gradient — [color] 0% → [lighter color] 100%
    Width: [percentage]% of parent
    Transition: width 800ms ease on change
  
  Row 3: Sub-metrics — IBM Plex Mono 400, 9px, --text-muted
    e.g. "Media awareness  •  Viral velocity: ↑ RISING"
    Arrow ↑ in --status-critical, ↓ in --status-contained, → in --status-elevated

AXIS LABELS:
  Row 1: PUBLIC EXPOSURE
  Row 2: LEGAL EXPOSURE
  Row 3: INTERNAL STABILITY (inverted — high % = GOOD)
```

---

### 6.8 BOTTOM RIGHT BOTTOM — RESOLUTION SCORE

**Width:** 300px | **Height:** ~25% of right column | **Background:** `var(--bg-surface)`

#### Panel Header

```
Height: 36px
Padding: 0 12px
Border-bottom: 1px solid var(--bg-border)
Layout: flex, space-between, align-center

Left:  "RESOLUTION SCORE" — Barlow Condensed 600, 11px, letter-spacing 0.12em, --text-secondary
Right: [🔴 LIVE] badge — same as top bar
```

#### Score Display (main body)

```
Layout: flex column, align-center, padding: 12px

The Big Number:
  Font: Orbitron 900, 48px
  letter-spacing: -0.02em
  Color mapping (with text-shadow glow):
    70–100: --status-contained,  glow rgba(0,200,150,0.4)
    40–69:  --status-elevated,   glow rgba(255,184,0,0.4)
    20–39:  --status-high,       glow rgba(255,107,0,0.4)
    0–19:   --status-critical,   glow rgba(255,45,45,0.4)
  
  On change: animated counter (JS requestAnimationFrame, 600ms ease-out)
  On DROP: brief red flash then settle
  On RISE: brief green flash then settle

State Label (below number, margin-top 4px):
  Font: Barlow Condensed 700, 12px, letter-spacing 0.12em, all-caps
  Values: "RESOLVED" / "RECOVERING" / "CRITICAL" / "MELTDOWN"
  Color: matches number color

Trend Row (flex, align-center, gap 6px, margin-top 4px):
  "TREND:" — IBM Plex Mono 400, 9px, --text-muted
  "↑ IMPROVING" / "↓ FALLING" / "→ STABLE"
  Font: IBM Plex Mono 500, 10px, matching status color
  Arrow animates on change: scale 1.3→1, 200ms
```

#### Score Context (bottom strip)

```
Border-top: 1px solid var(--bg-border)
Padding: 8px 12px
Background: var(--bg-elevated)

Line 1: "Target: 70+ to avoid public fallout"
  IBM Plex Mono 400, 9px, --text-muted

Line 2: "Key driver: [auto text from Observer Agent]"
  IBM Plex Mono 400, 9px, --text-primary

Line 3: "Next escalation in: [M:SS]"
  IBM Plex Mono 500, 10px, --status-high
  Countdown ticks every second
  Blinks when under 60 seconds
```

---

### 6.9 CHAIRMAN COMMAND BAR (PERSISTENT FOOTER)

**Height:** 52px | **Background:** `#080A0E` | **Border-top:** `1px solid var(--bg-border)`
**Position:** fixed, bottom: 0, left: 0, right: 0 | **Z-index:** 100

```
Layout: flex row, align-center, padding: 0 20px, gap: 12px
```

#### Segment 1 — Address Target Selector (160px)

```
Dropdown button:
  Height: 32px
  Padding: 0 12px
  Font: Barlow Condensed 600, 12px, letter-spacing 0.06em
  Color: --accent-primary
  Background: rgba(74,158,255,0.06)
  Border: 1px solid rgba(74,158,255,0.35)
  
  Default text: "▶ FULL ROOM ▼"
  Selected agent: "▶ [SURNAME] ▼"
  
  Dropdown panel:
    Position: absolute, bottom 100%, margin-bottom 4px
    Background: var(--bg-elevated)
    Border: 1px solid var(--bg-border)
    Min-width: 180px
    
    Options:
      "📢 FULL ROOM" (default)
      [agent name + role, one per line]
      Each: padding 8px 12px, IBM Plex Mono 400, 11px
      Hover: var(--bg-hover), color --accent-primary
      Selected: left border 2px --accent-primary
```

#### Segment 2 — Mic Button (44px × 44px)

```
Shape: Square (border-radius: 2px)

INACTIVE:
  Background: var(--bg-elevated)
  Border: 1px solid var(--bg-border)
  Icon: microphone SVG, 18px, --text-muted

RECORDING:
  Background: rgba(0,229,255,0.1)
  Border: 1px solid var(--accent-voice)
  Icon: microphone SVG, 18px, --accent-voice
  Outer ring: 
    Pseudo-element ::before
    Border: 2px solid rgba(0,229,255,0.3)
    Border-radius: 2px
    Animation: scale 1→1.4, opacity 1→0, 1.2s infinite
    
Interaction: hold-to-talk
  Mousedown → start recording
  Mouseup → stop, send
  Spacebar = same behavior
  On press: scale(0.94) 100ms
```

#### Segment 3 — Voice Waveform (180px)

```
Height: 28px
20 vertical bars, each 4px wide, gap 2px
When recording: bars animate (heights vary 15%–100%, 80ms interval), color --accent-voice
When silent: all bars at 2px height (flat baseline), color --bg-elevated
Transition: smooth, 100ms ease per bar
```

#### Segment 4 — Live Transcript (flex: 1)

```
Height: 32px
Background: var(--bg-elevated)
Border: 1px solid var(--bg-border)
Padding: 0 12px
Overflow: hidden
Layout: flex, align-center

"CHAIRMAN: " prefix:
  IBM Plex Mono 600, 11px, --accent-gold
  
Live text:
  IBM Plex Mono 400, 12px, --text-primary
  Words appear in real-time as spoken
  Previous sentence: fades to --text-muted after new sentence starts
  
Empty state: "Hold space or click mic to speak..." — IBM Plex Mono 400, 11px, --text-muted, italic
```

#### Segment 5 — Action Buttons (right side, flex row, gap 6px)

```
Each button:
  Height: 32px
  Padding: 0 10px
  Font: Barlow Condensed 500, 10px, letter-spacing 0.06em
  Border: 1px solid var(--bg-border)
  Background: transparent
  Color: --text-secondary
  Hover: background var(--bg-hover), color --text-primary
  Active/press: scale(0.97)

Buttons:
  [ 🗳️ FORCE VOTE ]    — triggers voting overlay on Crisis Board
  [ ❌ DISMISS AGENT ] — removes selected agent (disabled if none selected, opacity 0.4)
  [ ⏸️ PAUSE ROOM ]   — freezes all agent activity (toggles to ▶ RESUME)
```

---

## 7. ANIMATION & MOTION SYSTEM

### Global Ambient

```
SCANLINE SWEEP:
  Element: body::before pseudo
  Background: linear-gradient(transparent 50%, rgba(255,255,255,0.015) 50%)
  Background-size: 100% 4px
  Pointer-events: none, z-index: 9999
  Opacity: 0.4 (barely perceptible — just adds depth)
  This is STATIC — a texture, not animated.

ACTIVE PANEL PULSE (for Room Intelligence, Posture, Score):
  @keyframes panelBreath:
    0%: background rgba(13,17,23,1.0)
    50%: background rgba(13,17,23,0.85) + brightness(1.03)
    100%: background rgba(13,17,23,1.0)
  Duration: 5s infinite ease-in-out
  Only applies when data is actively updating
```

### Transition Tokens

```
--transition-fast:   150ms ease
--transition-base:   300ms ease
--transition-slow:   500ms ease
--transition-enter:  300ms cubic-bezier(0.16, 1, 0.3, 1)   /* spring in */
--transition-exit:   200ms cubic-bezier(0.4, 0, 1, 1)      /* quick out */
```

### Named Animations

```
@keyframes statusPulse     — dot opacity 1→0.3→1 (threat/live indicators)
@keyframes waveformBar     — height random cycle (speaking agents)
@keyframes thinkingDots    — sequential dot fade-in (thinking state)
@keyframes escalationSlide — translateY(-48px)→0 (crisis board banner)
@keyframes flashAlert      — background white flash → settle
@keyframes countUp/Down    — JS-driven number animation on score
@keyframes ringExpand      — mic button outer ring scale + fade
@keyframes agentEntrance   — translateY(8px)+opacity:0 → settled (when new agent added)
```

---

## 8. STATE DEFINITIONS

### Session Flow States

```
1. PRE-CRISIS — Landing/Input
   Single input centered on --bg-deepest
   Subtle particle field (slow-moving dots) in background
   No panels. No bar. Full drama.
   Input: "Describe your crisis." — placeholder in IBM Plex Mono, --text-muted
   CTA: "ASSEMBLE THE ROOM" button

2. ASSEMBLING — Loading
   Panels begin to appear (fade in from opacity:0 with 100ms stagger)
   Agent cards reveal one by one (200ms stagger, translateY(8px)→0)
   Briefing text types out character by character (40ms per char)
   "Generating crisis team..." in top bar instead of threat level

3. ACTIVE — Main Dashboard
   Full UI visible and functional
   All panels populated
   Agents in pods
   Feed, Intelligence, Posture, Score all live

4. ESCALATION — Overlay State
   Escalation banner appears on Crisis Board
   All agent pods briefly flash THINKING state (500ms)
   Room Intelligence fires new analysis item
   Threat badge may upgrade (flash animation on change)

5. RESOLUTION — Endgame
   Timer hits 00:00 OR Chairman calls "FORCE VOTE"
   Each pod zooms its final statement text (scale 1→1.05→1)
   Crisis Board locks (no new items)
   Score does final calculation + animation

6. AFTER-ACTION — Summary
   Full different screen (not the dashboard)
   Dark, clean, cinematic
   Timeline scrubber through full session
   Final scores, decision log, agent alignment analysis
   [ REPLAY ] [ NEW CRISIS ] CTAs
```

### Threat Level → UI Impact Matrix

```
CONTAINED:  badge green, top bar accent --accent-primary, scanline normal
ELEVATED:   badge amber, all panel borders gain 1px amber tint at 15% opacity
CRITICAL:   badge red, scanline animation speeds up, score glow intensifies
MELTDOWN:   entire viewport border flashes red every 8 seconds (2px border, opacity pulse),
            all conflict items pulse, waveforms turn red, timer blinks
```

---

## 9. RESPONSIVE BEHAVIOR

### Target Viewports

```
Minimum supported:  1280 × 800
Primary target:     1440 × 900
Secondary target:   1920 × 1080
4K optimization:    2560 × 1440 (max-width: 2400px centered)
Mobile:             NOT SUPPORTED (command centers don't run on phones)
```

### Breakpoint Adjustments

```
@1280px:
  Agent Roster: 200px (was 220px)
  Right Column: 260px (was 300px)
  Crisis Feed: 220px (was 260px)
  Font sizes: scale down ~10% via clamp()

@1920px:
  Agent Pods: minmax(180px, 1fr) (was 160px)
  Right Column: 340px
  Crisis Board gets extra horizontal space

@2560px:
  Entire dashboard centered, max-width: 2400px
  Background shows --bg-deepest at edges
```

### Font Scaling

```
--text-sm:       clamp(10px, 0.83vw, 12px)
--text-base:     clamp(11px, 0.9vw,  13px)
--text-md:       clamp(12px, 0.97vw, 14px)
--score-number:  clamp(32px, 3.3vw,  56px)
--timer:         clamp(12px, 0.97vw, 14px)
```

---

## 10. ASSET & ICON SYSTEM

### Icon Library

```
Primary library: Lucide Icons (consistent stroke weight, clean)
Default size: 16px unless noted
Stroke width: 1.5px (default Lucide)

Key icons:
  Mic, MicOff          — Command bar mic button
  Shield, ShieldAlert  — Threat level badge
  Users                — Agent roster header
  AlertTriangle        — Contradiction items
  Zap                  — Escalation events, conflict status
  Clock                — Countdown timer
  Activity             — Resolution score, waveform fallback
  Eye                  — Room Intelligence header
  Radio                — Live status indicators
  Plus, X              — Summon / Dismiss buttons
  ChevronDown          — Dropdown arrows
  Pause, Play          — Pause Room / Resume
  Vote (custom SVG)    — Force Vote button
  Pin                  — Critical Intel items
  Crosshair            — Logo mark (custom SVG)
```

### Custom SVG Components

```
1. WAVEFORM BARS (reusable SVG component):
   ViewBox: 40px × 20px
   5–7 rect elements, each 3px wide, gap 2px
   Animated via CSS @keyframes on height attribute
   Color: passed as prop/CSS variable
   
2. STATUS DOT (reusable):
   8px circle
   Color + glow via CSS filter
   Animation class toggleable
   
3. CIRCULAR SCORE GAUGE (Resolution Score only):
   ViewBox: 60px × 60px
   Background circle: r=25, stroke --bg-elevated, stroke-width 4
   Foreground arc: r=25, stroke-dasharray=157, stroke-dashoffset=JS-calculated
   Stroke: dynamic color, stroke-linecap: round
   Transition: stroke-dashoffset 800ms ease, stroke 300ms ease
   
4. LOGO CROSSHAIR:
   Custom SVG, 24px × 24px
   Two crossed lines + circle at center
   Thin stroke, color --accent-primary
```

### Empty & Loading States

```
Empty board column:
  Content: dashed border box, centered text
  "[No [agreements] yet]"
  IBM Plex Mono 400, 11px, --text-muted, opacity 0.5
  Border: 1px dashed --bg-border

Empty feed:
  "Monitoring channels..." 
  + single slow-pulsing status dot (--text-muted)

Loading agent pod (skeleton):
  @keyframes shimmer: background-position -200% → 200%
  Background: linear-gradient(90deg, --bg-surface, --bg-elevated, --bg-surface)
  Background-size: 200% 100%
  Duration: 1.5s infinite
  Applied to name, role, and waveform areas as rounded-rect placeholders

Loading data row (trust scores, posture bars):
  Same shimmer applied to bar track
  Number area: "—" placeholder in --text-muted
```

---

## DEVELOPER QUICK-START CHECKLIST

- [ ] Load fonts: `Rajdhani:600,700`, `IBM+Plex+Mono:400,500`, `Barlow+Condensed:500,600`, `Orbitron:700,900`
- [ ] Declare all CSS variables from Section 2 on `:root`
- [ ] Set `body { background: var(--bg-deepest); overflow: hidden; }`
- [ ] Apply scanline overlay as `body::before` (fixed, full viewport, pointer-events: none)
- [ ] Set up main CSS Grid from Section 5 (4 rows, 100vh)

- [ ] Build Top Command Bar (fixed, Row 1)
- [ ] Build Chairman Command Bar (fixed, Row 4)
- [ ] Build Row 2 grid: 220px + 1fr
- [ ] Build Row 3 grid: 260px + 1fr + 300px
- [ ] Build right column stack (3 panels stacked)
- [ ] Verify all panels have correct borders + 4px gaps

- [ ] Panel headers (all 8 panels, exact typography)
- [ ] Agent Roster with hardcoded test agents (all 5 states)
- [ ] Crisis Board with hardcoded test items in all 3 columns
- [ ] Crisis Feed with 4 hardcoded feed items
- [ ] Agent Pods with 2 speaking, 1 thinking, 1 conflicted
- [ ] Room Intelligence with 3 hardcoded item types
- [ ] Posture bars with hardcoded values
- [ ] Resolution Score with hardcoded 42

- [ ] Status dot animations (@keyframes statusPulse)
- [ ] Speaking waveform bars (@keyframes waveformBar)
- [ ] Thinking dots (@keyframes thinkingDots)
- [ ] New item entrance animations (Crisis Board, Feed)
- [ ] Score counter animation
- [ ] Mic button ring expansion
- [ ] Escalation banner slide-down

- [ ] Connect state store (Zustand recommended)
- [ ] Wire session states (Pre-crisis → Assembling → Active)
- [ ] Wire threat level changes to UI
- [ ] Wire agent status changes to pods + roster
- [ ] Wire new items to Crisis Board (animate on arrival)
- [ ] Wire new feed items (animate on arrival)
- [ ] Wire Resolution Score real-time updates

- [ ] WebSocket connection for all agent updates
- [ ] Gemini Live API for voice (per-agent)
- [ ] Chairman mic: hold-to-talk UX + waveform visualizer
- [ ] Speech-to-text → live transcript in command bar

- [ ] Test all panels at 1280px, 1440px, 1920px
- [ ] Verify no overflow/scroll on main dashboard
- [ ] Add ambient panel pulse to right column panels
- [ ] Verify threat level → full-UI color shift works
- [ ] Test MELTDOWN state (viewport border flash)
- [ ] Landing/input screen animation
- [ ] After-action screen

---

*War Room Design Spec v1.0 — Built for the Gemini Live Agent Challenge*
*Total components: 9 panels × avg 4 states each = ~36 distinct visual states*
