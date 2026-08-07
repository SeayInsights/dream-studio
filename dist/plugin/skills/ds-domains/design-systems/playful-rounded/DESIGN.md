# Playful Rounded Design System

**Inspired by:** Airbnb, Duolingo, Figma  
**Best for:** Consumer apps, education platforms, social features, gamified experiences  
**Personality:** Friendly, approachable, warm, playful

---

## 1. Color Palette

### Primary Colors
```css
--primary-coral: #FF385C;        /* Airbnb signature coral */
--primary-green: #58CC02;        /* Duolingo success green */
--primary-purple: #6E56CF;       /* Figma collaborative purple */
--primary-blue: #00A5FF;         /* Friendly sky blue */
```

### Secondary Colors
```css
--secondary-peach: #FF6B6B;      /* Warm accent */
--secondary-mint: #2DD4BF;       /* Fresh highlight */
--secondary-amber: #FFBE3D;      /* Sunshine yellow */
--secondary-lavender: #A78BFA;   /* Soft purple */
```

### Neutrals
```css
--neutral-900: #222222;          /* Almost black text */
--neutral-700: #484848;          /* Secondary text */
--neutral-500: #717171;          /* Muted text */
--neutral-300: #DDDDDD;          /* Borders */
--neutral-100: #F7F7F7;          /* Light backgrounds */
--neutral-white: #FFFFFF;        /* Pure white */
```

### Semantic Colors
```css
--success: #58CC02;              /* Achievement green */
--warning: #FFC800;              /* Gentle warning */
--error: #FF4B4B;                /* Friendly error */
--info: #00A5FF;                 /* Helpful info */
```

### Gradients
```css
--gradient-warm: linear-gradient(135deg, #FF385C 0%, #FF6B6B 100%);
--gradient-achievement: linear-gradient(135deg, #58CC02 0%, #2DD4BF 100%);
--gradient-magical: linear-gradient(135deg, #6E56CF 0%, #A78BFA 100%);
--gradient-sunrise: linear-gradient(135deg, #FFBE3D 0%, #FF6B6B 100%);
```

---

## 2. Typography

### Font Families
```css
--font-primary: 'Circular', 'Inter', -apple-system, sans-serif;  /* Airbnb-style */
--font-heading: 'Poppins', 'Circular', sans-serif;               /* Rounded, friendly */
--font-mono: 'JetBrains Mono', 'Courier New', monospace;         /* Technical */
```

### Type Scale
```css
--text-xs: 0.75rem;      /* 12px - Labels, captions */
--text-sm: 0.875rem;     /* 14px - Secondary text */
--text-base: 1rem;       /* 16px - Body text */
--text-lg: 1.125rem;     /* 18px - Emphasis */
--text-xl: 1.25rem;      /* 20px - Small headings */
--text-2xl: 1.5rem;      /* 24px - Subheadings */
--text-3xl: 1.875rem;    /* 30px - Page titles */
--text-4xl: 2.25rem;     /* 36px - Hero headings */
--text-5xl: 3rem;        /* 48px - Marketing hero */
```

### Font Weights
```css
--weight-normal: 400;
--weight-medium: 500;
--weight-semibold: 600;
--weight-bold: 700;
--weight-extrabold: 800;
```

### Line Heights
```css
--leading-tight: 1.25;   /* Headings */
--leading-snug: 1.375;   /* Subheadings */
--leading-normal: 1.5;   /* Body text */
--leading-relaxed: 1.625; /* Comfortable reading */
```

---

## 3. Spacing System

### Base Scale (4px grid)
```css
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-5: 1.25rem;   /* 20px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-10: 2.5rem;   /* 40px */
--space-12: 3rem;     /* 48px */
--space-16: 4rem;     /* 64px */
--space-20: 5rem;     /* 80px */
--space-24: 6rem;     /* 96px */
```

### Component Spacing
```css
--spacing-component-xs: var(--space-2);   /* Tight elements */
--spacing-component-sm: var(--space-3);   /* Compact cards */
--spacing-component-md: var(--space-4);   /* Standard padding */
--spacing-component-lg: var(--space-6);   /* Comfortable cards */
--spacing-component-xl: var(--space-8);   /* Hero sections */
```

---

## 4. Border Radius

### Playful Rounded Scale
```css
--radius-sm: 8px;      /* Buttons, inputs */
--radius-md: 12px;     /* Cards, panels */
--radius-lg: 16px;     /* Feature cards */
--radius-xl: 24px;     /* Hero cards */
--radius-2xl: 32px;    /* Modal containers */
--radius-full: 9999px; /* Pills, avatars */
```

### Component-Specific
```css
--radius-button: var(--radius-sm);
--radius-card: var(--radius-lg);
--radius-modal: var(--radius-2xl);
--radius-avatar: var(--radius-full);
--radius-badge: var(--radius-full);
```

---

## 5. Shadows & Elevation

### Shadow Scale
```css
--shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.04);
--shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04);
--shadow-md: 0 4px 6px rgba(0, 0, 0, 0.04), 0 2px 4px rgba(0, 0, 0, 0.03);
--shadow-lg: 0 10px 15px rgba(0, 0, 0, 0.05), 0 4px 6px rgba(0, 0, 0, 0.04);
--shadow-xl: 0 20px 25px rgba(0, 0, 0, 0.06), 0 10px 10px rgba(0, 0, 0, 0.03);
--shadow-2xl: 0 25px 50px rgba(0, 0, 0, 0.08);
```

### Colored Shadows (Playful Touch)
```css
--shadow-coral: 0 8px 20px rgba(255, 56, 92, 0.15);
--shadow-green: 0 8px 20px rgba(88, 204, 2, 0.15);
--shadow-purple: 0 8px 20px rgba(110, 86, 207, 0.15);
--shadow-blue: 0 8px 20px rgba(0, 165, 255, 0.15);
```

### Elevation Layers
```css
--elevation-base: var(--shadow-sm);      /* Cards */
--elevation-raised: var(--shadow-md);    /* Hover states */
--elevation-floating: var(--shadow-lg);  /* Dropdowns */
--elevation-modal: var(--shadow-2xl);    /* Modals */
```

---

## 6. Animation & Motion

### Timing Functions
```css
--ease-bounce: cubic-bezier(0.68, -0.55, 0.265, 1.55);     /* Playful bounce */
--ease-smooth: cubic-bezier(0.4, 0.0, 0.2, 1);             /* Material smooth */
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);          /* Spring effect */
--ease-gentle: cubic-bezier(0.25, 0.46, 0.45, 0.94);       /* Gentle ease */
```

### Durations
```css
--duration-instant: 100ms;   /* Immediate feedback */
--duration-fast: 200ms;      /* Quick transitions */
--duration-normal: 300ms;    /* Standard animations */
--duration-slow: 400ms;      /* Deliberate motion */
--duration-slower: 600ms;    /* Emphasized changes */
```

### Animation Presets
```css
/* Button press */
--anim-button-press: transform var(--duration-fast) var(--ease-smooth);

/* Card hover */
--anim-card-hover: all var(--duration-normal) var(--ease-gentle);

/* Modal entrance */
--anim-modal-in: all var(--duration-normal) var(--ease-spring);

/* Success celebration */
--anim-success: transform var(--duration-slow) var(--ease-bounce);
```

### Microinteractions
```css
/* Playful scale on hover */
.interactive:hover {
  transform: scale(1.02);
  transition: var(--anim-card-hover);
}

/* Bounce on click */
.button:active {
  transform: scale(0.96);
  transition: var(--duration-instant);
}

/* Subtle wiggle */
@keyframes wiggle {
  0%, 100% { transform: rotate(0deg); }
  25% { transform: rotate(-2deg); }
  75% { transform: rotate(2deg); }
}
```

---

## 7. Component Patterns

### Buttons

#### Primary Button
```css
.btn-primary {
  background: var(--primary-coral);
  color: var(--neutral-white);
  padding: var(--space-3) var(--space-6);
  border-radius: var(--radius-button);
  font-weight: var(--weight-semibold);
  box-shadow: var(--shadow-sm);
  transition: var(--anim-button-press);
}

.btn-primary:hover {
  background: #E0203D;
  box-shadow: var(--shadow-md);
  transform: translateY(-1px);
}

.btn-primary:active {
  transform: translateY(0) scale(0.98);
}
```

#### Gamified Button (Duolingo-style)
```css
.btn-gamified {
  background: var(--primary-green);
  color: var(--neutral-white);
  padding: var(--space-4) var(--space-8);
  border-radius: var(--radius-md);
  font-weight: var(--weight-bold);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  box-shadow: 0 4px 0 #46A302, var(--shadow-md);
  transition: var(--duration-fast);
}

.btn-gamified:active {
  transform: translateY(3px);
  box-shadow: 0 1px 0 #46A302, var(--shadow-xs);
}
```

### Cards

#### Feature Card
```css
.card-feature {
  background: var(--neutral-white);
  border-radius: var(--radius-lg);
  padding: var(--space-6);
  box-shadow: var(--elevation-base);
  transition: var(--anim-card-hover);
  border: 1px solid var(--neutral-100);
}

.card-feature:hover {
  box-shadow: var(--elevation-raised);
  transform: translateY(-4px);
  border-color: var(--neutral-300);
}
```

#### Achievement Card
```css
.card-achievement {
  background: var(--gradient-achievement);
  color: var(--neutral-white);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  box-shadow: var(--shadow-green);
  position: relative;
  overflow: hidden;
}

.card-achievement::before {
  content: '🎉';
  position: absolute;
  top: var(--space-4);
  right: var(--space-4);
  font-size: var(--text-4xl);
  opacity: 0.3;
}
```

### Forms

#### Input Field
```css
.input-field {
  padding: var(--space-3) var(--space-4);
  border: 2px solid var(--neutral-300);
  border-radius: var(--radius-sm);
  font-size: var(--text-base);
  transition: var(--duration-fast);
  background: var(--neutral-white);
}

.input-field:focus {
  outline: none;
  border-color: var(--primary-purple);
  box-shadow: 0 0 0 3px rgba(110, 86, 207, 0.1);
}

.input-field::placeholder {
  color: var(--neutral-500);
}
```

### Progress Indicators

#### Progress Bar (Duolingo-style)
```css
.progress-bar {
  height: 12px;
  background: var(--neutral-200);
  border-radius: var(--radius-full);
  overflow: hidden;
  position: relative;
}

.progress-bar-fill {
  height: 100%;
  background: var(--gradient-achievement);
  border-radius: var(--radius-full);
  transition: width var(--duration-slow) var(--ease-smooth);
  box-shadow: inset 0 2px 4px rgba(255, 255, 255, 0.3);
}
```

### Badges & Pills

#### Badge
```css
.badge {
  display: inline-flex;
  align-items: center;
  padding: var(--space-1) var(--space-3);
  background: var(--primary-coral);
  color: var(--neutral-white);
  border-radius: var(--radius-badge);
  font-size: var(--text-xs);
  font-weight: var(--weight-semibold);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
```

---

## 8. Layout & Grid

### Container Widths
```css
--container-sm: 640px;   /* Mobile-first content */
--container-md: 768px;   /* Tablets */
--container-lg: 1024px;  /* Desktop */
--container-xl: 1280px;  /* Wide layouts */
--container-2xl: 1536px; /* Full experience */
```

### Grid System
```css
.grid-playful {
  display: grid;
  gap: var(--space-6);
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
}

.grid-cards {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}
```

### Spacing Rhythm
```css
--rhythm-section: var(--space-16);   /* Between sections */
--rhythm-content: var(--space-8);    /* Between content blocks */
--rhythm-element: var(--space-4);    /* Between related elements */
```

---

## 9. Accessibility

### Focus Styles
```css
*:focus-visible {
  outline: 3px solid var(--primary-purple);
  outline-offset: 2px;
  border-radius: var(--radius-sm);
}

.btn:focus-visible {
  box-shadow: 0 0 0 4px rgba(110, 86, 207, 0.3);
}
```

### Color Contrast
- All text meets WCAG AA standards (4.5:1 for body, 3:1 for large text)
- Primary coral (#FF385C) on white: 4.85:1
- Primary green (#58CC02) on white: 2.94:1 (use darker shade for text)
- Neutral-900 (#222222) on white: 16.58:1

### Reduced Motion
```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### Screen Reader Support
```css
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border-width: 0;
}
```

### Interactive Element Sizes
- Minimum touch target: 44×44px (WCAG 2.5.5)
- Recommended button padding: 12px 24px minimum
- Icon buttons: 48×48px minimum

---

## Usage Examples

### Hero Section
```html
<section class="hero-playful">
  <div class="container">
    <h1 class="hero-title">Welcome home</h1>
    <p class="hero-subtitle">Find your next adventure</p>
    <button class="btn-primary btn-lg">Get started</button>
  </div>
</section>

<style>
.hero-playful {
  padding: var(--space-20) var(--space-6);
  background: var(--gradient-warm);
  color: var(--neutral-white);
  border-radius: 0 0 var(--radius-2xl) var(--radius-2xl);
}

.hero-title {
  font-size: var(--text-5xl);
  font-weight: var(--weight-bold);
  line-height: var(--leading-tight);
  margin-bottom: var(--space-4);
}
</style>
```

### Achievement Toast
```html
<div class="toast-achievement">
  <span class="toast-icon">🎉</span>
  <div class="toast-content">
    <h4>Streak milestone!</h4>
    <p>7 days in a row</p>
  </div>
</div>

<style>
.toast-achievement {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-4) var(--space-6);
  background: var(--neutral-white);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  border-left: 4px solid var(--primary-green);
  animation: slideInRight var(--duration-normal) var(--ease-spring);
}
</style>
```

---

## Design Principles

1. **Friendly First** - Every interaction should feel warm and welcoming
2. **Playful Delight** - Add subtle animations and personality where appropriate
3. **Clear Hierarchy** - Use size, color, and spacing to guide users naturally
4. **Celebrate Success** - Make achievements and progress feel rewarding
5. **Reduce Friction** - Keep interactions simple and intuitive
6. **Mobile-Friendly** - Design for touch and small screens first
7. **Accessible Always** - Ensure everyone can use your interface comfortably

---

**When to Use This System:**
- Consumer-facing apps and services
- Education and learning platforms
- Social and community features
- Gamified experiences
- Onboarding flows
- Marketing landing pages

**When to Avoid:**
- Enterprise dashboards (use minimal-modern instead)
- Financial applications requiring seriousness
- Medical or legal interfaces
- Developer tools (use brutal-technical instead)
