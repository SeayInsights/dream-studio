# Animation Pitfalls — 16 Battle-Tested Rules

Battle-tested rules compiled from real production failures. Each rule exists because someone shipped a broken animation.

---

## Performance Rules

### Rule 1: No animation > 800ms

Entrance and emphasis animations over 800ms feel sluggish. Users notice delay after 400ms. The sweet spot is 200–400ms for most transitions.

*Failure case: Hero section fade-in at 1500ms made users think the page was broken.*

---

### Rule 2: Never animate layout properties

`top`, `left`, `width`, `height`, `margin`, and `padding` trigger layout recalculation on every frame. Use `transform: translate()` and `transform: scale()` instead.

*Failure case: Sidebar slide-in using `left` caused 15fps jank on mobile.*

```css
/* Bad */
.panel { left: -300px; transition: left 300ms; }
.panel.open { left: 0; }

/* Good */
.panel { transform: translateX(-300px); transition: transform 300ms; }
.panel.open { transform: translateX(0); }
```

---

### Rule 3: Use `will-change` sparingly

Only add `will-change` when you've measured jank. It creates a compositor layer which consumes GPU memory. Remove it after the animation completes.

*Failure case: Adding `will-change: transform` to 50 list items caused a GPU memory spike and tab crash on low-end Android.*

```css
/* Add before animation, remove after */
.animating { will-change: transform; }
.done { will-change: auto; }
```

---

### Rule 4: Never combine opacity + transform + filter simultaneously

Three concurrent compositor operations on the same element cause frame drops, especially on mobile. Pick two max.

*Failure case: Card entrance with fade + scale + blur caused 20fps on iPhone SE.*

```css
/* Bad — three compositor operations */
.card { animation: enter 400ms; }
@keyframes enter {
  from { opacity: 0; transform: scale(0.9); filter: blur(4px); }
}

/* Good — two max */
@keyframes enter {
  from { opacity: 0; transform: scale(0.9); }
}
```

---

### Rule 5: Prefer `transform` over `top`/`left`

`transform` only triggers composite (cheap). `top`/`left` triggers layout → paint → composite (expensive). This is the single biggest performance win in CSS animation.

---

## Timing Rules

### Rule 6: Ease-out for entrances, ease-in for exits

Objects entering the viewport should decelerate (ease-out). Objects leaving should accelerate (ease-in). Use ease-in-out for emphasis and loops.

*Why: Matches real-world physics. Objects arriving "land" (decelerate). Objects departing "launch" (accelerate).*

```css
.enter { animation: fadeIn 300ms ease-out; }
.exit  { animation: fadeOut 200ms ease-in; }
```

---

### Rule 7: No `animation-delay` without a visual placeholder

If an element has `animation-delay: 500ms`, the user sees a blank space for 500ms. Show a skeleton or placeholder, or start the element in its initial animated state (opacity 0) so the space is held.

*Failure case: Staggered card entrance left empty card slots for 200–1000ms. Users thought content was missing.*

```css
/* Hold initial state so layout doesn't shift */
.card { opacity: 0; animation: fadeIn 300ms ease-out forwards; }
.card:nth-child(1) { animation-delay: 0ms; }
.card:nth-child(2) { animation-delay: 100ms; }
```

---

### Rule 8: Stagger max 5 elements

More than 5 staggered elements means the last one doesn't appear for 1–2 seconds. Users scroll past before it animates.

*Rule of thumb: Stagger delay = 80–120ms per element. 5 × 100ms = 500ms total. 10 × 100ms = 1000ms = too long.*

---

## Accessibility Rules

### Rule 9: Always include `prefers-reduced-motion`

Some users get motion sickness from animations. This is not optional — it is a WCAG 2.1 requirement.

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

### Rule 10: No infinite loops without user control

Continuous animations (loading spinners, background particles) must have a way to pause. Either pause on hover/focus or provide a visible pause button.

*Failure case: Background particle animation caused seizure risk for photosensitive users.*

```css
.particles:hover,
.particles:focus-within {
  animation-play-state: paused;
}
```

---

### Rule 11: No autoplay video with motion

Videos with rapid motion or flashing must be paused by default with a play button. Never autoplay motion content.

```html
<!-- Correct: muted + no autoplay for motion content -->
<video muted playsinline controls>
  <source src="hero.mp4" type="video/mp4">
</video>
```

---

## Design Rules

### Rule 12: One hero animation per viewport

Multiple competing animations in the same viewport fight for attention. Pick one focal animation; everything else should be subtle or static.

*Failure case: Three simultaneous entrance animations made the hero section feel chaotic.*

---

### Rule 13: Scroll animations must be progressive

Don't dump all scroll animations at once. Reveal elements as they enter the viewport with IntersectionObserver, not on page load.

*Implementation: Use `threshold: 0.2` (trigger when 20% visible). Use `rootMargin: '0px 0px -50px 0px'` to trigger slightly before the element is fully in view.*

```js
const observer = new IntersectionObserver(
  (entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('visible');
        observer.unobserve(entry.target); // animate once
      }
    });
  },
  { threshold: 0.2, rootMargin: '0px 0px -50px 0px' }
);

document.querySelectorAll('[data-animate]').forEach((el) => observer.observe(el));
```

---

### Rule 14: Exit animations must be faster than entrances

Users initiated the exit — they are waiting for it to complete. Entrance: 300–600ms. Exit: 200–400ms.

```css
.modal-enter { animation: slideIn 400ms ease-out; }
.modal-exit  { animation: slideOut 250ms ease-in; }
```

---

### Rule 15: Never animate text content changes

Morphing, typing, or character-by-character reveals are distracting and break assistive technology. Fade the container, not the text.

*Failure case: Character-by-character heading reveal was read by screen readers one character at a time.*

```css
/* Bad — animates the text itself */
.heading span { animation: typein 50ms steps(1) forwards; }

/* Good — fade the container */
.heading { animation: fadeIn 300ms ease-out; }
```

---

### Rule 16: Test on low-end devices

An animation that runs smoothly on a MacBook Pro might run at 10fps on a budget Android phone. Target 60fps on mid-range devices.

*Testing approach: Chrome DevTools → Performance tab → CPU throttling set to 4x slowdown. If the animation drops below 30fps, simplify it — remove a property, reduce duration, or remove `filter`.*
