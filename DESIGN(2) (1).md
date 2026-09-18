# PiggyShip UI Design System Reference

## Purpose

This document defines the visual design direction for PiggyShip.

The attached reference image is used **only as visual inspiration for
visual language, spacing, typography, color relationships, component
polish, and interaction quality**.

PiggyShip must **not reproduce the reference application's layout,
features, information architecture, wording, charts, cards, or
workflows**.

The product should retain its own logistics-control-tower identity and
information architecture while adopting the reference's level of visual
refinement.

------------------------------------------------------------------------

# 1. Core Design Direction

## Design Personality

PiggyShip should feel:

-   Premium
-   Enterprise-grade
-   Operational
-   Precise
-   Calm under pressure
-   Data-focused
-   Modern
-   Trustworthy
-   Dense enough for professional users without feeling cluttered

The interface should resemble a sophisticated operations control center
rather than a generic AI SaaS dashboard.

## Visual Principle

Use the following design philosophy:

> **Quiet interface, strong hierarchy, meaningful contrast, precise
> spacing, restrained decoration.**

The UI should communicate intelligence through structure and information
hierarchy rather than excessive gradients, glowing effects, oversized
typography, or decorative AI elements.

------------------------------------------------------------------------

# 2. Reference Image Usage Rules

The reference image establishes the following visual inspiration:

-   Strong black or near-black primary workspace
-   White and very light neutral surfaces around important content
-   Muted gray secondary information
-   Restrained use of green and lime accents
-   Rounded but controlled corners
-   Thin borders
-   Generous internal spacing
-   Strong typographic hierarchy
-   Minimal iconography
-   Compact controls
-   High information density with clear grouping
-   Subtle hover and transition behavior
-   Large visual blocks surrounded by smaller supporting elements

Do not copy:

-   The exact page structure
-   The navigation arrangement
-   The reference's cards
-   The reference's charts
-   The reference's vehicle panel
-   The reference's order table
-   The reference's sales/fulfillment sections
-   The reference's wording
-   The reference's feature set
-   The exact proportions or composition

The reference is a **visual design reference only**.

------------------------------------------------------------------------

# 3. Color System

PiggyShip should use a restrained neutral palette with a strong dark
operational workspace.

## Primary Background

``` css
--background: #0B0C0E;
```

Use for:

-   Main application workspace
-   Large operational surfaces
-   Primary dashboard canvas
-   High-information areas

The background should appear almost black but not pure black.

Avoid:

``` css
#000000
```

Pure black creates excessive contrast and can make the interface feel
harsh.

------------------------------------------------------------------------

## Elevated Surface

``` css
--surface: #111318;
```

Use for:

-   Cards
-   Panels
-   Modals
-   Secondary workspace sections

------------------------------------------------------------------------

## Secondary Surface

``` css
--surface-secondary: #17191E;
```

Use for:

-   Nested cards
-   Input fields
-   Hoverable rows
-   Scenario containers
-   Secondary controls

------------------------------------------------------------------------

## Border

``` css
--border: #272A30;
```

Use thin 1px borders extensively.

Borders should provide structure without becoming visually dominant.

Recommended opacity for subtle separators:

``` css
border-color: rgba(255,255,255,0.08);
```

------------------------------------------------------------------------

# 4. Typography Colors

## Primary Text

``` css
--foreground: #F5F5F5;
```

Use for:

-   Headings
-   Important metrics
-   Shipment identifiers
-   Primary labels
-   Main decisions

## Secondary Text

``` css
--muted-foreground: #A1A1AA;
```

Use for:

-   Supporting information
-   Metadata
-   Descriptions
-   Timestamps
-   Secondary labels

## Tertiary Text

``` css
--subtle-foreground: #71717A;
```

Use sparingly for:

-   Helper text
-   Extremely low-priority metadata
-   Disabled information

Never use low-contrast text for critical operational information.

------------------------------------------------------------------------

# 5. Accent Palette

The reference image uses restrained green/lime accents. PiggyShip should
adopt the same principle without copying the exact colors.

## Primary Accent

``` css
--accent: #B8D96A;
```

Use for:

-   Positive state
-   Successful optimization
-   Recommended action
-   Active progress
-   Important system highlights

The accent should be used sparingly.

It should never cover large portions of the interface.

------------------------------------------------------------------------

## Success

``` css
--success: #8BCF72;
```

Use for:

-   Safe
-   Completed
-   Within SLA
-   Valid
-   Successfully optimized

------------------------------------------------------------------------

## Warning

``` css
--warning: #D9A441;
```

Use for:

-   SLA approaching
-   Moderate risk
-   Attention required
-   Uncertain state

------------------------------------------------------------------------

## Critical

``` css
--destructive: #E06464;
```

Use for:

-   Critical SLA risk
-   Invalid operation
-   Failure
-   Blocked action
-   Dangerous constraint violation

Red should be used as a signal, not as a decorative theme.

------------------------------------------------------------------------

## Information

``` css
--info: #8BAFC7;
```

Use for:

-   Informational state
-   Neutral system events
-   Supporting visualizations

------------------------------------------------------------------------

# 6. Color Usage Ratio

Follow an approximate visual distribution:

-   65--75% dark neutrals
-   15--25% secondary/elevated neutrals
-   5--10% accent and semantic colors

Do not create a rainbow interface.

Color should communicate meaning.

A user should be able to understand the operational state by looking at
the color hierarchy.

------------------------------------------------------------------------

# 7. Light Surfaces

Light surfaces can be used selectively for emphasis.

Preferred:

``` css
#F4F4F0
#FFFFFF
#EDEDE8
```

Use them for:

-   High-priority decision areas
-   Focused modal content
-   Selected information
-   Important interaction surfaces

Do not convert the whole application into a light dashboard.

The dominant application experience should remain a sophisticated dark
control-center interface.

------------------------------------------------------------------------

# 8. Typography

## Font Family

Preferred:

``` css
font-family:
  Inter,
  ui-sans-serif,
  system-ui,
  -apple-system,
  BlinkMacSystemFont,
  "Segoe UI",
  sans-serif;
```

Alternative premium UI fonts may be used only if they preserve excellent
readability.

Do not use:

-   Decorative fonts
-   Futuristic fonts
-   Handwritten fonts
-   Excessively geometric display fonts
-   Monospace fonts for normal interface text

------------------------------------------------------------------------

# 9. Type Scale

## Page Title

``` text
28–32px
font-weight: 600
line-height: 1.15
```

## Section Heading

``` text
18–22px
font-weight: 600
```

## Card Heading

``` text
14–16px
font-weight: 600
```

## Body

``` text
14px
font-weight: 400
line-height: 1.5
```

## Metadata

``` text
12–13px
font-weight: 400
```

## Large Metric

``` text
28–40px
font-weight: 500–600
letter-spacing: -0.03em
```

Do not make every number oversized.

Large typography should indicate hierarchy.

------------------------------------------------------------------------

# 10. Letter Spacing

Use slightly tighter tracking for major numbers and headings.

Recommended:

``` css
letter-spacing: -0.025em;
```

For body text:

``` css
letter-spacing: 0;
```

Avoid excessive letter spacing.

------------------------------------------------------------------------

# 11. Spacing System

Use a consistent 4px base grid.

Preferred values:

``` text
4px
8px
12px
16px
20px
24px
32px
40px
48px
64px
```

Most cards should use:

``` text
16–24px
```

internal padding.

Large sections may use:

``` text
24–32px
```

Never randomly mix spacing values.

------------------------------------------------------------------------

# 12. Border Radius

Use controlled rounded corners.

## Small Controls

``` css
border-radius: 8px;
```

## Cards

``` css
border-radius: 12px;
```

## Large Panels

``` css
border-radius: 16px;
```

## Pills

``` css
border-radius: 9999px;
```

Avoid extremely rounded cards.

The product should feel enterprise-grade rather than playful.

------------------------------------------------------------------------

# 13. Borders

Use 1px borders as the primary structural mechanism.

Preferred:

``` css
border: 1px solid rgba(255,255,255,0.08);
```

Hover:

``` css
border-color: rgba(255,255,255,0.15);
```

Active:

``` css
border-color: rgba(184,217,106,0.35);
```

Avoid thick borders.

Avoid glowing borders.

------------------------------------------------------------------------

# 14. Shadows

Use shadows very carefully because the dark theme should primarily rely
on contrast and borders.

Preferred:

``` css
box-shadow:
  0 12px 32px rgba(0,0,0,0.25);
```

For modals:

``` css
box-shadow:
  0 24px 80px rgba(0,0,0,0.45);
```

Avoid:

-   Strong neon glow
-   Colored shadows everywhere
-   Excessive blur
-   Large floating SaaS-style cards

------------------------------------------------------------------------

# 15. Surface Hierarchy

Create visual depth using:

``` text
Background
    ↓
Surface
    ↓
Elevated Surface
    ↓
Focused Surface
    ↓
Active Surface
```

Each layer should differ only slightly.

Example:

``` text
#0B0C0E
#111318
#17191E
#1D2026
```

The interface should feel layered rather than flat.

------------------------------------------------------------------------

# 16. Navigation Design

Navigation should be compact and visually quiet.

Use:

-   Small icon
-   Short label
-   Clear active state
-   Consistent spacing
-   Thin borders
-   Subtle background transition

Active navigation:

``` text
Dark background
High-contrast text
Subtle border
Very small accent indication
```

Do not use oversized sidebar items.

Do not use colorful navigation icons.

------------------------------------------------------------------------

# 17. Iconography

Use `lucide-react`.

Icons should be:

-   Simple
-   Monoline
-   Consistent
-   Approximately 16--20px
-   Visually secondary to text

Recommended sizes:

``` text
14px: compact metadata
16px: normal controls
18px: navigation
20px: important actions
24px: major empty-state or system indicators
```

Icons should not dominate the interface.

Never use emoji as interface icons.

Do not use text characters as fake icons.

------------------------------------------------------------------------

# 18. Buttons

Buttons should feel precise and tactile.

## Primary Button

Characteristics:

-   Strong contrast
-   Compact height
-   Medium weight text
-   8px radius
-   Minimal shadow

Example visual direction:

``` text
Height: 36–40px
Padding: 12–16px horizontal
Radius: 8px
Font: 13–14px
```

## Secondary Button

Use:

-   Transparent or surface background
-   Thin border
-   Muted text

## Ghost Button

Use only for low-priority actions.

## Destructive Button

Use semantic red only when the action is genuinely destructive or
dangerous.

Avoid oversized pill buttons.

------------------------------------------------------------------------

# 19. Button Interaction

### Hover

-   Background becomes slightly lighter
-   Border becomes slightly more visible
-   Icon shifts minimally if appropriate

### Active

-   Slightly darker surface
-   Tiny scale reduction if appropriate

``` css
transform: scale(0.98);
```

### Focus

Use a visible but subtle focus ring.

``` css
box-shadow: 0 0 0 2px rgba(184,217,106,0.25);
```

### Disabled

Reduce opacity.

Do not remove the element's structure.

------------------------------------------------------------------------

# 20. Hover Philosophy

Hover effects should be:

-   Fast
-   Subtle
-   Functional

Recommended duration:

``` css
transition: 150ms ease;
```

For larger transitions:

``` css
transition: 200ms ease;
```

Avoid:

-   Large movement
-   Excessive scaling
-   Neon glow
-   Rotating icons unnecessarily
-   Long animations

Hover should communicate:

> "This element is interactive."

Not:

> "Look at this animation."

------------------------------------------------------------------------

# 21. Card Design

Cards should not look like isolated floating boxes.

Use cards primarily to create information hierarchy.

A premium card should contain:

``` text
Header
Supporting context
Primary information
Optional action
```

Recommended:

``` text
Background: #111318
Border: 1px solid rgba(255,255,255,0.08)
Radius: 12px
Padding: 16–20px
```

Cards should align to a consistent grid.

------------------------------------------------------------------------

# 22. Tables

Tables should feel like enterprise operational data surfaces.

Use:

-   Compact rows
-   Strong column alignment
-   Muted headers
-   Clear status indicators
-   Minimal borders
-   Row hover

Avoid heavy boxed cells.

Preferred row height:

``` text
48–60px
```

Header:

``` text
11–12px
font-weight: 500
text-transform: uppercase only when useful
letter-spacing: 0.04em
```

------------------------------------------------------------------------

# 23. Status Indicators

Use small semantic indicators.

Preferred pattern:

``` text
● Status
```

The dot should be small.

Do not use large colored blocks unless the state is extremely important.

Examples:

``` text
Success
Warning
Critical
Neutral
```

The status text should remain readable even without color.

Color must never be the only indicator.

------------------------------------------------------------------------

# 24. Progress Indicators

Progress bars should be thin and precise.

Recommended:

``` text
Height: 4–6px
Radius: 9999px
```

Background:

``` css
#272A30
```

Fill uses the appropriate semantic color.

Avoid large dashboard-style progress gauges unless they communicate
genuinely important information.

------------------------------------------------------------------------

# 25. Data Visualization Style

Charts should follow the same restrained design language.

Use:

-   Dark backgrounds
-   Thin grid lines
-   Muted axes
-   One dominant data color
-   Minimal labels
-   Small tooltips

Avoid:

-   3D charts
-   Heavy gradients
-   Decorative chart backgrounds
-   Excessive colors
-   Thick grid lines

Charts should look analytical rather than decorative.

------------------------------------------------------------------------

# 26. Modal Design

Modals should feel like focused operational workspaces.

Recommended:

``` text
Width:
720–1100px depending on complexity

Background:
#111318

Border:
1px solid rgba(255,255,255,0.10)

Radius:
16px

Shadow:
Large soft shadow
```

Use a slightly darker backdrop:

``` css
background: rgba(0,0,0,0.65);
backdrop-filter: blur(6px);
```

The modal should visually separate itself from the underlying dashboard
without appearing disconnected.

------------------------------------------------------------------------

# 27. Information Hierarchy

Every screen should have a clear hierarchy:

### Level 1

What requires attention?

### Level 2

What is happening?

### Level 3

Why is it happening?

### Level 4

What supporting information is relevant?

### Level 5

What action can the operator take?

Do not give every piece of information equal visual weight.

------------------------------------------------------------------------

# 28. Dense Information Without Clutter

PiggyShip is an operational product, so information density is
necessary.

Use:

-   Grouping
-   Whitespace
-   Alignment
-   Typography
-   Borders
-   Muted colors

to organize density.

Do not solve density by making everything tiny.

Do not hide important information behind excessive tabs.

------------------------------------------------------------------------

# 29. Visual Focus

Each screen should have one primary visual focus.

For example:

``` text
Primary:
Current operational issue

Secondary:
Supporting metrics

Tertiary:
Historical/contextual information

Actions:
Clearly separated
```

The user should understand the screen's purpose within approximately two
seconds.

------------------------------------------------------------------------

# 30. Micro-Interactions

Use subtle micro-interactions for:

-   Opening panels
-   Updating metrics
-   Changing filters
-   Selecting rows
-   Confirming actions
-   Updating status
-   Loading data

Recommended animation duration:

``` text
150–250ms
```

For larger transitions:

``` text
250–400ms
```

Never animate every element simultaneously.

------------------------------------------------------------------------

# 31. Loading States

Use skeleton loading rather than blank screens.

Skeletons should:

-   Match the actual content dimensions
-   Use subtle neutral contrast
-   Avoid bright shimmer effects

Preferred:

``` css
background: #17191E;
```

with a very subtle animated highlight.

------------------------------------------------------------------------

# 32. Empty States

Empty states should be calm and informative.

Structure:

``` text
Small icon
Title
One-line explanation
Optional action
```

Avoid oversized illustrations.

Avoid decorative graphics that distract from the operational purpose.

------------------------------------------------------------------------

# 33. Alerts and Notifications

Notifications should feel like operational signals.

Use:

-   Small semantic icon
-   Strong title
-   Short explanation
-   Optional action
-   Dismiss control

Avoid huge popups covering the workspace.

Notifications should enter and leave smoothly.

------------------------------------------------------------------------

# 34. Forms and Inputs

Inputs should use:

``` text
Height: 36–40px
Radius: 8px
Background: #111318 or #17191E
Border: #272A30
```

Placeholder:

``` text
#71717A
```

Focused:

``` text
Border becomes slightly brighter
Subtle accent focus ring
```

Avoid bright white input backgrounds inside the dark workspace unless
deliberately used for a special focused surface.

------------------------------------------------------------------------

# 35. Search

Search should look like an integrated command-center control.

Use:

-   Small search icon
-   Muted placeholder
-   Compact height
-   Thin border
-   Strong focus state

Do not make search visually dominant unless it is the primary
interaction on that screen.

------------------------------------------------------------------------

# 36. Filters

Filters should use compact controls.

Preferred:

``` text
Filter
Sort
Date
Status
Risk
Location
```

Each control should use a consistent height and border treatment.

Avoid oversized filter chips.

------------------------------------------------------------------------

# 37. Background Treatment

The background should remain mostly flat.

Optional subtle treatment:

``` css
background:
  radial-gradient(
    circle at top right,
    rgba(184,217,106,0.035),
    transparent 35%
  ),
  #0B0C0E;
```

Use this extremely subtly.

The interface should not look like a futuristic gaming dashboard.

------------------------------------------------------------------------

# 38. Grid System

Use a consistent responsive grid.

Desktop:

``` text
12-column conceptual grid
```

Recommended gaps:

``` text
16–24px
```

Panels should align vertically and horizontally.

Avoid arbitrary widths.

------------------------------------------------------------------------

# 39. Responsive Behavior

The design should gracefully adapt to:

-   Desktop
-   Laptop
-   Tablet

Prioritize desktop because the application is an operational control
interface.

On smaller screens:

-   Collapse secondary information
-   Stack panels
-   Preserve critical status
-   Keep primary actions accessible
-   Avoid horizontal overflow

------------------------------------------------------------------------

# 40. Premium Detail Principles

Use small details to create polish:

-   Consistent 1px borders
-   Perfect icon alignment
-   Stable spacing
-   Consistent corner radius
-   Carefully muted secondary text
-   Clear focus states
-   Subtle hover transitions
-   Strong baseline alignment
-   Consistent number formatting
-   Consistent status semantics

The premium feel should come from **precision**, not decoration.

------------------------------------------------------------------------

# 41. Things to Avoid

Do not use:

-   Emojis
-   Emoji-style icons
-   Excessive gradients
-   Neon colors
-   Glassmorphism everywhere
-   Huge shadows
-   Excessive blur
-   Excessive rounded corners
-   Giant text
-   Random animations
-   Excessive card nesting
-   Rainbow charts
-   Generic AI sparkle graphics
-   "AI" labels everywhere
-   Fake futuristic effects
-   Decorative 3D elements
-   Excessive badges
-   Excessive pills
-   Inconsistent icon styles

The interface must never feel like a template generated by an AI design
tool.

------------------------------------------------------------------------

# 42. Anti-Pattern: Generic AI SaaS

Avoid visual patterns such as:

``` text
Purple gradient
+
White cards
+
AI sparkle icon
+
Huge heading
+
Rounded pill buttons
+
Glassmorphism
+
Floating blobs
```

This is not the desired visual identity.

PiggyShip should instead feel like:

``` text
Dark operational workspace
+
Precise data hierarchy
+
Muted neutrals
+
Restrained lime/green accents
+
Enterprise typography
+
Thin borders
+
Compact controls
+
Purposeful motion
```

------------------------------------------------------------------------

# 43. Visual Language for Intelligence

AI should be communicated through the **quality of the interface**, not
decoration.

When the system produces an intelligent recommendation, emphasize:

-   Evidence
-   Confidence
-   Consequences
-   Reasoning
-   Impact
-   Alternatives
-   Decision state

Do not use animated AI symbols to indicate intelligence.

------------------------------------------------------------------------

# 44. Visual Language for Risk

Risk should use a semantic hierarchy.

### Low Risk

Muted green indicator.

### Moderate Risk

Amber indicator.

### High Risk

Red indicator.

### Critical

Red indicator plus stronger contrast and clear text.

Avoid flashing red UI.

Operational systems should remain calm even during critical events.

------------------------------------------------------------------------

# 45. Visual Language for Recommendations

Recommended actions should have a clear but restrained visual
distinction.

Use:

-   Slight accent border
-   Subtle accent background
-   Small recommendation label
-   Strong action hierarchy

Avoid:

-   Large glowing borders
-   Excessive green
-   Giant "RECOMMENDED" banners

The recommendation should be obvious without dominating the entire
interface.

------------------------------------------------------------------------

# 46. Motion Design

Motion should communicate state changes.

### Enter

``` text
Opacity: 0 → 1
Translate Y: 4px → 0
Duration: 180ms
```

### Exit

``` text
Opacity: 1 → 0
Duration: 120ms
```

### Panel expansion

``` text
180–250ms
ease-out
```

### Data update

Use subtle number transitions when useful.

Avoid continuous motion unless it represents live operational data.

------------------------------------------------------------------------

# 47. Hover Effects for Major Components

## Cards

On hover:

``` text
Border slightly brightens
Background slightly changes
```

No large lift.

## Table Rows

On hover:

``` text
Background becomes #17191E
```

## Buttons

On hover:

``` text
Slight brightness increase
Border becomes clearer
```

## Navigation

On hover:

``` text
Muted surface appears
```

All hover effects should remain understated.

------------------------------------------------------------------------

# 48. Accessibility

Maintain:

-   Strong text contrast
-   Visible keyboard focus
-   Semantic HTML
-   Accessible labels
-   Non-color status indicators
-   Reduced-motion support
-   Sufficient click targets

Provide a reduced-motion mode for users who prefer it.

------------------------------------------------------------------------

# 49. Design Tokens

Use centralized CSS variables.

Recommended foundation:

``` css
:root {
  --background: #0B0C0E;
  --foreground: #F5F5F5;

  --surface: #111318;
  --surface-secondary: #17191E;
  --surface-tertiary: #1D2026;

  --border: #272A30;

  --muted-foreground: #A1A1AA;
  --subtle-foreground: #71717A;

  --accent: #B8D96A;

  --success: #8BCF72;
  --warning: #D9A441;
  --destructive: #E06464;
  --info: #8BAFC7;

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;

  --transition-fast: 150ms;
  --transition-normal: 200ms;
}
```

All components should reference these variables rather than introducing
random colors.

------------------------------------------------------------------------

# 50. Design Quality Checklist

Before considering a screen complete, verify:

-   Is the hierarchy immediately understandable?
-   Are important operational states obvious?
-   Are colors semantic?
-   Are borders consistent?
-   Are corner radii consistent?
-   Are icons from one icon system?
-   Is typography consistent?
-   Are spacing values based on the grid?
-   Are hover states subtle?
-   Are focus states visible?
-   Is the interface too colorful?
-   Is there unnecessary decoration?
-   Does anything resemble a generic AI dashboard?
-   Does the interface feel like a professional logistics control
    center?
-   Does the visual design support the information rather than compete
    with it?

------------------------------------------------------------------------

# 51. Final Visual Target

The desired result is:

**Premium enterprise control center**

with:

-   Dark near-black workspace
-   Sophisticated neutral surfaces
-   Restrained lime/green accent
-   Strong white typography
-   Muted metadata
-   Thin borders
-   Controlled rounded corners
-   Precise iconography
-   Compact professional controls
-   Strong alignment
-   High information density
-   Subtle motion
-   Clear operational states
-   Excellent whitespace discipline

The reference image is the **visual quality benchmark**, not the product
blueprint.

PiggyShip must remain visually distinct and should develop its own
information architecture, components, and interaction patterns around
its logistics domain.

The final interface should communicate:

> **Precision, control, intelligence, and operational confidence.**
