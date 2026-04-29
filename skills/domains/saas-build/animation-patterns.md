# Animation Patterns

Web animation reference for React SaaS and marketing pages — text animations, cursor effects, card reveals, and scroll-driven transitions. Sourced from: meetdarji006/meet-ui, Yashchauhan008/portfolio-3d.

---

## 1. Text Animation Components

### Hyper Text
Scrambles characters on hover, then resolves to the target string. Classic "hacker" decode effect.
```tsx
<HyperText text="Welcome" className="text-4xl font-bold" />
```
Implementation: `useEffect` on hover → cycle through random chars → settle on real chars with `setTimeout` stagger.

### Morphing Text
Crossfades between an array of strings on a timer. Useful for hero taglines.
```tsx
<MorphingText texts={["Design", "Build", "Ship"]} interval={2000} />
```
Pattern: CSS `opacity` transition + alternating render of two overlapping spans.

### Typewriter Text
Types characters one by one, optionally loops.
```tsx
<TypewriterText words={["Hello", "World"]} loop typingSpeed={80} deletingSpeed={40} />
```

### Gooey Text
SVG `feTurbulence` + `feDisplacementMap` filter creates a liquid/melting warp on hover.
Use for hero sections — high visual impact, use sparingly.

### Rubber Band Text
Each character bounces with spring physics on hover. Framer Motion `whileHover` per character.
```tsx
// Wrap each char in a motion.span with spring stiffness: 300, damping: 10
```

### Looping Words
Vertical slot-machine text that cycles through a word list.
```tsx
<LoopingWords words={["Fast", "Reliable", "Beautiful"]} />
```

### Spotlight Text / Pattern Text
Text with a radial gradient spotlight that follows mouse position. Uses `mousemove` → CSS variable `--x --y` → `radial-gradient` mask.

---

## 2. Cursor Effects

Replace or augment the native cursor for immersive hero sections. Always provide `cursor: none` on the target element.

### Magnetic Cursor
Cursor snaps toward interactive elements within a radius. Framer Motion `useMotionValue` + `useSpring` on x/y.
```tsx
// On element hover: lerp cursor position toward element center
// Spring config: stiffness: 150, damping: 15
```

### Pixel Cursor Trail
Leaves a trail of colored squares that fade out. `mousemove` → push coordinates → `requestAnimationFrame` decay loop.

### Ring Cursor
Outer ring follows with a lag (spring delay), inner dot follows immediately. Two `motion.div` elements with different spring configs.
```tsx
const outerSpring = { stiffness: 100, damping: 20 }  // lags
const innerSpring = { stiffness: 500, damping: 30 }  // snappy
```

### Follow Eyes
SVG eyes that track cursor position. Compute angle from eye center to cursor: `Math.atan2(dy, dx)`, rotate pupil.

---

## 3. Card & Reveal Patterns

### Glow Card
Radial gradient border glow that follows mouse within the card. `mousemove` → CSS vars `--mouse-x --mouse-y` → `radial-gradient` on `::before` pseudo-element.
```css
.glow-card::before {
  background: radial-gradient(600px at var(--mouse-x) var(--mouse-y),
    rgba(99,102,241,0.15), transparent 80%);
}
```

### Wave Card
Card surface has a subtle CSS wave animation. `animation: wave 3s ease-in-out infinite` on a pseudo-element with `border-radius` morphing.

### Content Reveal Card
Content hidden behind a frosted overlay; hover slides/fades it away. Framer Motion `AnimatePresence` + `initial={{ opacity:0, y:20 }}` → `animate={{ opacity:1, y:0 }}`.

### Morphing Card Stack
Stacked cards that spread and expand on hover. Each card uses `z-index` + `translateY` + `rotate` transforms.
```tsx
// Cards: [{rotate: -6, y: 16}, {rotate: -3, y: 8}, {rotate: 0, y: 0}]
// On hover: animate to spread positions
```

### Stacked Carousel / Staggered Testimonials
Cards fan out on interaction; selecting one brings it to front. `motion.div` with `layoutId` for shared element transitions.

---

## 4. GSAP Scroll Timeline Patterns

Use GSAP + ScrollTrigger for scroll-driven narrative sequences. Requires `gsap` + `@gsap/react`.

### Basic scroll-pinned section
```tsx
useGSAP(() => {
  gsap.timeline({
    scrollTrigger: {
      trigger: containerRef.current,
      start: "top top",
      end: "+=300%",
      pin: true,           // pins the container while timeline plays
      scrub: 1,            // smooth scrub (1s lag behind scroll)
    }
  })
  .from(".hero-title", { opacity: 0, y: 60, duration: 1 })
  .from(".hero-sub",   { opacity: 0, y: 40, duration: 0.8 }, "-=0.4")
  .to(".hero-image",   { scale: 1.2, duration: 1 });
}, []);
```

### Stagger reveal on scroll
```tsx
gsap.from(".card", {
  scrollTrigger: { trigger: ".card-grid", start: "top 80%" },
  opacity: 0, y: 50,
  stagger: 0.15,
  duration: 0.6,
  ease: "power2.out"
});
```

### Horizontal scroll section
```tsx
gsap.to(".panel-track", {
  x: () => -(totalWidth - window.innerWidth),
  ease: "none",
  scrollTrigger: {
    trigger: ".horizontal-section",
    pin: true, scrub: 1,
    end: () => `+=${totalWidth}`
  }
});
```

### Cleanup (React)
```tsx
useGSAP(() => {
  const ctx = gsap.context(() => { /* all animations */ }, containerRef);
  return () => ctx.revert();  // cleanup on unmount
}, []);
```

---

## 5. Framer Motion Idioms

### Entrance animations
```tsx
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.4, ease: "easeOut" }}
/>
```

### Stagger children
```tsx
const container = { hidden: {}, show: { transition: { staggerChildren: 0.1 } } }
const item = { hidden: { opacity: 0, y: 20 }, show: { opacity: 1, y: 0 } }

<motion.ul variants={container} initial="hidden" animate="show">
  {items.map(i => <motion.li key={i} variants={item} />)}
</motion.ul>
```

### Layout animations (reorder / expand)
```tsx
<motion.div layout>  {/* animate position/size changes automatically */}
```

### Shared element transition
```tsx
// Source card
<motion.img layoutId={`image-${id}`} src={img} />
// Detail view (same layoutId = morphs between positions)
<motion.img layoutId={`image-${id}`} src={img} className="full-size" />
```

### Spring config reference
| Use case | stiffness | damping |
|----------|-----------|---------|
| Snappy UI response | 400 | 30 |
| Fluid follow cursor | 150 | 15 |
| Bouncy card hover | 300 | 10 |
| Slow reveal | 80 | 20 |

---

## Anti-patterns

| ❌ Wrong | ✅ Correct |
|---|---|
| GSAP animations without ScrollTrigger cleanup | Always `ctx.revert()` in React `useGSAP` return |
| Animating `width`/`height` directly | Animate `scaleX`/`scaleY` — GPU composited, no layout thrash |
| `cursor: none` globally | Scope to the hero section only — don't break UX elsewhere |
| Heavy cursor effects on mobile | `useMediaQuery` — disable cursor effects on touch devices |
| Framer Motion without `layout` key on reordering lists | `layout` prop on `motion.div` prevents position jumps |
| Playing GSAP animations before fonts load | Wait for `document.fonts.ready` before triggering text animations |
