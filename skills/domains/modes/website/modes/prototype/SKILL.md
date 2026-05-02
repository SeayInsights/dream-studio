---
ds:
  pack: domains
  mode: website/prototype
  mode_type: build
  inputs: [direction_lock, screen_inventory, navigation_map]
  outputs: [html_prototype]
  capabilities_required: [Read, Write]
  model_preference: sonnet
  estimated_duration: 20-45min
---

# Prototype — Interactive Device Prototypes

Builds single-file HTML interactive prototypes in device frames, driven by a JS state machine.

## Step 1: Device Selection

Ask which device frame to use (or infer from context):

| Device | Frame template | Use when |
|--------|---------------|----------|
| iOS (iPhone 15 Pro) | `assets/ios-frame.html` | iOS app, mobile-first |
| Android (Pixel 8) | `assets/android-frame.html` | Android app, cross-platform |
| Browser (Chrome) | `assets/browser-frame.html` | Web app, desktop SaaS |

If the user doesn't specify, ask before proceeding.

## Step 2: Screen Inventory

List every screen the prototype needs. For each screen, define:
- **Name** — e.g., Login, Dashboard, Profile
- **Key elements** — buttons, inputs, cards, nav bars
- **Navigation targets** — which screen does each tap/click lead to?

Cap at 5 screens. If the user describes more, split into multiple prototypes and say so.

## Step 3: State Machine Definition

Map screens as states and interactions as transitions:

```
Login       → [tap "Sign In"]   → Dashboard
Dashboard   → [tap "Profile"]   → Profile
Profile     → [tap "Back"]      → Dashboard
Dashboard   → [tap "Settings"]  → Settings
Settings    → [tap "Back"]      → Dashboard
```

Identify the pattern before building:
- **Linear** — A → B → C (onboarding, checkout)
- **Hub-and-spoke** — Home → [multiple] → Home (dashboard apps)
- **Tab bar** — parallel top-level screens with persistent tab nav
- **Modal** — overlay screens that return to previous state on dismiss

## Step 4: Build HTML

Single-file HTML. Structure:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>[App Name] Prototype</title>
  <link href="[Google Fonts URL]" rel="stylesheet">
  <style>
    /* Direction lock tokens */
    :root { /* palette, fonts, spacing from direction lock */ }

    /* Device frame */
    .device-frame { /* from assets template */ }

    /* Screen management */
    .screen { display: none; width: 100%; height: 100%; }
    .screen.active { display: flex; flex-direction: column; }

    /* Transition animation */
    @keyframes slideIn  { from { transform: translateX(100%); } to { transform: translateX(0); } }
    @keyframes fadeIn   { from { opacity: 0; } to { opacity: 1; } }
    .screen.active { animation: slideIn 250ms ease-out; }

    /* Touch targets */
    [onclick] { min-width: 44px; min-height: 44px; cursor: pointer; }

    /* Safe area insets (iOS notch / Dynamic Island) */
    .safe-top    { padding-top: env(safe-area-inset-top, 44px); }
    .safe-bottom { padding-bottom: env(safe-area-inset-bottom, 34px); }

    @media (prefers-reduced-motion: reduce) { .screen.active { animation: none; } }
  </style>
</head>
<body>
  <!-- Device frame wraps all screens -->
  <div class="device-frame">
    <div class="screen-area">

      <div class="screen active" data-screen="login">
        <!-- Login screen content -->
      </div>

      <div class="screen" data-screen="dashboard">
        <!-- Dashboard screen content -->
      </div>

    </div>
  </div>

  <script>
    function navigateTo(screenId) {
      document.querySelectorAll('.screen').forEach(s => s.classList.remove('active'));
      const next = document.querySelector(`[data-screen="${screenId}"]`);
      if (next) next.classList.add('active');
    }
  </script>
</body>
</html>
```

Wire interactions with inline handlers: `onclick="navigateTo('dashboard')"`.

Apply direction lock palette and fonts to all screens. No ad-hoc color or font values.

## Step 5: Anti-Slop Lint

```bash
py scripts/lint-artifact.py <output.html>
```

Fix all violations before delivering.

## Mobile-Specific Guidelines

- Touch targets: minimum 44×44px (Apple HIG)
- System font fallback: San Francisco (iOS), Roboto (Android) — override with direction lock fonts
- Status bar content must be real: use an accurate time (e.g., 9:41), full signal, full battery
- Safe area insets required for notch / Dynamic Island
- Bottom nav bar for 3–5 primary actions
- No hover-dependent interactions — mobile has no hover

## Anti-patterns

- Prototype without device frame (loses platform context)
- Screens with no path back (dead ends)
- Hover-only interactions on mobile prototypes
- Missing loading / empty / error states for data-driven screens
- Touch targets under 44px
- More than 5 screens in a single file — split into multiple prototypes
- Inline styles overriding direction lock tokens
- External JS dependencies — state machine must be self-contained
