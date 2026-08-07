# Tech-Minimal Design System

A minimal, clean design system for tech/SaaS products, BI dashboards, and developer tools. Inspired by Stripe, Linear, and Vercel.

## 1. Visual Theme

**Core Principles:**
- **Minimal & Clean**: Strip away unnecessary elements. Every pixel serves a purpose.
- **Data-First**: Prioritize information density without sacrificing clarity.
- **High Contrast**: Ensure accessibility and readability with strong contrast ratios.
- **Purposeful Motion**: Subtle, fast transitions that enhance (not distract from) the experience.
- **Monochrome Foundation**: Gray-based with selective color for emphasis.

**Aesthetic Identity:**
- Sharp edges over rounded corners (2-4px max border radius)
- Generous white space around content blocks
- Subtle borders (1px) over heavy shadows
- Typography as a design element
- Grid-based precision alignment

---

## 2. Color Palette

### Primary Colors
```
Brand Primary:    #0070F3  (Vercel blue - actions, links, primary CTAs)
Brand Dark:       #0051CC  (Hover states, pressed states)
Brand Light:      #E6F3FF  (Backgrounds, subtle highlights)
```

### Neutrals (Monochrome Foundation)
```
Gray 0 (White):   #FFFFFF  (Backgrounds, cards)
Gray 1:           #FAFAFA  (Subtle backgrounds, hover states)
Gray 2:           #F4F4F5  (Borders, dividers - light mode)
Gray 3:           #E4E4E7  (Disabled backgrounds)
Gray 4:           #D4D4D8  (Border emphasis)
Gray 5:           #A1A1AA  (Placeholder text, secondary info)
Gray 6:           #71717A  (Tertiary text, labels)
Gray 7:           #52525B  (Secondary text)
Gray 8:           #3F3F46  (Primary text - light backgrounds)
Gray 9:           #27272A  (Headings, high emphasis)
Gray 10 (Black):  #18181B  (Max contrast text)
```

### Semantic Colors
```
Success:          #10B981  (Emerald - confirmations, positive states)
Success Light:    #D1FAE5  (Success backgrounds)
Warning:          #F59E0B  (Amber - warnings, alerts)
Warning Light:    #FEF3C7  (Warning backgrounds)
Error:            #EF4444  (Red - errors, destructive actions)
Error Light:      #FEE2E2  (Error backgrounds)
Info:             #3B82F6  (Blue - informational messages)
Info Light:       #DBEAFE  (Info backgrounds)
```

### Data Visualization (BI Dashboards)
```
Chart 1:          #0070F3  (Primary data series)
Chart 2:          #7C3AED  (Violet)
Chart 3:          #10B981  (Emerald)
Chart 4:          #F59E0B  (Amber)
Chart 5:          #EC4899  (Pink)
Chart 6:          #06B6D4  (Cyan)
Chart 7:          #8B5CF6  (Purple)
Chart 8:          #14B8A6  (Teal)
```

---

## 3. Typography

### Font Families
```css
/* Primary - UI Text */
--font-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;

/* Monospace - Code, Data, Metrics */
--font-mono: 'JetBrains Mono', 'SF Mono', 'Consolas', monospace;

/* Optional - Display/Marketing */
--font-display: 'Cabinet Grotesk', 'Inter', sans-serif;
```

### Type Scale
```css
/* Font Sizes */
--text-xs:    0.75rem;   /* 12px - labels, captions */
--text-sm:    0.875rem;  /* 14px - secondary text, table data */
--text-base:  1rem;      /* 16px - body text */
--text-lg:    1.125rem;  /* 18px - emphasized body */
--text-xl:    1.25rem;   /* 20px - section headers */
--text-2xl:   1.5rem;    /* 24px - page titles */
--text-3xl:   1.875rem;  /* 30px - hero headings */
--text-4xl:   2.25rem;   /* 36px - display text */

/* Line Heights */
--leading-tight:  1.25;   /* Headings */
--leading-snug:   1.375;  /* Subheadings */
--leading-normal: 1.5;    /* Body text */
--leading-relaxed: 1.625; /* Long-form content */

/* Font Weights */
--weight-normal:  400;
--weight-medium:  500;
--weight-semibold: 600;
--weight-bold:    700;
```

### Hierarchy Rules
- **H1 (Page Title)**: 2xl-3xl, weight-bold, Gray 9, tight leading
- **H2 (Section)**: xl-2xl, weight-semibold, Gray 8, tight leading
- **H3 (Subsection)**: lg-xl, weight-semibold, Gray 8, snug leading
- **Body**: base, weight-normal, Gray 7, normal leading
- **Secondary**: sm, weight-normal, Gray 6, normal leading
- **Labels**: xs-sm, weight-medium, Gray 6, uppercase tracking

---

## 4. Components

### Buttons

**Primary Button**
```css
Background:    #0070F3
Text:          #FFFFFF (weight-medium, text-sm)
Padding:       10px 16px
Border-radius: 4px
Transition:    background 150ms ease

Hover:         #0051CC
Active:        #0051CC + scale(0.98)
Disabled:      #E4E4E7 background, #A1A1AA text
```

**Secondary Button**
```css
Background:    #FFFFFF
Border:        1px solid #E4E4E7
Text:          #27272A (weight-medium, text-sm)
Padding:       9px 15px (1px less for border)

Hover:         #FAFAFA background
Active:        #F4F4F5 background
```

**Ghost Button**
```css
Background:    transparent
Text:          #52525B (weight-medium, text-sm)
Padding:       10px 16px

Hover:         #FAFAFA background
Active:        #F4F4F5 background
```

### Inputs

**Text Input**
```css
Background:    #FFFFFF
Border:        1px solid #E4E4E7
Text:          #27272A (text-base)
Padding:       8px 12px
Border-radius: 4px
Height:        40px

Focus:         border #0070F3, box-shadow 0 0 0 3px #E6F3FF
Error:         border #EF4444, box-shadow 0 0 0 3px #FEE2E2
Disabled:      background #FAFAFA, text #A1A1AA
```

**Label**
```css
Text:          #3F3F46 (text-sm, weight-medium)
Margin-bottom: 6px
```

### Cards

**Default Card**
```css
Background:    #FFFFFF
Border:        1px solid #E4E4E7
Border-radius: 8px
Padding:       24px
Shadow:        none (border-only default)

Hover:         border #D4D4D8 (if interactive)
```

**Elevated Card** (modals, popovers)
```css
Background:    #FFFFFF
Border:        1px solid #E4E4E7
Border-radius: 8px
Padding:       24px
Shadow:        0 4px 6px -1px rgba(0,0,0,0.06), 
               0 2px 4px -1px rgba(0,0,0,0.04)
```

### Tables

**Table Header**
```css
Background:    #FAFAFA
Border-bottom: 1px solid #E4E4E7
Text:          #52525B (text-xs, weight-medium, uppercase, tracking-wide)
Padding:       12px 16px
```

**Table Row**
```css
Border-bottom: 1px solid #F4F4F5
Text:          #27272A (text-sm)
Padding:       12px 16px

Hover:         background #FAFAFA
Striped (alt): background #FAFAFA
```

**Table Cell (Numeric)**
```css
Font:          --font-mono
Text-align:    right
Letter-spacing: -0.01em (tighter for digits)
```

### Charts (BI Dashboards)

**Chart Container**
```css
Background:    #FFFFFF
Border:        1px solid #E4E4E7
Border-radius: 8px
Padding:       20px
```

**Chart Title**
```css
Text:          #27272A (text-lg, weight-semibold)
Margin-bottom: 16px
```

**Axis Labels**
```css
Text:          #71717A (text-xs)
Font:          --font-mono (for numbers)
```

**Grid Lines**
```css
Color:         #F4F4F5
Stroke-width:  1px
```

**Tooltips**
```css
Background:    #18181B
Text:          #FFFFFF (text-sm)
Border-radius: 4px
Padding:       8px 12px
Shadow:        0 4px 6px rgba(0,0,0,0.15)
```

---

## 5. Layout

### Grid System
```css
/* Container Max-Widths */
--container-sm:  640px;
--container-md:  768px;
--container-lg:  1024px;
--container-xl:  1280px;
--container-2xl: 1536px;

/* Page Padding */
--page-padding-mobile: 16px;
--page-padding-tablet: 24px;
--page-padding-desktop: 32px;
```

### Spacing Scale (Tailwind-based)
```css
--space-0:   0px;
--space-1:   4px;
--space-2:   8px;
--space-3:   12px;
--space-4:   16px;
--space-5:   20px;
--space-6:   24px;
--space-8:   32px;
--space-10:  40px;
--space-12:  48px;
--space-16:  64px;
--space-20:  80px;
--space-24:  96px;
--space-32:  128px;
```

### White Space Principles
- **Component Padding**: 16-24px (space-4 to space-6)
- **Section Gaps**: 32-48px (space-8 to space-12)
- **Page Margins**: 64-96px vertical (space-16 to space-24)
- **Element Spacing**: 8-16px between related items (space-2 to space-4)
- **Line Breaks**: Avoid arbitrary breaks; use spacing to create rhythm

### Dashboard Layout (BI)
```
+-----------------------------------------+
| Header (64px height)                     |
+-----------------------------------------+
| KPI Row (120px height, 4-col grid)       |
| [Metric] [Metric] [Metric] [Metric]     |
+-----------------------------------------+
| Chart Grid (2-col on desktop, 1 mobile)  |
| [Chart 1    ] [Chart 2    ]              |
| [Chart 3    ] [Chart 4    ]              |
+-----------------------------------------+
| Data Table (full-width)                  |
+-----------------------------------------+

Spacing: 24px gaps between all sections
```

---

## 6. Depth

### Shadow System
```css
/* Level 0 - Flat (default) */
--shadow-none: none;

/* Level 1 - Subtle Lift (dropdowns, autocomplete) */
--shadow-sm: 0 1px 2px 0 rgba(0,0,0,0.05);

/* Level 2 - Cards on Hover */
--shadow-md: 0 4px 6px -1px rgba(0,0,0,0.06), 
             0 2px 4px -1px rgba(0,0,0,0.04);

/* Level 3 - Modals, Popovers */
--shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.08), 
             0 4px 6px -2px rgba(0,0,0,0.04);

/* Level 4 - Dialogs, Overlays */
--shadow-xl: 0 20px 25px -5px rgba(0,0,0,0.10), 
             0 10px 10px -5px rgba(0,0,0,0.04);
```

### Elevation Hierarchy
- **Base Layer**: White background, no shadow, 1px border
- **Elevated Layer**: Cards with shadow-md, modals with shadow-lg
- **Floating Layer**: Tooltips, dropdowns (shadow-lg + higher z-index)
- **Overlay Layer**: Dialogs, full-screen modals (shadow-xl + backdrop)

### Borders
```css
/* Prefer borders over shadows for flat design */
--border-width: 1px;
--border-color: #E4E4E7;
--border-color-strong: #D4D4D8;
--border-radius-sm: 4px;
--border-radius-md: 8px;
--border-radius-lg: 12px;
```

**Border Usage:**
- Cards, inputs, tables: Always use 1px border
- Avoid shadows unless element needs to "float" (modals, dropdowns)
- Dividers: 1px solid #F4F4F5 (lighter than card borders)

---

## 7. Do's and Don'ts

### Color Usage
**DO:**
- Use Gray 7-10 for primary text on white backgrounds
- Reserve brand blue (#0070F3) for actions and links only
- Use semantic colors (success, error) sparingly for status
- Keep data visualization to 6-8 colors max

**DON'T:**
- Don't use low-contrast gray text (below Gray 6) for body content
- Don't overuse brand color; 90% of UI should be monochrome
- Don't use semantic colors for decoration
- Don't mix chart colors with UI colors

### Typography
**DO:**
- Use monospace fonts for numbers, data, code
- Maintain consistent line-height within content blocks
- Use font-weight to create hierarchy (not just size)
- Keep text-sm or larger for body content

**DON'T:**
- Don't use multiple font families in the same view
- Don't use text smaller than 12px (text-xs)
- Don't use italic for emphasis (use weight or color)
- Don't center-align large blocks of text

### Layout
**DO:**
- Align elements to a grid (8px or 4px baseline)
- Use consistent spacing between sections (24px, 32px, 48px)
- Give content room to breathe (min 16px padding)
- Prioritize horizontal space for data tables

**DON'T:**
- Don't use arbitrary spacing (e.g., 17px, 23px)
- Don't cram content; use pagination or scrolling
- Don't mix spacing scales within the same component
- Don't ignore mobile breakpoints

### Components
**DO:**
- Use 40px height for interactive elements (buttons, inputs)
- Maintain consistent border-radius (4px for small, 8px for large)
- Provide clear hover/focus states for all interactive elements
- Use disabled states to prevent invalid actions

**DON'T:**
- Don't use custom components when native HTML works
- Don't remove focus indicators (accessibility requirement)
- Don't make non-interactive elements look clickable
- Don't rely on color alone to convey information

### Data Presentation
**DO:**
- Right-align numbers in tables
- Use tabular-nums (monospace digits) for aligned columns
- Show units and context labels clearly
- Use subtle backgrounds for alternate table rows

**DON'T:**
- Don't left-align numeric data
- Don't use proportional fonts for data columns
- Don't hide critical context (units, timestamps)
- Don't use heavy zebra-striping (subtle #FAFAFA only)

### Depth & Shadows
**DO:**
- Default to borders; use shadows for floating elements
- Keep shadows subtle (low opacity, small blur)
- Layer modals above page content with backdrop
- Use consistent elevation levels

**DON'T:**
- Don't use heavy drop shadows (this isn't 2010)
- Don't stack shadows (one level per element)
- Don't use shadows on flat UI elements (buttons, inputs)
- Don't mix border + shadow on the same element (pick one)

### Responsive Design
**DO:**
- Stack multi-column layouts vertically on mobile
- Increase touch targets to 44px minimum on mobile
- Use horizontal scrolling for wide tables on small screens
- Test on real devices, not just browser resize

**DON'T:**
- Don't hide critical content on mobile
- Don't use hover states as the only interaction cue
- Don't use fixed-width layouts
- Don't ignore landscape orientation on tablets

---

## 8. Responsive Behavior

### Breakpoints
```css
/* Mobile First Approach */
--breakpoint-sm:  640px;   /* Landscape phones */
--breakpoint-md:  768px;   /* Tablets */
--breakpoint-lg:  1024px;  /* Laptops */
--breakpoint-xl:  1280px;  /* Desktops */
--breakpoint-2xl: 1536px;  /* Large desktops */
```

### Scaling Rules

**Mobile (<640px)**
- Single column layouts
- 16px page padding
- Stack all cards vertically
- Full-width buttons
- 44px min touch target height
- Hide secondary navigation; use hamburger menu
- Horizontal scroll for tables (with sticky first column)

**Tablet (640px - 1024px)**
- 2-column grids for cards
- 24px page padding
- Show condensed navigation (icons + labels)
- 40px touch targets
- Stack complex dashboards into 1-2 columns

**Desktop (1024px+)**
- 3-4 column grids for cards
- 32px page padding
- Full navigation with labels
- 40px interaction targets
- Multi-column dashboards (2-3 charts per row)

### Typography Scaling
```css
/* Mobile */
h1: text-2xl (24px)
h2: text-xl (20px)
body: text-base (16px)

/* Desktop */
h1: text-3xl-4xl (30-36px)
h2: text-2xl (24px)
body: text-base (16px) - same as mobile
```

### Component Adaptations

**Buttons (Mobile)**
- Full-width for primary actions
- Min-height: 44px
- Increased padding: 12px 20px

**Tables (Mobile)**
- Horizontal scroll container
- Sticky first column
- Reduced cell padding: 8px 12px
- Hide non-essential columns (priority-based)

**Charts (Mobile)**
- Full-width, reduce height to fit viewport
- Larger touch areas for tooltips
- Simplified legends (below chart, not side)

**Modals (Mobile)**
- Full-screen on small devices
- Slide-up animation from bottom
- Close button in top-right

---

## 9. Agent Prompt Guide

When Claude generates designs using this system, follow these rules:

### Initialization Prompt
```
Use the Tech-Minimal design system:
- Monochrome foundation (grays) with selective blue for actions
- Inter font for UI, JetBrains Mono for data/code
- 1px borders preferred over shadows
- 8px spacing grid
- 40px interactive element height
- High contrast text (Gray 7-10 on white)
```

### Component Generation Rules

**When creating buttons:**
- Default to secondary style (white + border) unless action is primary
- Use `background: #0070F3`, `padding: 10px 16px`, `border-radius: 4px`
- Include hover state: `background: #0051CC`
- Add disabled state: `background: #E4E4E7`, `color: #A1A1AA`

**When creating forms:**
- Labels above inputs, not floating
- 40px input height, 8px 12px padding
- Focus state: blue border + light blue shadow
- Group related fields with 16px spacing

**When creating tables:**
- Header: `background: #FAFAFA`, uppercase small text
- Rows: 1px bottom border (#F4F4F5), hover with #FAFAFA
- Numeric columns: right-aligned, monospace font
- Sticky header if >20 rows

**When creating dashboards:**
- KPI metrics at top (4-column grid)
- Charts in 2-column grid below
- Data table at bottom (full-width)
- 24px gaps between sections
- Each card: white background, 1px border, 8px radius

**When creating charts:**
- Use Chart 1-8 colors from palette
- Grid lines: #F4F4F5, 1px
- Axis labels: Gray 6, monospace for numbers
- Tooltips: dark (#18181B) with white text

### Color Selection Logic
1. **Text**: Default to Gray 7 (#71717A) for body, Gray 9 (#27272A) for headings
2. **Backgrounds**: White (#FFFFFF) for cards, Gray 1 (#FAFAFA) for subtle areas
3. **Borders**: Gray 2 (#E4E4E7) for default, Gray 4 (#D4D4D8) for emphasis
4. **Actions**: Blue (#0070F3) for primary, Gray 8 text for secondary
5. **Status**: Use semantic colors only when status is critical (success, error, warning)

### Spacing Application
- **Between sections**: 32px (space-8) or 48px (space-12)
- **Card padding**: 24px (space-6)
- **Element groups**: 16px (space-4) vertical gap
- **Inline elements**: 8px (space-2) horizontal gap
- **Form fields**: 12px (space-3) between label and input

### Responsive Defaults
- Always mobile-first (start with single column)
- Breakpoints: 640px (sm), 768px (md), 1024px (lg)
- Stack multi-column layouts vertically below 768px
- Increase touch targets to 44px on mobile
- Use horizontal scroll for wide tables on small screens

### Accessibility Checklist
- Minimum text size: 14px (text-sm)
- Contrast ratio: 4.5:1 for body text, 7:1 for headings
- Focus indicators: blue outline + light shadow
- Interactive elements: min 40px height (44px mobile)
- Semantic HTML: use `<button>`, `<input>`, `<table>` correctly

### Example Prompt for Dashboard
```
Create a BI dashboard using Tech-Minimal:
- Top row: 4 KPI cards (white, bordered, 8px radius, 24px padding)
- Middle: 2x2 chart grid (line + bar charts, use Chart 1-4 colors)
- Bottom: data table (sticky header, monospace numbers, right-aligned)
- Spacing: 24px gaps everywhere
- Mobile: stack to single column
```

### Example Prompt for Form
```
Create a login form using Tech-Minimal:
- Card container: white, 1px border, 8px radius, 24px padding
- Inputs: 40px height, Gray 2 border, blue focus ring
- Primary button: full-width, blue (#0070F3), 10px 16px padding
- Labels: Gray 8, text-sm, weight-medium, 6px margin-bottom
- Spacing: 16px between fields
```

### Code Output Format
When generating HTML/CSS:
- Use CSS custom properties for colors/spacing
- Include hover/focus states explicitly
- Add responsive media queries for <768px
- Use semantic HTML5 tags
- Include ARIA labels for interactive elements

### Don'ts for Agents
- Don't invent new colors outside the palette
- Don't use arbitrary spacing (stick to 4px/8px grid)
- Don't add unnecessary animations
- Don't use multiple font families
- Don't ignore mobile breakpoints
- Don't remove borders to "simplify" (borders are intentional)

---

## Quick Reference Card

**Colors**: Grays 0-10, Blue #0070F3, Semantic (success/error/warning)  
**Fonts**: Inter (UI), JetBrains Mono (data)  
**Spacing**: 4/8/12/16/24/32/48/64px  
**Borders**: 1px solid #E4E4E7, radius 4-8px  
**Shadows**: Avoid unless floating (modals, dropdowns)  
**Interactive**: 40px height, blue focus ring  
**Breakpoints**: 640/768/1024/1280/1536px  
**Grid**: 8px baseline, mobile-first

**Stripe DNA**: High contrast, generous spacing, monochrome-first  
**Linear DNA**: Sharp typography, subtle depth, data density  
**Vercel DNA**: Clean, modern, performance-focused

---

*This design system is optimized for BI dashboards, SaaS products, and developer tools where clarity and data density are paramount.*
