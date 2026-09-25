# Editorial Modern Design System

Content-first design system inspired by Notion, Substack, and Medium. Optimized for long-form reading, documentation, blogs, knowledge bases, and storytelling experiences.

---

## 1. Visual Theme

**Philosophy:** Content is the hero. Typography, whitespace, and rhythm guide readers through immersive narratives without distraction.

**Core Principles:**
- **Readability First:** Generous line-height (1.6-1.8), optimal line length (65-75 characters), comfortable font sizes
- **Hierarchy Through Scale:** Dramatic scale shifts between headlines and body text create clear information layers
- **White Space as Structure:** Margins and padding define content zones — no decorative borders or dividers needed
- **Subtle Depth:** Minimal shadows and elevation; rely on spacing and typography for separation
- **Content Breathing Room:** Single-column layouts with wide margins for distraction-free reading

**Mood:** Calm, focused, intellectual, timeless. Feels like a quiet library or a well-designed print magazine.

---

## 2. Color Palette

### Text Colors
```css
--text-primary: #1a1a1a;        /* Body text, headlines */
--text-secondary: #525252;      /* Subheadings, metadata */
--text-tertiary: #737373;       /* Captions, timestamps, secondary info */
--text-link: #2563eb;           /* Links (blue-600) */
--text-link-hover: #1d4ed8;     /* Link hover (blue-700) */
```

### Background Colors
```css
--bg-canvas: #ffffff;           /* Main background */
--bg-elevated: #fafafa;         /* Sidebar, code blocks, callouts */
--bg-hover: #f5f5f5;            /* Interactive element hover */
--bg-accent: #f0f9ff;           /* Highlight backgrounds (blue-50) */
```

### Accent Colors
```css
--accent-primary: #2563eb;      /* Primary actions, selected states (blue-600) */
--accent-secondary: #7c3aed;    /* Secondary actions, tags (violet-600) */
--accent-success: #059669;      /* Success states (emerald-600) */
--accent-warning: #d97706;      /* Warnings (amber-600) */
--accent-danger: #dc2626;       /* Errors, destructive actions (red-600) */
```

### Borders
```css
--border-light: #e5e5e5;        /* Dividers, card outlines */
--border-medium: #d4d4d4;       /* Input borders, table borders */
--border-focus: #2563eb;        /* Focus rings */
```

**Usage Notes:**
- High text contrast (4.5:1 minimum) for accessibility
- Accent colors used sparingly — let content dominate
- Borders are subtle and minimal
- Dark mode variant swaps backgrounds and text (see Responsive section)

---

## 3. Typography

### Font Families
```css
--font-serif: "Tiempos Text", "Iowan Old Style", "Palatino Linotype", "URW Palladio L", P052, serif;
--font-sans: "Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
--font-mono: "JetBrains Mono", "Fira Code", "Courier New", monospace;
```

**Pairing Strategy:** Serif for headlines and body text (warmth, readability), sans-serif for UI elements and metadata (clarity, modernity), monospace for code and technical content.

### Type Scale
```css
/* Headlines */
--text-5xl: 3rem;      /* 48px — Article titles */
--text-4xl: 2.25rem;   /* 36px — Section headings */
--text-3xl: 1.875rem;  /* 30px — Subsection headings */
--text-2xl: 1.5rem;    /* 24px — Card titles, large headings */

/* Body */
--text-xl: 1.25rem;    /* 20px — Intro paragraphs, large body */
--text-lg: 1.125rem;   /* 18px — Standard body text */
--text-base: 1rem;     /* 16px — UI text, captions */
--text-sm: 0.875rem;   /* 14px — Metadata, timestamps */
--text-xs: 0.75rem;    /* 12px — Labels, tags */
```

### Line Heights
```css
--leading-tight: 1.25;    /* Headlines, display text */
--leading-normal: 1.6;    /* Body text */
--leading-relaxed: 1.8;   /* Long-form content, blog posts */
```

### Font Weights
```css
--font-light: 300;        /* Rarely used */
--font-normal: 400;       /* Body text */
--font-medium: 500;       /* Subheadings, emphasized text */
--font-semibold: 600;     /* UI elements, buttons */
--font-bold: 700;         /* Headlines, strong emphasis */
```

**Typography Best Practices:**
- Use serif for article body text (--text-lg, --leading-relaxed)
- Use sans-serif for metadata, buttons, and navigation
- Limit line length to 65-75 characters for optimal readability
- Scale up headlines dramatically (3-4 steps) for visual impact
- Use font weight variations (medium, semibold) over size changes for subtle hierarchy

---

## 4. Components

### Article Header
```html
<header class="article-header">
  <h1 class="article-title">The Power of Long-Form Content</h1>
  <div class="article-meta">
    <span class="author">By Jane Doe</span>
    <span class="separator">·</span>
    <time class="timestamp">May 1, 2026</time>
    <span class="separator">·</span>
    <span class="read-time">8 min read</span>
  </div>
</header>
```
```css
.article-header {
  max-width: 680px;
  margin: 0 auto 3rem;
  text-align: left;
}

.article-title {
  font-family: var(--font-serif);
  font-size: var(--text-5xl);
  font-weight: var(--font-bold);
  line-height: var(--leading-tight);
  color: var(--text-primary);
  margin-bottom: 1rem;
}

.article-meta {
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.separator {
  color: var(--border-medium);
}
```

### Body Text Block
```html
<div class="content-block">
  <p>Long-form content requires careful attention to typography, spacing, and rhythm...</p>
</div>
```
```css
.content-block {
  max-width: 680px;
  margin: 0 auto;
}

.content-block p {
  font-family: var(--font-serif);
  font-size: var(--text-lg);
  line-height: var(--leading-relaxed);
  color: var(--text-primary);
  margin-bottom: 1.5rem;
}

.content-block h2 {
  font-family: var(--font-serif);
  font-size: var(--text-3xl);
  font-weight: var(--font-bold);
  line-height: var(--leading-tight);
  color: var(--text-primary);
  margin: 3rem 0 1rem;
}

.content-block h3 {
  font-family: var(--font-serif);
  font-size: var(--text-2xl);
  font-weight: var(--font-semibold);
  line-height: var(--leading-tight);
  color: var(--text-primary);
  margin: 2rem 0 0.75rem;
}
```

### Callout / Aside
```html
<aside class="callout">
  <div class="callout-icon">💡</div>
  <div class="callout-content">
    <strong>Key Insight:</strong> Readers retain 65% more information from well-structured content.
  </div>
</aside>
```
```css
.callout {
  max-width: 680px;
  margin: 2rem auto;
  padding: 1.5rem;
  background: var(--bg-accent);
  border-left: 4px solid var(--accent-primary);
  border-radius: 8px;
  display: flex;
  gap: 1rem;
}

.callout-icon {
  font-size: 1.5rem;
  flex-shrink: 0;
}

.callout-content {
  font-family: var(--font-sans);
  font-size: var(--text-base);
  line-height: var(--leading-normal);
  color: var(--text-primary);
}
```

### Code Block
```html
<pre class="code-block"><code class="language-javascript">const reader = new ContentReader({
  mode: 'immersive',
  theme: 'editorial-modern'
});</code></pre>
```
```css
.code-block {
  max-width: 680px;
  margin: 2rem auto;
  padding: 1.5rem;
  background: var(--bg-elevated);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  overflow-x: auto;
  font-family: var(--font-mono);
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--text-primary);
}
```

### Table of Contents
```html
<nav class="toc">
  <h4 class="toc-title">In This Article</h4>
  <ul class="toc-list">
    <li><a href="#introduction">Introduction</a></li>
    <li><a href="#core-principles">Core Principles</a></li>
    <li><a href="#implementation">Implementation</a></li>
  </ul>
</nav>
```
```css
.toc {
  max-width: 240px;
  padding: 1.5rem;
  background: var(--bg-elevated);
  border-radius: 8px;
  position: sticky;
  top: 2rem;
}

.toc-title {
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 1rem;
}

.toc-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.toc-list li {
  margin-bottom: 0.5rem;
}

.toc-list a {
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  color: var(--text-tertiary);
  text-decoration: none;
  transition: color 0.15s ease;
}

.toc-list a:hover {
  color: var(--text-link);
}

.toc-list a.active {
  color: var(--accent-primary);
  font-weight: var(--font-medium);
}
```

### Sidebar Widget
```html
<aside class="sidebar-widget">
  <h4 class="widget-title">Related Reading</h4>
  <div class="widget-content">
    <a href="#" class="widget-link">Understanding Typography</a>
    <a href="#" class="widget-link">Content Hierarchy Principles</a>
  </div>
</aside>
```
```css
.sidebar-widget {
  padding: 1.5rem;
  background: var(--bg-canvas);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  margin-bottom: 1.5rem;
}

.widget-title {
  font-family: var(--font-sans);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--text-primary);
  margin-bottom: 1rem;
}

.widget-content {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.widget-link {
  font-family: var(--font-sans);
  font-size: var(--text-sm);
  color: var(--text-link);
  text-decoration: none;
  transition: color 0.15s ease;
}

.widget-link:hover {
  color: var(--text-link-hover);
  text-decoration: underline;
}
```

### Button (Primary)
```html
<button class="btn-primary">Subscribe</button>
```
```css
.btn-primary {
  font-family: var(--font-sans);
  font-size: var(--text-base);
  font-weight: var(--font-medium);
  color: #ffffff;
  background: var(--accent-primary);
  border: none;
  border-radius: 6px;
  padding: 0.75rem 1.5rem;
  cursor: pointer;
  transition: background 0.15s ease, transform 0.1s ease;
}

.btn-primary:hover {
  background: var(--text-link-hover);
}

.btn-primary:active {
  transform: translateY(1px);
}
```

---

## 5. Layout

### Grid System
```css
/* Content-centered layout with sidebar */
.editorial-grid {
  display: grid;
  grid-template-columns: 1fr min(680px, 100%) 1fr;
  gap: 0 3rem;
  max-width: 1280px;
  margin: 0 auto;
  padding: 2rem;
}

.editorial-grid .content {
  grid-column: 2;
}

.editorial-grid .sidebar {
  grid-column: 3;
}

/* Full-width breakout */
.editorial-grid .breakout {
  grid-column: 1 / -1;
  max-width: 1000px;
  margin: 0 auto;
}
```

### Spacing Scale
```css
--space-xs: 0.25rem;   /* 4px */
--space-sm: 0.5rem;    /* 8px */
--space-md: 1rem;      /* 16px */
--space-lg: 1.5rem;    /* 24px */
--space-xl: 2rem;      /* 32px */
--space-2xl: 3rem;     /* 48px */
--space-3xl: 4rem;     /* 64px */
--space-4xl: 6rem;     /* 96px */
```

**Layout Principles:**
- **Single-column main content** (680px max-width for reading comfort)
- **Generous margins** (minimum 2rem on mobile, 3rem on desktop)
- **Vertical rhythm** (consistent spacing between sections using --space-2xl or --space-3xl)
- **Sticky sidebar** for navigation (table of contents, related links)
- **Full-width breakouts** for images, quotes, or data visualizations

### Example Page Structure
```html
<div class="editorial-page">
  <header class="page-header">
    <!-- Site logo, navigation -->
  </header>
  
  <div class="editorial-grid">
    <main class="content">
      <article>
        <header class="article-header">...</header>
        <div class="content-block">...</div>
      </article>
    </main>
    
    <aside class="sidebar">
      <nav class="toc">...</nav>
      <div class="sidebar-widget">...</div>
    </aside>
  </div>
  
  <footer class="page-footer">
    <!-- Footer links, copyright -->
  </footer>
</div>
```

---

## 6. Depth

### Elevation System
```css
/* Minimal shadows — rely on borders and spacing */
--shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
--shadow-md: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
--shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.05);
```

**Usage:**
- **Level 0 (Flat):** Article body, inline content — no shadow, no border
- **Level 1 (Surface):** Cards, callouts, code blocks — `border: 1px solid var(--border-light)` + `--shadow-sm`
- **Level 2 (Elevated):** Sticky sidebar, floating TOC, modals — `--shadow-md`
- **Level 3 (Overlay):** Tooltips, dropdowns, popovers — `--shadow-lg`

**Depth Philosophy:**
Editorial design avoids heavy shadows. Use subtle borders and whitespace to create separation. Shadows are reserved for interactive overlays (dropdowns, modals) that need clear visual separation from content.

---

## 7. Do's and Don'ts

### Do's
- **Do** use generous line-height (1.6-1.8) for body text
- **Do** limit line length to 65-75 characters for readability
- **Do** scale headlines dramatically (3-5x body text size)
- **Do** use serif fonts for long-form body text (warmth, readability)
- **Do** pair serif headlines with sans-serif metadata (contrast, clarity)
- **Do** give content room to breathe (2-3rem margins minimum)
- **Do** use subtle borders over heavy shadows
- **Do** maintain vertical rhythm (consistent spacing between sections)
- **Do** left-align text (never justify long-form content)
- **Do** use single-column layouts for main content

### Don'ts
- **Don't** use decorative backgrounds or patterns (distracts from content)
- **Don't** use narrow containers (<600px for body text)
- **Don't** use tight line-height (<1.4) for body text
- **Don't** use all-caps for long text (slows reading speed)
- **Don't** use light gray text for body content (reduces readability)
- **Don't** use multiple colors for text hierarchy (use size/weight instead)
- **Don't** use heavy drop shadows or glows
- **Don't** center-align long paragraphs (hard to scan)
- **Don't** use more than 2 font families in a design
- **Don't** crowd the page — whitespace is a feature, not wasted space

---

## 8. Responsive

### Breakpoints
```css
--screen-sm: 640px;   /* Small devices (landscape phones) */
--screen-md: 768px;   /* Tablets */
--screen-lg: 1024px;  /* Laptops */
--screen-xl: 1280px;  /* Desktops */
```

### Mobile Adaptations
```css
/* Stack sidebar below content on mobile */
@media (max-width: 1023px) {
  .editorial-grid {
    grid-template-columns: 1fr;
    padding: 1rem;
  }
  
  .editorial-grid .content,
  .editorial-grid .sidebar {
    grid-column: 1;
  }
  
  .sidebar {
    margin-top: 3rem;
  }
}

/* Reduce headline sizes on mobile */
@media (max-width: 767px) {
  .article-title {
    font-size: 2rem; /* Down from 3rem */
  }
  
  .content-block h2 {
    font-size: 1.5rem; /* Down from 1.875rem */
  }
  
  .content-block p {
    font-size: 1rem; /* Down from 1.125rem */
  }
}
```

### Dark Mode
```css
@media (prefers-color-scheme: dark) {
  :root {
    --text-primary: #e5e5e5;
    --text-secondary: #a3a3a3;
    --text-tertiary: #737373;
    --text-link: #60a5fa; /* blue-400 */
    --text-link-hover: #93c5fd; /* blue-300 */
    
    --bg-canvas: #0a0a0a;
    --bg-elevated: #171717;
    --bg-hover: #262626;
    --bg-accent: #172554; /* blue-950 */
    
    --border-light: #262626;
    --border-medium: #404040;
    --border-focus: #60a5fa;
  }
}
```

**Responsive Strategy:**
- **Mobile-first:** Start with single-column layout, add sidebar at 1024px+
- **Fluid typography:** Scale down headlines proportionally on small screens
- **Touch-friendly:** Minimum 44px tap targets for buttons and links
- **Dark mode:** Swap color palette while maintaining contrast ratios
- **Reading comfort:** Keep 680px content width on all screen sizes

---

## 9. Agent Prompt Guide

When designing with the editorial-modern system, use this guidance to translate user requests into design decisions.

### Prompt Templates

**For article/blog layouts:**
```
Create a blog post layout using editorial-modern.
- Use serif (Tiempos Text fallback to system serif) for headline and body
- Main content max-width 680px, centered
- Headline: 48px bold serif, line-height 1.25
- Body text: 18px regular serif, line-height 1.8
- Meta info (author, date, read time): 14px sans-serif, tertiary gray
- Sidebar with sticky table of contents at 1024px+
- 48px vertical spacing between sections
```

**For documentation pages:**
```
Create a documentation page using editorial-modern.
- Left sidebar navigation (240px wide, sticky)
- Main content area 680px max-width
- Headings: serif bold (h1: 36px, h2: 30px, h3: 24px)
- Body text: 18px serif, line-height 1.8
- Code blocks: JetBrains Mono, light gray background, 8px border-radius
- Callouts: blue-50 background, blue-600 left border (4px)
- Right sidebar for table of contents (sticky)
```

**For content platforms:**
```
Create a content feed using editorial-modern.
- Grid layout: 2 columns at 1024px+, 1 column on mobile
- Card components: white background, 1px light gray border, 8px border-radius
- Card title: 24px serif bold
- Card excerpt: 16px serif regular, 1.6 line-height
- Card meta: 14px sans-serif, tertiary gray
- 24px gap between cards
- Hover state: subtle shadow (shadow-md)
```

### Design Decision Tree

| User says... | System response |
|--------------|-----------------|
| "Make this readable" | Apply 18px serif body text, 1.8 line-height, 680px max-width |
| "Add hierarchy" | Scale up headline to 48px, use font-weight variations (semibold, bold) |
| "It feels cramped" | Increase vertical spacing to 48px between sections, add 32px margins |
| "The sidebar is cluttered" | Stack widgets vertically, use subtle borders (not backgrounds), limit to 3-4 items |
| "Make it feel premium" | Use serif headlines, generous whitespace, minimal borders, subtle shadows |
| "It's hard to scan" | Add table of contents, use bold subheadings every 3-4 paragraphs, break up long text blocks |
| "The code doesn't stand out" | Use elevated background, mono font, syntax highlighting (if available) |

### Common Mistakes to Avoid

1. **Using sans-serif for long-form body text** → Serif is more readable at length
2. **Narrow content width (<600px)** → Breaks reading rhythm, feels cramped
3. **Tight line-height (<1.5)** → Strains eyes, reduces comprehension
4. **Too many font sizes** → Limit to 4-5 sizes max for hierarchy
5. **Heavy shadows or gradients** → Distracts from content, feels dated
6. **Center-aligned paragraphs** → Hard to scan, slows reading speed
7. **Colorful text for hierarchy** → Use size/weight instead; color is for accents only
8. **Ignoring vertical rhythm** → Inconsistent spacing breaks flow

### Testing Checklist

Before finalizing an editorial-modern design:
- [ ] Body text is 18px serif with 1.8 line-height
- [ ] Main content max-width is 680px
- [ ] Headlines are 2-3x larger than body text
- [ ] Vertical spacing between sections is 48px minimum
- [ ] Sidebar (if present) is sticky and ≤240px wide
- [ ] No decorative backgrounds or heavy shadows
- [ ] Dark mode color palette swaps correctly
- [ ] Mobile layout stacks to single column <1024px
- [ ] Line length is 65-75 characters
- [ ] All text contrast meets WCAG AA (4.5:1 minimum)

---

## Quick Reference Card

```
COLORS:        Text #1a1a1a → #e5e5e5 (dark)  |  Accent #2563eb  |  Border #e5e5e5
FONTS:         Serif (Tiempos Text)  |  Sans (Inter)  |  Mono (JetBrains Mono)
SCALE:         48px / 36px / 30px / 24px / 18px / 16px / 14px
LINE-HEIGHT:   1.8 (body)  |  1.6 (UI)  |  1.25 (headlines)
LAYOUT:        680px content  |  240px sidebar  |  48px section spacing
SHADOWS:       Minimal (shadow-sm for cards, shadow-md for overlays)
RADIUS:        6-8px (subtle rounding)
BREAKPOINTS:   1024px (sidebar), 768px (tablet), 640px (mobile)
```
