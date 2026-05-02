---
ds:
  pack: domains
  mode: website/animate
  mode_type: build
  inputs: [direction_lock, animation_target, animation_type]
  outputs: [html_with_animations, export_instructions]
  capabilities_required: [Read, Write]
  model_preference: sonnet
  estimated_duration: 10-30min
---

# Animate — Motion Design Engine

> MANDATORY: Read `references/animation-pitfalls.md` before every animation decision.

## Conceptual Model

| Primitive | Definition |
|-----------|------------|
| **Stage** | Containing element that defines animation boundaries |
| **Sprite** | Any element that animates within the stage |
| **Timeline** | Sequence and timing of sprite animations |

## Animation Categories

| Category | Purpose | Max Duration | Example |
|----------|---------|-------------|---------|
| Entrance | Element appears | 600ms | Fade up, slide in, scale up |
| Exit | Element disappears | 400ms | Fade out, slide out, scale down |
| Emphasis | Draw attention | 800ms | Pulse, shake, glow |
| Transition | Between states | 300ms | Page change, tab switch |
| Scroll | On-scroll reveal | 600ms | Parallax, fade-in on intersect |
| Stagger | Sequential reveal | 1200ms total | Cards appearing one by one |
| Loop | Continuous motion | N/A (user-controlled) | Background particles, loading |

## Implementation Rules

- Use CSS animations and transitions — not JS-based animation libraries
- Use `@keyframes` for complex sequences
- Use `transition` for simple state changes
- Use `IntersectionObserver` for scroll-triggered animations
- Use CSS `animation-delay` for stagger patterns
- Always include `prefers-reduced-motion` media query
- Always provide pause/stop control for infinite loops

## Anti-Patterns (hard stops)

- Animation > 800ms for entrances
- Simultaneous `opacity` + `transform` + `filter` on the same element
- `animation-delay` without a visual placeholder (content jumps in)
- Layout-triggering properties (`top`, `left`, `width`, `height`) in animations — use `transform` instead
- No `prefers-reduced-motion` media query
- Infinite loop without user control (pause/stop)
- More than 5 staggered elements
- JS animation libraries when CSS can do it

## Export Pipeline

Export is manual (not automated). Guide the user through these steps.

### MP4 at 60fps
```bash
# 1. Record in browser via DevTools or screen capture tool
# 2. Normalize to 25fps base
ffmpeg -i recording.mp4 -r 25 base.mp4
# 3. Interpolate to 60fps
ffmpeg -i base.mp4 -vf "minterpolate=fps=60:mi_mode=mci" output-60fps.mp4
```

### GIF with palette optimization
```bash
ffmpeg -i recording.mp4 -vf "fps=15,scale=800:-1:flags=lanczos,palettegen" palette.png
ffmpeg -i recording.mp4 -i palette.png -filter_complex "fps=15,scale=800:-1:flags=lanczos[x];[x][1:v]paletteuse" output.gif
```

### Add BGM/audio
```bash
ffmpeg -i output.mp4 -i bgm.mp3 -c:v copy -c:a aac -shortest final.mp4
```

## Audio / BGM Guidance

| Mood | Character |
|------|-----------|
| Corporate | Clean, professional, moderate tempo |
| Playful | Upbeat, friendly, energetic |
| Dramatic | Building tension, cinematic |
| Ambient | Subtle, atmospheric, non-intrusive |
| Tech | Electronic, modern, precise |
| Cinematic | Orchestral, emotional, sweeping |

Free royalty-free sources: **freesound.org**, **Pixabay Audio**, **YouTube Audio Library**
