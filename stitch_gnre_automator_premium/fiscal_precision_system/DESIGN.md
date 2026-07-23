---
name: Fiscal Precision System
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#434656'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#737688'
  outline-variant: '#c3c5d9'
  surface-tint: '#004ced'
  primary: '#003ec7'
  on-primary: '#ffffff'
  primary-container: '#0052ff'
  on-primary-container: '#dfe3ff'
  inverse-primary: '#b7c4ff'
  secondary: '#505f76'
  on-secondary: '#ffffff'
  secondary-container: '#d0e1fb'
  on-secondary-container: '#54647a'
  tertiary: '#4b4e50'
  on-tertiary: '#ffffff'
  tertiary-container: '#636668'
  on-tertiary-container: '#e2e4e6'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dde1ff'
  primary-fixed-dim: '#b7c4ff'
  on-primary-fixed: '#001452'
  on-primary-fixed-variant: '#0038b6'
  secondary-fixed: '#d3e4fe'
  secondary-fixed-dim: '#b7c8e1'
  on-secondary-fixed: '#0b1c30'
  on-secondary-fixed-variant: '#38485d'
  tertiary-fixed: '#e0e3e5'
  tertiary-fixed-dim: '#c4c7c9'
  on-tertiary-fixed: '#191c1e'
  on-tertiary-fixed-variant: '#444749'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 48px
    fontWeight: '700'
    lineHeight: 56px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '600'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 18px
    fontWeight: '400'
    lineHeight: 28px
  body-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 16px
  label-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  unit: 4px
  container-max: 1440px
  gutter: 24px
  margin-mobile: 16px
  margin-desktop: 32px
  stack-xs: 4px
  stack-sm: 8px
  stack-md: 16px
  stack-lg: 24px
  stack-xl: 48px
---

## Brand & Style

This design system is engineered for a high-stakes SaaS environment where tax automation meets enterprise-grade reliability. The brand personality is **authoritative, surgical, and frictionless**. It draws inspiration from the "utility-luxe" aesthetic—combining the systematic rigor of Linear with the approachable clarity of Notion and the polished execution of Stripe.

The visual style is **Advanced Minimalism**. It prioritizes information density without sacrificing whitespace, ensuring that complex fiscal data (GNRE, tax codes, and compliance states) feels manageable and organized. The UI should evoke an emotional response of "calm control," reducing the cognitive load associated with tax management through a highly structured and predictable interface.

## Colors

The palette is anchored by a **Deep Corporate Blue** (`#0052FF`), representing action, precision, and trust. This is supported by a sophisticated range of "Slate" grays that provide depth and hierarchy without the harshness of pure black.

- **Primary:** Used for main CTAs, active states, and critical navigation highlights.
- **Neutrals:** A scale from `#F8FAFC` (Surface) to `#0F172A` (Text) ensures high legibility and a premium feel.
- **Semantic Colors:** Success (Green), Error (Red), and Warning (Amber) are used sparingly and with high saturation to ensure state changes are immediately recognizable against the neutral background.
- **Dark Mode:** In dark mode, surfaces shift to `#020617`, using subtle borders (`#1E293B`) instead of heavy shadows to define depth.

## Typography

The system utilizes **Inter** for all primary communication, chosen for its exceptional legibility in data-heavy SaaS applications. To emphasize the technical and fiscal nature of the platform, **JetBrains Mono** is introduced for labels, ID codes, and financial figures (monospaced alignment is crucial for comparing tax values).

**Hierarchy Rules:**
- Use negative letter-spacing on larger headings to maintain a compact, "Linear-like" feel.
- Body text should prioritize readability with generous line heights.
- Labels (JetBrains Mono) should be used for status tags, fiscal codes, and metadata.

## Layout & Spacing

This design system uses a **systematic 4px grid**. Layouts should be primarily fluid with a maximum container width of 1440px to ensure data doesn't become over-extended on ultra-wide monitors.

- **Desktop:** 12-column grid with 24px gutters. Use "Sidebar + Content" or "Top Nav + Centered Content" patterns.
- **Mobile:** 4-column grid with 16px margins.
- **Spacing Philosophy:** Use "Stack" spacing (vertical) to group related fiscal items. For example, a 16px gap between card elements and 48px between major sections.

## Elevation & Depth

Depth is conveyed through **Tonal Layering** and **Ambient Shadows**. Instead of traditional heavy shadows, this system uses low-opacity, high-diffusion shadows that make elements feel like they are floating just above the surface.

- **Level 0 (Base):** Primary background color (`#F8FAFC`).
- **Level 1 (Cards/Sidebar):** White background with a 1px border (`#E2E8F0`) and a very soft shadow (0px 2px 4px rgba(0,0,0,0.02)).
- **Level 2 (Popovers/Modals):** White background with a more pronounced ambient shadow (0px 10px 25px rgba(0,0,0,0.08)).
- **Glassmorphism:** Apply a subtle backdrop blur (8px) to sticky headers and sidebars to maintain context of the scroll position, mimicking the "Stripe Dashboard" look.

## Shapes

The shape language is **balanced and modern**. We avoid the childishness of overly rounded "pill" shapes for primary containers, opting instead for a structured 12px-16px radius that feels professional yet contemporary.

- **Components (Buttons, Inputs):** 8px (Soft).
- **Cards & Containers:** 12px (Standard).
- **Modals & Large Sections:** 16px (Large).
- **Chips/Status Tags:** Fully rounded (Pill) to distinguish them from interactive buttons.

## Components

### Buttons
- **Primary:** Deep Blue background, white text. Subtle 1px inner highlight on the top edge for a tactile feel.
- **Secondary:** Transparent background with a light slate border. 
- **Micro-interactions:** On hover, primary buttons should darken by 5%; on click, they should scale slightly (0.98x) to simulate a physical press.

### Inputs
- Clean, 1px bordered boxes (`#CBD5E1`). 
- On focus, the border changes to Primary Blue with a 3px soft blue outer glow (halo).
- Labels should always be visible above the input in `label-sm` typography.

### Cards
- Use for grouping tax documents or automation statistics. 
- Headers within cards should have a subtle bottom divider (`1px solid #F1F5F9`).
- Hover state: Cards should lift slightly with an increased shadow depth to indicate interactivity.

### Status Chips
- For GNRE states (Paid, Pending, Overdue): Use low-saturation background tints with high-saturation text (e.g., light green background with dark green text) for maximum accessibility.

### Data Tables
- Row-based layout with no vertical borders. 
- Use Zebra striping on hover only. 
- Financial columns should use `label-md` (JetBrains Mono) for perfect decimal alignment.