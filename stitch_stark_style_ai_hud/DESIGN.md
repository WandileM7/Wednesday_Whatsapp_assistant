---
name: ASTRALIS_OS
colors:
  surface: '#10141a'
  surface-dim: '#10141a'
  surface-bright: '#353940'
  surface-container-lowest: '#0a0e14'
  surface-container-low: '#181c22'
  surface-container: '#1c2026'
  surface-container-high: '#262a31'
  surface-container-highest: '#31353c'
  on-surface: '#dfe2eb'
  on-surface-variant: '#b9cacb'
  inverse-surface: '#dfe2eb'
  inverse-on-surface: '#2d3137'
  outline: '#849495'
  outline-variant: '#3a494b'
  surface-tint: '#00dbe7'
  primary: '#e1fdff'
  on-primary: '#00363a'
  primary-container: '#00f2ff'
  on-primary-container: '#006a71'
  inverse-primary: '#00696f'
  secondary: '#ffb4a2'
  on-secondary: '#621100'
  secondary-container: '#c52d01'
  on-secondary-container: '#ffe2db'
  tertiary: '#fcf5ff'
  on-tertiary: '#3c0090'
  tertiary-container: '#e3d4ff'
  on-tertiary-container: '#7318ff'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#74f5ff'
  primary-fixed-dim: '#00dbe7'
  on-primary-fixed: '#002022'
  on-primary-fixed-variant: '#004f54'
  secondary-fixed: '#ffdad2'
  secondary-fixed-dim: '#ffb4a2'
  on-secondary-fixed: '#3c0700'
  on-secondary-fixed-variant: '#8a1c00'
  tertiary-fixed: '#e9ddff'
  tertiary-fixed-dim: '#d1bcff'
  on-tertiary-fixed: '#23005b'
  on-tertiary-fixed-variant: '#5700c9'
  background: '#10141a'
  on-background: '#dfe2eb'
  surface-variant: '#31353c'
  surface-main: '#10141a'
  glow-cyan: rgba(0, 219, 231, 0.3)
  scanline-overlay: rgba(0, 219, 231, 0.05)
  error-red: '#93000a'
typography:
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 48px
    fontWeight: '700'
    lineHeight: '1.1'
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '700'
    lineHeight: '1.2'
  headline-md:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: '1.2'
    letterSpacing: 0.05em
  body-lg:
    fontFamily: Geist
    fontSize: 18px
    fontWeight: '400'
    lineHeight: '1.6'
  body-md:
    fontFamily: Geist
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.5'
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: '1.0'
    letterSpacing: 0.15em
  data-numeral:
    fontFamily: JetBrains Mono
    fontSize: 20px
    fontWeight: '700'
    lineHeight: '1.0'
spacing:
  unit: 4px
  gutter: 16px
  margin-mobile: 16px
  margin-desktop: 40px
  container-max: 1440px
---

## Brand & Style
ASTRALIS_OS is a high-performance, "Cyber-Tactical" interface designed for mission-critical command centers. The brand personality is technical, precise, and authoritative, evoking the feeling of an advanced starship's neural link. 

The design style is a hybrid of **Futuristic Brutalism** and **Glassmorphism**. It utilizes sharp geometries, "scanline" textures, and holographic glows to create a sense of digital immersion. The aesthetic prioritizes data density and system status over traditional whitespace, using glowing accents to guide the user's attention through a complex information hierarchy.

## Colors
The palette is rooted in a "Deep Space" neutral black (#0a0e14), providing a high-contrast foundation for vibrant, emissive accents. 

- **Primary (Electric Cyan):** Used for interactive elements, status indicators, and primary branding. It should always appear "emissive" via text shadows or outer glows.
- **Secondary (Warp Orange):** Reserved for warnings, high-load states, and destructive actions.
- **Surface Strategy:** Surfaces use varying levels of transparency (70-80% opacity) combined with backdrop blurs (20px+) to maintain legibility over animated background shaders.
- **Scanlines:** A global CSS linear gradient overlay creates a physical monitor effect, reinforcing the OS aesthetic.

## Typography
The typographic system uses three distinct families to categorize information:
1. **Space Grotesk (Headlines):** High-tech and geometric. Used for panel headers and system titles.
2. **Geist (Body):** Clean and functional. Used for general descriptions and settings.
3. **JetBrains Mono (Data/Labels):** Monospaced for technical accuracy. Used for logs, timestamps, sensor readings, and button labels.

All monospaced labels should be set in Uppercase with tracking (letter-spacing) increased to at least 0.15em to enhance the "coded" look.

## Layout & Spacing
The layout uses a **Modular Grid** approach. Content is housed in discrete "Modules" that are visually separated by gutters and borders rather than whitespace.

- **Grid Model:** 12-column fluid grid on desktop; single-column stack on mobile.
- **Side Navigation:** On desktop, a fixed 64px (minimized) to 256px (expanded) sidebar provides primary navigation.
- **Panel Density:** Modules should use 24px (6 units) of internal padding.
- **Hierarchy:** Critical diagnostics are placed in the top-left (Primary Reading Zone), with action directives in the bottom-right.

## Elevation & Depth
Depth is created through **Glassmorphism** and **Luminous Layering** rather than traditional shadows.

1.  **Base Layer:** Dark background with active 3D particles or WebGL shaders.
2.  **Mid Layer:** Semi-transparent panels (`bg-surface/70`) with `backdrop-blur-xl`.
3.  **Top Layer:** Interactive elements and accents.
4.  **Tactile Accents:** Use "Inner Glow" borders (`box-shadow: inset 0 0 0 1px rgba(0, 219, 231, 0.3)`).
5.  **Focus State:** Elements should "pulse" or gain a stronger outer glow (`drop-shadow`) when active or hovered.

## Shapes
The primary shape language is **Sharp and Angular**. 
- Base modules use a 0px radius (Sharp).
- **Corner Brackets:** Use L-shaped corner accents on alternate corners (Top-Left/Bottom-Right) to frame content.
- **Clipped Corners:** Action buttons and primary CTA's use a 45-degree "clip-path" on one or more corners to suggest high-tech hardware.
- **Circular Gauges:** Used exclusively for analog-style data visualization (HUD elements).

## Components
- **Buttons:**
    - *Primary:* Solid Cyan fill with black monospaced text. Clipped corners.
    - *Secondary:* Ghost style with 1px Cyan border and 5% opacity fill.
    - *Danger:* 1px Red border with 10% Red background tint.
- **Modules (Cards):** Must include `module-border` classes and corner brackets. Use backdrop blur to ensure text legibility over background animations.
- **Data Visuals:** Gauges should use double-stroke circles (one solid for value, one dashed for decoration).
- **Mission Logs:** Use a vertical border-left (2px) to denote log entry severity (Cyan for Info, Orange/Red for Warning).
- **Status Indicators:** Use a "Glow" animation (2s pulse) for "LIVE" or "ONLINE" states.
- **Scrollbars:** Ultra-thin (4px), transparent track, Cyan thumb with 30% opacity.