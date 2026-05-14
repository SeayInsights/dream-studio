# Executive Clean Design System

**IBM Carbon + Salesforce Lightning inspired**

Enterprise design system for dashboards, reports, and executive presentations. Professional, authoritative, data-focused, and accessible at scale.

---

## 1. Design Philosophy

**Core Principles:**
- **Data First**: Information hierarchy supports rapid decision-making
- **Professional Authority**: Visual language conveys credibility and expertise
- **Systematic Clarity**: Consistent patterns reduce cognitive load
- **Enterprise Scale**: Components work across teams, products, and contexts
- **Accessible by Default**: WCAG AAA compliance baked into every decision

**Design Values:**
- Precision over decoration
- Substance over style
- Function over form
- Clarity over cleverness
- Trust over trend

**IBM Carbon Influence**: Rigorous grid system, productive density, deliberate motion
**Salesforce Lightning Influence**: Utility-first components, data-table excellence, status-driven color
**Microsoft Fluent Influence**: Depth through elevation, adaptive type scale, neutral backgrounds

---

## 2. Color System

### Base Palette

**Neutrals** (IBM Gray scale)
```
Gray 10:  #f4f4f4  Background / Canvas
Gray 20:  #e0e0e0  Subtle borders
Gray 30:  #c6c6c6  Disabled states
Gray 50:  #8d8d8d  Secondary text
Gray 70:  #525252  Primary text
Gray 90:  #262626  Headings
Gray 100: #161616  Emphasis
```

**Brand Accent** (Professional blue)
```
Blue 60:  #0f62fe  Primary actions
Blue 70:  #0353e9  Hover states
Blue 80:  #002d9c  Active states
Blue 20:  #d0e2ff  Subtle backgrounds
Blue 10:  #edf5ff  Highlights
```

### Semantic Colors

**Status System** (Salesforce-inspired)
```
Success:  #2e844a  (Green 60)
Warning:  #f1c21b  (Yellow 30)
Error:    #da1e28  (Red 60)
Info:     #0043ce  (Blue 70)
```

**Data Visualization** (6-color categorical)
```
1. #0f62fe  Blue 60
2. #8a3ffc  Purple 60
3. #33b1ff  Cyan 40
4. #007d79  Teal 70
5. #ff7eb6  Magenta 50
6. #fa4d56  Red 50
```

**Sequential Scale** (for heatmaps, gradients)
```
#edf5ff → #d0e2ff → #a6c8ff → #78a9ff → #4589ff → #0f62fe → #0043ce
```

### Accessibility Standards

- **Text on Gray 10**: Minimum Gray 70 (4.5:1)
- **Interactive elements**: 3:1 against background
- **Data charts**: 3:1 between adjacent segments
- **Status indicators**: Never rely on color alone

---

## 3. Typography

### Type Scale (IBM Plex Sans)

**Productive Hierarchy** (dashboards, tables, dense UIs)
```
Heading 1:  32px / 40px  SemiBold  Gray 90
Heading 2:  28px / 36px  SemiBold  Gray 90
Heading 3:  20px / 28px  SemiBold  Gray 90
Heading 4:  16px / 24px  SemiBold  Gray 90

Body:       14px / 20px  Regular   Gray 70
Body Small: 12px / 16px  Regular   Gray 70
Caption:    12px / 16px  Regular   Gray 50
Label:      12px / 16px  Medium    Gray 70

Code:       14px / 20px  IBM Plex Mono
```

**Expressive Hierarchy** (presentations, reports)
```
Display:    48px / 56px  Light     Gray 90
Heading 1:  42px / 50px  Regular   Gray 90
Heading 2:  32px / 40px  Regular   Gray 90
Heading 3:  28px / 36px  Regular   Gray 90

Body:       16px / 24px  Regular   Gray 70
Body Small: 14px / 20px  Regular   Gray 70
```

### Font Stacks

**Primary**: IBM Plex Sans, system-ui, -apple-system, sans-serif
**Monospace**: IBM Plex Mono, 'Courier New', monospace

### Typographic Rules

- **Max line length**: 66 characters (body text)
- **Table text**: 14px regular, 12px for dense data
- **Number alignment**: Tabular numerals, right-aligned in tables
- **Case**: Sentence case for UI, Title Case for marketing only
- **Emphasis**: Medium weight over italic for data contexts

---

## 4. Layout & Spacing

### Grid System (IBM Carbon 16-column)

**Breakpoints:**
```
sm:  672px   (mobile)
md:  1056px  (tablet)
lg:  1312px  (desktop)
xl:  1584px  (wide)
max: 1920px  (ultra-wide)
```

**Gutters:**
```
sm:  16px
md:  16px
lg:  32px
xl:  32px
```

**Margins:**
```
sm:  16px
md:  16px
lg:  32px
xl:  32px
```

### Spacing Scale (4px base)

```
spacing-01:  2px   Tight element spacing
spacing-02:  4px   Compact layouts
spacing-03:  8px   Default element spacing
spacing-04:  12px  Small vertical rhythm
spacing-05:  16px  Standard vertical rhythm
spacing-06:  24px  Medium section spacing
spacing-07:  32px  Large section spacing
spacing-08:  40px  Page section dividers
spacing-09:  48px  Major layout sections
spacing-10:  64px  Hero spacing
spacing-11:  80px  Extra-large spacing
spacing-12:  96px  Maximum spacing
```

### Layout Patterns

**Dashboard Grid:**
- Cards on 4, 6, 8, or 12 column spans
- Minimum card height: 240px
- Card padding: spacing-05 (16px)
- Card gap: spacing-05 (16px)

**Data Table:**
- Row height: 40px (default), 32px (compact)
- Cell padding: 16px horizontal, 12px vertical
- Header background: Gray 10
- Zebra striping: Gray 10 / White

**Report Layout:**
- Content max-width: 1312px
- Section spacing: spacing-09 (48px)
- Paragraph spacing: spacing-05 (16px)

---

## 5. Components

### Core UI Components

**Button** (Salesforce-inspired utility)
```
Primary:    Blue 60 bg, White text, 48px height
Secondary:  Transparent bg, Blue 60 border + text
Ghost:      Transparent, Gray 70 text
Danger:     Red 60 bg, White text

States:
- Hover: Darken 1 step
- Active: Darken 2 steps
- Disabled: Gray 30 bg, Gray 50 text
- Focus: 2px Blue 60 outline, 2px offset
```

**Card**
```
Background: White
Border: 1px Gray 20
Radius: 0px (sharp, professional)
Shadow: 0 1px 2px rgba(0,0,0,0.06)
Hover: Shadow 0 2px 8px rgba(0,0,0,0.1)
Padding: spacing-05 (16px)
```

**Input Field**
```
Height: 40px
Border: 1px Gray 50
Background: White
Padding: 0 16px
Font: 14px Regular

States:
- Focus: 2px Blue 60 outline
- Error: Red 60 border, Red 60 outline
- Disabled: Gray 10 bg, Gray 30 border
```

**Data Table**
```
Header: Gray 10 bg, 12px Medium, Gray 70
Row: 40px height, 14px Regular
Border: 1px Gray 20 (horizontal only)
Hover: Gray 10 background
Selected: Blue 10 background, Blue 60 left border
Sorting: Caret icon, Blue 60 when active
```

**Tag / Badge**
```
Height: 24px
Padding: 0 8px
Radius: 12px
Font: 12px Medium

Variants:
- Info: Blue 20 bg, Blue 70 text
- Success: Green 20 bg, Green 70 text
- Warning: Yellow 20 bg, Gray 100 text
- Error: Red 20 bg, Red 70 text
```

**Modal**
```
Overlay: rgba(22, 22, 22, 0.5)
Container: White bg, max-width 640px
Header: 20px SemiBold, spacing-05 padding
Body: 14px Regular, spacing-05 padding
Footer: Gray 10 bg, spacing-05 padding
Shadow: 0 8px 24px rgba(0,0,0,0.15)
```

### Data Visualization Components

**Chart Container**
```
Background: White
Border: 1px Gray 20
Padding: spacing-06 (24px)
Title: 16px SemiBold Gray 90
Subtitle: 12px Regular Gray 50
```

**KPI Card**
```
Value: 32px SemiBold Gray 90 (tabular numerals)
Label: 12px Regular Gray 50
Delta: 14px Medium, Green/Red with arrow
Sparkline: Gray 50 baseline, Blue 60 line
```

**Progress Bar**
```
Height: 8px
Track: Gray 20
Fill: Blue 60
Label: 12px Medium, above or inline
```

---

## 6. Iconography

**System**: Carbon Icons (IBM)
**Size Scale**: 16px, 20px, 24px, 32px
**Weight**: 1.5px stroke
**Grid**: Aligned to pixel grid
**Style**: Outlined, geometric, minimal

**Common Icons:**
- Navigation: chevron-right, chevron-down, menu, close
- Actions: add, edit, delete, download, upload, settings
- Status: checkmark-filled, warning-filled, error-filled, info-filled
- Data: chart-line, chart-bar, table, filter, search

**Usage Rules:**
- Always pair with accessible labels
- Minimum touch target: 32x32px (even if icon is 16px)
- Interactive icons: Blue 60, hover Blue 70
- Decorative icons: Gray 50

---

## 7. Motion & Animation

**Productive Motion** (IBM Carbon standard)

**Duration Scale:**
```
Fast:     100ms  Micro-interactions, hover states
Moderate: 200ms  Component transitions, dropdowns
Slow:     300ms  Panel slides, modal entry
Extra:    500ms  Page transitions, complex choreography
```

**Easing:**
```
Standard:  cubic-bezier(0.2, 0, 0.38, 0.9)  Entrances
Exit:      cubic-bezier(0.2, 0, 1, 0.9)      Exits
Expressive: cubic-bezier(0.4, 0.14, 0.3, 1)  Emphasis
```

**Animation Principles:**
- **Purpose-driven**: Motion communicates state change or spatial relationship
- **Subtle**: Never draw attention away from content
- **Performant**: GPU-accelerated properties only (transform, opacity)
- **Respectful**: Respect prefers-reduced-motion

**Common Patterns:**
- Dropdown: 200ms slide-down with fade
- Modal: 300ms scale(0.95 → 1) with fade
- Toast: 200ms slide-up from bottom
- Loading: Subtle pulse on skeleton screens

---

## 8. Accessibility

**WCAG AAA Compliance**

**Color Contrast:**
- Body text: 7:1 minimum (AAA)
- UI components: 3:1 minimum (AA)
- Large text (18px+): 4.5:1 minimum (AA)

**Keyboard Navigation:**
- All interactive elements in tab order
- Focus indicators: 2px outline, 2px offset, high contrast
- Skip links on complex layouts
- Arrow key navigation for lists, tables, menus

**Screen Reader Support:**
- Semantic HTML (nav, main, article, section)
- ARIA labels on icon-only buttons
- ARIA live regions for dynamic content
- Table headers (th) with scope attributes

**Responsive Text:**
- Supports 200% zoom without horizontal scroll
- Relative units (rem) for font sizes
- Line length max 66 characters

**Reduced Motion:**
- Respect prefers-reduced-motion
- Fallback to instant state changes
- Never auto-play animations

**Form Accessibility:**
- Labels always visible (never placeholder-only)
- Error messages programmatically associated
- Required fields clearly marked
- Autocomplete attributes where applicable

---

## 9. Patterns & Best Practices

### Dashboard Layout Pattern

**Anatomy:**
1. **Header Bar** (64px height)
   - Logo / App title (left)
   - Navigation (center)
   - User actions (right)
   - Background: White, Border-bottom: 1px Gray 20

2. **Filter Bar** (Optional, 56px height)
   - Date range, dropdowns, search
   - Background: Gray 10
   - Sticky on scroll

3. **KPI Row** (120px height)
   - 4-6 KPI cards
   - Grid: 4 columns on lg+, 2 on md, 1 on sm

4. **Chart Grid**
   - 2-3 column layout
   - Cards with equal height per row
   - Spacing-05 gaps

5. **Data Table** (Full-width)
   - Pagination at bottom
   - Sticky header on scroll

### Report Layout Pattern

**Structure:**
- Cover page: Display typography, minimal decoration
- Executive summary: 1-column, spacing-09 sections
- Data sections: 2-column grid (chart + insights)
- Appendix: Full-width tables, compact spacing

**Typography Flow:**
- Heading 1: Section titles
- Heading 3: Sub-sections
- Body: Paragraphs, spacing-05 between
- Caption: Chart annotations, table footnotes

### Status Indicators

**Multi-channel approach** (never color alone):
- Icon + Color + Text label
- Example: checkmark-filled (green) + "Complete"
- Example: warning-filled (yellow) + "Needs Attention"

### Data Table Best Practices

**Column Types:**
- **Text**: Left-aligned, 14px Regular
- **Numbers**: Right-aligned, Tabular numerals
- **Dates**: Left-aligned, consistent format (YYYY-MM-DD)
- **Status**: Center-aligned, Tag component
- **Actions**: Right-aligned, icon buttons

**Sorting:**
- Clickable headers with caret icon
- Active column: Blue 60 text + icon

**Pagination:**
- Rows per page: 25, 50, 100
- Navigation: First, Previous, Page numbers, Next, Last
- Summary: "Showing 1-25 of 1,234"

### Loading States

**Skeleton Screens:**
- Use Gray 20 rectangles matching content structure
- Subtle pulse animation (optional)
- No spinners unless process takes >3 seconds

**Progress Indicators:**
- Determinate: Progress bar with percentage
- Indeterminate: Linear progress (for unknown duration)

### Error Handling

**Inline Errors:**
- Red 60 border on input
- Error icon + message below field
- 12px Regular, Red 60 text

**Page-level Errors:**
- Toast notification (top-right)
- 5-second auto-dismiss or manual close
- Icon + Title + Description

**Empty States:**
- Illustration (optional, minimal)
- 20px SemiBold heading
- 14px Regular description
- Primary action button

### Responsive Strategy

**Mobile-First:**
- Stack cards vertically
- Horizontal scroll for wide tables
- Collapse navigation to hamburger menu
- Enlarge touch targets to 44px minimum

**Tablet:**
- 2-column grid for cards
- Side navigation visible
- Filters in collapsible panel

**Desktop:**
- Full grid layout (3-4 columns)
- Persistent side navigation
- Inline filters

---

## Implementation Notes

**CSS Framework**: Tailwind CSS with custom Carbon-inspired config
**Component Library**: Headless UI for accessible primitives
**Icons**: @carbon/icons-react
**Charts**: Recharts or Chart.js with custom Carbon theme

**Figma Resources:**
- IBM Carbon Design Kit
- Salesforce Lightning Design System (SLDS) Kit

**Code Example** (Button component):
```tsx
<button className="
  h-12 px-6
  bg-blue-600 hover:bg-blue-700 active:bg-blue-800
  text-white text-sm font-medium
  focus:outline-none focus:ring-2 focus:ring-blue-600 focus:ring-offset-2
  disabled:bg-gray-300 disabled:text-gray-500 disabled:cursor-not-allowed
  transition-colors duration-200
">
  Primary Action
</button>
```

---

**End of Design System**

For implementation questions or component requests, reference IBM Carbon documentation and Salesforce Lightning Design System guidelines.
