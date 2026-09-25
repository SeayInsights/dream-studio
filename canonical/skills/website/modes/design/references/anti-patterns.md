---
source: https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
extracted: 2026-05-02
pattern: anti-patterns
purpose: 99 UX anti-patterns with do/don't examples
---

# UX Anti-Patterns Reference

A comprehensive collection of 99 UX anti-patterns covering accessibility violations, poor interaction design, performance issues, and more. Each anti-pattern includes do/don't examples and severity ratings.

## Table of Contents

- [Navigation](#navigation) (6 patterns)
- [Animation](#animation) (8 patterns)
- [Layout](#layout) (7 patterns)
- [Touch](#touch) (6 patterns)
- [Interaction](#interaction) (8 patterns)
- [Accessibility](#accessibility) (11 patterns)
- [Performance](#performance) (9 patterns)
- [Forms](#forms) (10 patterns)
- [Responsive](#responsive) (8 patterns)
- [Typography](#typography) (6 patterns)
- [Feedback](#feedback) (6 patterns)
- [Content](#content) (4 patterns)
- [Onboarding](#onboarding) (1 pattern)
- [Search](#search) (2 patterns)
- [Data Entry](#data-entry) (1 pattern)
- [AI Interaction](#ai-interaction) (3 patterns)
- [Spatial UI](#spatial-ui) (2 patterns)
- [Sustainability](#sustainability) (2 patterns)

---

## Navigation

### 1. Smooth Scroll (High Severity)
**Platform:** Web

**Issue:** Anchor links should scroll smoothly to target section

**Do:** Use scroll-behavior: smooth on html element
```css
html { scroll-behavior: smooth; }
```

**Don't:** Jump directly without transition
```html
<a href='#section'> without CSS
```

---

### 2. Sticky Navigation (Medium Severity)
**Platform:** Web

**Issue:** Fixed nav should not obscure content

**Do:** Add padding-top to body equal to nav height
```
pt-20 (if nav is h-20)
```

**Don't:** Let nav overlap first section content
```
No padding compensation
```

---

### 3. Active State (Medium Severity)
**Platform:** All

**Issue:** Current page/section should be visually indicated

**Do:** Highlight active nav item with color/underline
```
text-primary border-b-2
```

**Don't:** No visual feedback on current location
```
All links same style
```

---

### 4. Back Button (High Severity)
**Platform:** Mobile

**Issue:** Users expect back to work predictably

**Do:** Preserve navigation history properly
```javascript
history.pushState()
```

**Don't:** Break browser/app back button behavior
```javascript
location.replace()
```

---

### 5. Deep Linking (Medium Severity)
**Platform:** All

**Issue:** URLs should reflect current state for sharing

**Do:** Update URL on state/view changes
```
Use query params or hash
```

**Don't:** Static URLs for dynamic content
```
Single URL for all states
```

---

### 6. Breadcrumbs (Low Severity)
**Platform:** Web

**Issue:** Show user location in site hierarchy

**Do:** Use for sites with 3+ levels of depth
```
Home > Category > Product
```

**Don't:** Use for flat single-level sites
```
Only on deep nested pages
```

---

## Animation

### 7. Excessive Motion (High Severity)
**Platform:** All

**Issue:** Too many animations cause distraction and motion sickness

**Do:** Animate 1-2 key elements per view maximum
```
Single hero animation
```

**Don't:** Animate everything that moves
```
animate-bounce on 5+ elements
```

---

### 8. Duration Timing (Medium Severity)
**Platform:** All

**Issue:** Animations should feel responsive not sluggish

**Do:** Use 150-300ms for micro-interactions
```
transition-all duration-200
```

**Don't:** Use animations longer than 500ms for UI
```
duration-1000
```

---

### 9. Reduced Motion (High Severity)
**Platform:** All

**Issue:** Respect user's motion preferences

**Do:** Check prefers-reduced-motion media query
```css
@media (prefers-reduced-motion: reduce)
```

**Don't:** Ignore accessibility motion settings
```
No motion query check
```

---

### 10. Loading States (High Severity)
**Platform:** All

**Issue:** Show feedback during async operations

**Do:** Use skeleton screens or spinners
```
animate-pulse skeleton
```

**Don't:** Leave UI frozen with no feedback
```
Blank screen while loading
```

---

### 11. Hover vs Tap (High Severity)
**Platform:** All

**Issue:** Hover effects don't work on touch devices

**Do:** Use click/tap for primary interactions
```
onClick handler
```

**Don't:** Rely only on hover for important actions
```
onMouseEnter only
```

---

### 12. Continuous Animation (Medium Severity)
**Platform:** All

**Issue:** Infinite animations are distracting

**Do:** Use for loading indicators only
```
animate-spin on loader
```

**Don't:** Use for decorative elements
```
animate-bounce on icons
```

---

### 13. Transform Performance (Medium Severity)
**Platform:** Web

**Issue:** Some CSS properties trigger expensive repaints

**Do:** Use transform and opacity for animations
```css
transform: translateY()
```

**Don't:** Animate width/height/top/left properties
```css
top: 10px animation
```

---

### 14. Easing Functions (Low Severity)
**Platform:** All

**Issue:** Linear motion feels robotic

**Do:** Use ease-out for entering ease-in for exiting
```
ease-out
```

**Don't:** Use linear for UI transitions
```
linear
```

---

## Layout

### 15. Z-Index Management (High Severity)
**Platform:** Web

**Issue:** Stacking context conflicts cause hidden elements

**Do:** Define z-index scale system (10 20 30 50)
```
z-10 z-20 z-50
```

**Don't:** Use arbitrary large z-index values
```
z-[9999]
```

---

### 16. Overflow Hidden (Medium Severity)
**Platform:** Web

**Issue:** Hidden overflow can clip important content

**Do:** Test all content fits within containers
```
overflow-auto with scroll
```

**Don't:** Blindly apply overflow-hidden
```
overflow-hidden truncating content
```

---

### 17. Fixed Positioning (Medium Severity)
**Platform:** Web

**Issue:** Fixed elements can overlap or be inaccessible

**Do:** Account for safe areas and other fixed elements
```
Fixed nav + fixed bottom with gap
```

**Don't:** Stack multiple fixed elements carelessly
```
Multiple overlapping fixed elements
```

---

### 18. Stacking Context (Medium Severity)
**Platform:** Web

**Issue:** New stacking contexts reset z-index

**Do:** Understand what creates new stacking context
```
Parent with z-index isolates children
```

**Don't:** Expect z-index to work across contexts
```
z-index: 9999 not working
```

---

### 19. Content Jumping (High Severity)
**Platform:** Web

**Issue:** Layout shift when content loads is jarring

**Do:** Reserve space for async content
```
aspect-ratio or fixed height
```

**Don't:** Let images/content push layout around
```
No dimensions on images
```

---

### 20. Viewport Units (Medium Severity)
**Platform:** Web

**Issue:** 100vh can be problematic on mobile browsers

**Do:** Use dvh or account for mobile browser chrome
```
min-h-dvh or min-h-screen
```

**Don't:** Use 100vh for full-screen mobile layouts
```
h-screen on mobile
```

---

### 21. Container Width (Medium Severity)
**Platform:** Web

**Issue:** Content too wide is hard to read

**Do:** Limit max-width for text content (65-75ch)
```
max-w-prose or max-w-3xl
```

**Don't:** Let text span full viewport width
```
Full width paragraphs
```

---

## Touch

### 22. Touch Target Size (High Severity)
**Platform:** Mobile

**Issue:** Small buttons are hard to tap accurately

**Do:** Minimum 44x44px touch targets
```
min-h-[44px] min-w-[44px]
```

**Don't:** Tiny clickable areas
```
w-6 h-6 buttons
```

---

### 23. Touch Spacing (Medium Severity)
**Platform:** Mobile

**Issue:** Adjacent touch targets need adequate spacing

**Do:** Minimum 8px gap between touch targets
```
gap-2 between buttons
```

**Don't:** Tightly packed clickable elements
```
gap-0 or gap-1
```

---

### 24. Gesture Conflicts (Medium Severity)
**Platform:** Mobile

**Issue:** Custom gestures can conflict with system

**Do:** Avoid horizontal swipe on main content
```
Vertical scroll primary
```

**Don't:** Override system gestures
```
Horizontal swipe carousel only
```

---

### 25. Tap Delay (Medium Severity)
**Platform:** Mobile

**Issue:** 300ms tap delay feels laggy

**Do:** Use touch-action CSS or fastclick
```css
touch-action: manipulation
```

**Don't:** Default mobile tap handling
```
No touch optimization
```

---

### 26. Pull to Refresh (Low Severity)
**Platform:** Mobile

**Issue:** Accidental refresh is frustrating

**Do:** Disable where not needed
```css
overscroll-behavior: contain
```

**Don't:** Enable by default everywhere
```
Default overscroll
```

---

### 27. Haptic Feedback (Low Severity)
**Platform:** Mobile

**Issue:** Tactile feedback improves interaction feel

**Do:** Use for confirmations and important actions
```javascript
navigator.vibrate(10)
```

**Don't:** Overuse vibration feedback
```
Vibrate on every tap
```

---

## Interaction

### 28. Focus States (High Severity)
**Platform:** All

**Issue:** Keyboard users need visible focus indicators

**Do:** Use visible focus rings on interactive elements
```
focus:ring-2 focus:ring-blue-500
```

**Don't:** Remove focus outline without replacement
```
outline-none without alternative
```

---

### 29. Hover States (Medium Severity)
**Platform:** Web

**Issue:** Visual feedback on interactive elements

**Do:** Change cursor and add subtle visual change
```
hover:bg-gray-100 cursor-pointer
```

**Don't:** No hover feedback on clickable elements
```
No hover style
```

---

### 30. Active States (Medium Severity)
**Platform:** All

**Issue:** Show immediate feedback on press/click

**Do:** Add pressed/active state visual change
```
active:scale-95
```

**Don't:** No feedback during interaction
```
No active state
```

---

### 31. Disabled States (Medium Severity)
**Platform:** All

**Issue:** Clearly indicate non-interactive elements

**Do:** Reduce opacity and change cursor
```
opacity-50 cursor-not-allowed
```

**Don't:** Confuse disabled with normal state
```
Same style as enabled
```

---

### 32. Loading Buttons (High Severity)
**Platform:** All

**Issue:** Prevent double submission during async actions

**Do:** Disable button and show loading state
```
disabled={loading} spinner
```

**Don't:** Allow multiple clicks during processing
```
Button clickable while loading
```

---

### 33. Error Feedback (High Severity)
**Platform:** All

**Issue:** Users need to know when something fails

**Do:** Show clear error messages near problem
```
Red border + error message
```

**Don't:** Silent failures with no feedback
```
No indication of error
```

---

### 34. Success Feedback (Medium Severity)
**Platform:** All

**Issue:** Confirm successful actions to users

**Do:** Show success message or visual change
```
Toast notification or checkmark
```

**Don't:** No confirmation of completed action
```
Action completes silently
```

---

### 35. Confirmation Dialogs (High Severity)
**Platform:** All

**Issue:** Prevent accidental destructive actions

**Do:** Confirm before delete/irreversible actions
```
Are you sure modal
```

**Don't:** Delete without confirmation
```
Direct delete on click
```

---

## Accessibility

### 36. Color Contrast (High Severity)
**Platform:** All

**Issue:** Text must be readable against background

**Do:** Minimum 4.5:1 ratio for normal text
```
#333 on white (7:1)
```

**Don't:** Low contrast text
```
#999 on white (2.8:1)
```

---

### 37. Color Only (High Severity)
**Platform:** All

**Issue:** Don't convey information by color alone

**Do:** Use icons/text in addition to color
```
Red text + error icon
```

**Don't:** Red/green only for error/success
```
Red border only for error
```

---

### 38. Alt Text (High Severity)
**Platform:** All

**Issue:** Images need text alternatives

**Do:** Descriptive alt text for meaningful images
```html
alt='Dog playing in park'
```

**Don't:** Empty or missing alt attributes
```html
alt='' for content images
```

---

### 39. Heading Hierarchy (Medium Severity)
**Platform:** Web

**Issue:** Screen readers use headings for navigation

**Do:** Use sequential heading levels h1-h6
```
h1 then h2 then h3
```

**Don't:** Skip heading levels or misuse for styling
```
h1 then h4
```

---

### 40. ARIA Labels (High Severity)
**Platform:** All

**Issue:** Interactive elements need accessible names

**Do:** Add aria-label for icon-only buttons
```html
aria-label='Close menu'
```

**Don't:** Icon buttons without labels
```html
<button><Icon/></button>
```

---

### 41. Keyboard Navigation (High Severity)
**Platform:** Web

**Issue:** All functionality accessible via keyboard

**Do:** Tab order matches visual order
```
tabIndex for custom order
```

**Don't:** Keyboard traps or illogical tab order
```
Unreachable elements
```

---

### 42. Screen Reader (Medium Severity)
**Platform:** All

**Issue:** Content should make sense when read aloud

**Do:** Use semantic HTML and ARIA properly
```html
<nav> <main> <article>
```

**Don't:** Div soup with no semantics
```html
<div> for everything
```

---

### 43. Form Labels (High Severity)
**Platform:** All

**Issue:** Inputs must have associated labels

**Do:** Use label with for attribute or wrap input
```html
<label for='email'>
```

**Don't:** Placeholder-only inputs
```html
placeholder='Email' only
```

---

### 44. Error Messages (High Severity)
**Platform:** All

**Issue:** Error messages must be announced

**Do:** Use aria-live or role=alert for errors
```html
role='alert'
```

**Don't:** Visual-only error indication
```
Red border only
```

---

### 45. Skip Links (Medium Severity)
**Platform:** Web

**Issue:** Allow keyboard users to skip navigation

**Do:** Provide skip to main content link
```
Skip to main content link
```

**Don't:** No skip link on nav-heavy pages
```
100 tabs to reach content
```

---

### 46. Motion Sensitivity (High Severity)
**Platform:** All

**Issue:** Parallax/Scroll-jacking causes nausea

**Do:** Respect prefers-reduced-motion
```css
@media (prefers-reduced-motion)
```

**Don't:** Force scroll effects
```javascript
ScrollTrigger.create()
```

---

## Performance

### 47. Image Optimization (High Severity)
**Platform:** All

**Issue:** Large images slow page load

**Do:** Use appropriate size and format (WebP)
```
srcset with multiple sizes
```

**Don't:** Unoptimized full-size images
```
4000px image for 400px display
```

---

### 48. Lazy Loading (Medium Severity)
**Platform:** All

**Issue:** Load content as needed

**Do:** Lazy load below-fold images and content
```html
loading='lazy'
```

**Don't:** Load everything upfront
```
All images eager load
```

---

### 49. Code Splitting (Medium Severity)
**Platform:** Web

**Issue:** Large bundles slow initial load

**Do:** Split code by route/feature
```javascript
dynamic import()
```

**Don't:** Single large bundle
```
All code in main bundle
```

---

### 50. Caching (Medium Severity)
**Platform:** Web

**Issue:** Repeat visits should be fast

**Do:** Set appropriate cache headers
```
Cache-Control headers
```

**Don't:** No caching strategy
```
Every request hits server
```

---

### 51. Font Loading (Medium Severity)
**Platform:** Web

**Issue:** Web fonts can block rendering

**Do:** Use font-display swap or optional
```css
font-display: swap
```

**Don't:** Invisible text during font load
```
FOIT (Flash of Invisible Text)
```

---

### 52. Third Party Scripts (Medium Severity)
**Platform:** Web

**Issue:** External scripts can block rendering

**Do:** Load non-critical scripts async/defer
```html
async or defer attribute
```

**Don't:** Synchronous third-party scripts
```html
<script src='...'> in head
```

---

### 53. Bundle Size (Medium Severity)
**Platform:** Web

**Issue:** Large JavaScript slows interaction

**Do:** Monitor and minimize bundle size
```
Bundle analyzer
```

**Don't:** Ignore bundle size growth
```
No size monitoring
```

---

### 54. Render Blocking (Medium Severity)
**Platform:** Web

**Issue:** CSS/JS can block first paint

**Do:** Inline critical CSS defer non-critical
```
Critical CSS inline
```

**Don't:** Large blocking CSS files
```
All CSS in head
```

---

## Forms

### 55. Input Labels (High Severity)
**Platform:** All

**Issue:** Every input needs a visible label

**Do:** Always show label above or beside input
```html
<label>Email</label><input>
```

**Don't:** Placeholder as only label
```html
placeholder='Email' only
```

---

### 56. Error Placement (Medium Severity)
**Platform:** All

**Issue:** Errors should appear near the problem

**Do:** Show error below related input
```
Error under each field
```

**Don't:** Single error message at top of form
```
All errors at form top
```

---

### 57. Inline Validation (Medium Severity)
**Platform:** All

**Issue:** Validate as user types or on blur

**Do:** Validate on blur for most fields
```
onBlur validation
```

**Don't:** Validate only on submit
```
Submit-only validation
```

---

### 58. Input Types (Medium Severity)
**Platform:** All

**Issue:** Use appropriate input types

**Do:** Use email tel number url etc
```html
type='email'
```

**Don't:** Text input for everything
```html
type='text' for email
```

---

### 59. Autofill Support (Medium Severity)
**Platform:** Web

**Issue:** Help browsers autofill correctly

**Do:** Use autocomplete attribute properly
```html
autocomplete='email'
```

**Don't:** Block or ignore autofill
```html
autocomplete='off' everywhere
```

---

### 60. Required Indicators (Medium Severity)
**Platform:** All

**Issue:** Mark required fields clearly

**Do:** Use asterisk or (required) text
```
* required indicator
```

**Don't:** No indication of required fields
```
Guess which are required
```

---

### 61. Password Visibility (Medium Severity)
**Platform:** All

**Issue:** Let users see password while typing

**Do:** Toggle to show/hide password
```
Show/hide password button
```

**Don't:** No visibility toggle
```
Password always hidden
```

---

### 62. Submit Feedback (High Severity)
**Platform:** All

**Issue:** Confirm form submission status

**Do:** Show loading then success/error state
```
Loading -> Success message
```

**Don't:** No feedback after submit
```
Button click with no response
```

---

### 63. Input Affordance (Medium Severity)
**Platform:** All

**Issue:** Inputs should look interactive

**Do:** Use distinct input styling
```
Border/background on inputs
```

**Don't:** Inputs that look like plain text
```
Borderless inputs
```

---

### 64. Mobile Keyboards (Medium Severity)
**Platform:** Mobile

**Issue:** Show appropriate keyboard for input type

**Do:** Use inputmode attribute
```html
inputmode='numeric'
```

**Don't:** Default keyboard for all inputs
```
Text keyboard for numbers
```

---

## Responsive

### 65. Mobile First (Medium Severity)
**Platform:** Web

**Issue:** Design for mobile then enhance for larger

**Do:** Start with mobile styles then add breakpoints
```
Default mobile + md: lg: xl:
```

**Don't:** Desktop-first causing mobile issues
```
Desktop default + max-width queries
```

---

### 66. Breakpoint Testing (Medium Severity)
**Platform:** Web

**Issue:** Test at all common screen sizes

**Do:** Test at 320 375 414 768 1024 1440
```
Multiple device testing
```

**Don't:** Only test on your device
```
Single device development
```

---

### 67. Touch Friendly (High Severity)
**Platform:** Web

**Issue:** Mobile layouts need touch-sized targets

**Do:** Increase touch targets on mobile
```
Larger buttons on mobile
```

**Don't:** Same tiny buttons on mobile
```
Desktop-sized targets on mobile
```

---

### 68. Readable Font Size (High Severity)
**Platform:** All

**Issue:** Text must be readable on all devices

**Do:** Minimum 16px body text on mobile
```
text-base or larger
```

**Don't:** Tiny text on mobile
```
text-xs for body text
```

---

### 69. Viewport Meta (High Severity)
**Platform:** Web

**Issue:** Set viewport for mobile devices

**Do:** Use width=device-width initial-scale=1
```html
<meta name='viewport'...>
```

**Don't:** Missing or incorrect viewport
```
No viewport meta tag
```

---

### 70. Horizontal Scroll (High Severity)
**Platform:** Web

**Issue:** Avoid horizontal scrolling

**Do:** Ensure content fits viewport width
```
max-w-full overflow-x-hidden
```

**Don't:** Content wider than viewport
```
Horizontal scrollbar on mobile
```

---

### 71. Image Scaling (Medium Severity)
**Platform:** Web

**Issue:** Images should scale with container

**Do:** Use max-width: 100% on images
```
max-w-full h-auto
```

**Don't:** Fixed width images overflow
```html
width='800' fixed
```

---

### 72. Table Handling (Medium Severity)
**Platform:** Web

**Issue:** Tables can overflow on mobile

**Do:** Use horizontal scroll or card layout
```
overflow-x-auto wrapper
```

**Don't:** Wide tables breaking layout
```
Table overflows viewport
```

---

## Typography

### 73. Line Height (Medium Severity)
**Platform:** All

**Issue:** Adequate line height improves readability

**Do:** Use 1.5-1.75 for body text
```
leading-relaxed (1.625)
```

**Don't:** Cramped or excessive line height
```
leading-none (1)
```

---

### 74. Line Length (Medium Severity)
**Platform:** Web

**Issue:** Long lines are hard to read

**Do:** Limit to 65-75 characters per line
```
max-w-prose
```

**Don't:** Full-width text on large screens
```
Full viewport width text
```

---

### 75. Font Size Scale (Medium Severity)
**Platform:** All

**Issue:** Consistent type hierarchy aids scanning

**Do:** Use consistent modular scale
```
Type scale (12 14 16 18 24 32)
```

**Don't:** Random font sizes
```
Arbitrary sizes
```

---

### 76. Font Loading (Medium Severity)
**Platform:** Web

**Issue:** Fonts should load without layout shift

**Do:** Reserve space with fallback font
```
font-display: swap + similar fallback
```

**Don't:** Layout shift when fonts load
```
No fallback font
```

---

### 77. Contrast Readability (High Severity)
**Platform:** All

**Issue:** Body text needs good contrast

**Do:** Use darker text on light backgrounds
```
text-gray-900 on white
```

**Don't:** Gray text on gray background
```
text-gray-400 on gray-100
```

---

### 78. Heading Clarity (Medium Severity)
**Platform:** All

**Issue:** Headings should stand out from body

**Do:** Clear size/weight difference
```
Bold + larger size
```

**Don't:** Headings similar to body text
```
Same size as body
```

---

## Feedback

### 79. Loading Indicators (High Severity)
**Platform:** All

**Issue:** Show system status during waits

**Do:** Show spinner/skeleton for operations > 300ms
```
Skeleton or spinner
```

**Don't:** No feedback during loading
```
Frozen UI
```

---

### 80. Empty States (Medium Severity)
**Platform:** All

**Issue:** Guide users when no content exists

**Do:** Show helpful message and action
```
No items yet. Create one!
```

**Don't:** Blank empty screens
```
Empty white space
```

---

### 81. Error Recovery (Medium Severity)
**Platform:** All

**Issue:** Help users recover from errors

**Do:** Provide clear next steps
```
Try again button + help link
```

**Don't:** Error without recovery path
```
Error message only
```

---

### 82. Progress Indicators (Medium Severity)
**Platform:** All

**Issue:** Show progress for multi-step processes

**Do:** Step indicators or progress bar
```
Step 2 of 4 indicator
```

**Don't:** No indication of progress
```
No step information
```

---

### 83. Toast Notifications (Medium Severity)
**Platform:** All

**Issue:** Transient messages for non-critical info

**Do:** Auto-dismiss after 3-5 seconds
```
Auto-dismiss toast
```

**Don't:** Toasts that never disappear
```
Persistent toast
```

---

### 84. Confirmation Messages (Medium Severity)
**Platform:** All

**Issue:** Confirm successful actions

**Do:** Brief success message
```
Saved successfully toast
```

**Don't:** Silent success
```
No confirmation
```

---

## Content

### 85. Truncation (Medium Severity)
**Platform:** All

**Issue:** Handle long content gracefully

**Do:** Truncate with ellipsis and expand option
```
line-clamp-2 with expand
```

**Don't:** Overflow or broken layout
```
Overflow or cut off
```

---

### 86. Date Formatting (Low Severity)
**Platform:** All

**Issue:** Use locale-appropriate date formats

**Do:** Use relative or locale-aware dates
```
2 hours ago or locale format
```

**Don't:** Ambiguous date formats
```
01/02/03
```

---

### 87. Number Formatting (Low Severity)
**Platform:** All

**Issue:** Format large numbers for readability

**Do:** Use thousand separators or abbreviations
```
1.2K or 1,234
```

**Don't:** Long unformatted numbers
```
1234567
```

---

### 88. Placeholder Content (Low Severity)
**Platform:** All

**Issue:** Show realistic placeholders during dev

**Do:** Use realistic sample data
```
Real sample content
```

**Don't:** Lorem ipsum everywhere
```
Lorem ipsum
```

---

## Onboarding

### 89. User Freedom (Medium Severity)
**Platform:** All

**Issue:** Users should be able to skip tutorials

**Do:** Provide Skip and Back buttons
```
Skip Tutorial button
```

**Don't:** Force linear unskippable tour
```
Locked overlay until finished
```

---

## Search

### 90. Autocomplete (Medium Severity)
**Platform:** Web

**Issue:** Help users find results faster

**Do:** Show predictions as user types
```
Debounced fetch + dropdown
```

**Don't:** Require full type and enter
```
No suggestions
```

---

### 91. No Results (Medium Severity)
**Platform:** Web

**Issue:** Dead ends frustrate users

**Do:** Show 'No results' with suggestions
```
Try searching for X instead
```

**Don't:** Blank screen or '0 results'
```
No results found.
```

---

## Data Entry

### 92. Bulk Actions (Low Severity)
**Platform:** Web

**Issue:** Editing one by one is tedious

**Do:** Allow multi-select and bulk edit
```
Checkbox column + Action bar
```

**Don't:** Single row actions only
```
Repeated actions per row
```

---

## AI Interaction

### 93. Disclaimer (High Severity)
**Platform:** All

**Issue:** Users need to know they talk to AI

**Do:** Clearly label AI generated content
```
AI Assistant label
```

**Don't:** Present AI as human
```
Fake human name without label
```

---

### 94. Streaming (Medium Severity)
**Platform:** All

**Issue:** Waiting for full text is slow

**Do:** Stream text response token by token
```
Typewriter effect
```

**Don't:** Show loading spinner for 10s+
```
Spinner until 100% complete
```

---

### 95. Feedback Loop (Low Severity)
**Platform:** All

**Issue:** AI needs user feedback to improve

**Do:** Thumps up/down or 'Regenerate'
```
Feedback component
```

**Don't:** Static output only
```
Read-only text
```

---

## Spatial UI

### 96. Gaze Hover (High Severity)
**Platform:** VisionOS

**Issue:** Elements should respond to eye tracking before pinch

**Do:** Scale/highlight element on look
```
hoverEffect()
```

**Don't:** Static element until pinch
```
onTap only
```

---

### 97. Depth Layering (Medium Severity)
**Platform:** VisionOS

**Issue:** UI needs Z-depth to separate content from environment

**Do:** Use glass material and z-offset
```
.glassBackgroundEffect()
```

**Don't:** Flat opaque panels blocking view
```
bg-white
```

---

## Sustainability

### 98. Auto-Play Video (Medium Severity)
**Platform:** Web

**Issue:** Video consumes massive data and energy

**Do:** Click-to-play or pause when off-screen
```html
playsInline muted preload='none'
```

**Don't:** Auto-play high-res video loops
```html
autoplay loop
```

---

### 99. Asset Weight (Medium Severity)
**Platform:** Web

**Issue:** Heavy 3D/Image assets increase carbon footprint

**Do:** Compress and lazy load 3D models
```
Draco compression
```

**Don't:** Load 50MB textures
```
Raw .obj files
```

---

## Summary by Severity

### High Severity (31 patterns)
Navigation: Smooth Scroll, Back Button
Animation: Excessive Motion, Reduced Motion, Loading States, Hover vs Tap
Layout: Z-Index Management, Content Jumping
Touch: Touch Target Size
Interaction: Focus States, Loading Buttons, Error Feedback, Confirmation Dialogs
Accessibility: Color Contrast, Color Only, Alt Text, ARIA Labels, Keyboard Navigation, Form Labels, Error Messages, Motion Sensitivity
Performance: Image Optimization
Forms: Input Labels, Submit Feedback
Responsive: Touch Friendly, Readable Font Size, Viewport Meta, Horizontal Scroll
Typography: Contrast Readability
Feedback: Loading Indicators
AI Interaction: Disclaimer
Spatial UI: Gaze Hover

### Medium Severity (57 patterns)
Navigation: Sticky Navigation, Active State, Deep Linking
Animation: Duration Timing, Continuous Animation, Transform Performance
Layout: Overflow Hidden, Fixed Positioning, Stacking Context, Viewport Units, Container Width
Touch: Touch Spacing, Gesture Conflicts, Tap Delay
Interaction: Hover States, Active States, Disabled States, Success Feedback
Accessibility: Heading Hierarchy, Screen Reader, Skip Links
Performance: Lazy Loading, Code Splitting, Caching, Font Loading, Third Party Scripts, Bundle Size, Render Blocking
Forms: Error Placement, Inline Validation, Input Types, Autofill Support, Required Indicators, Password Visibility, Input Affordance, Mobile Keyboards
Responsive: Mobile First, Breakpoint Testing, Image Scaling, Table Handling
Typography: Line Height, Line Length, Font Size Scale, Font Loading, Heading Clarity
Feedback: Empty States, Error Recovery, Progress Indicators, Toast Notifications, Confirmation Messages
Content: Truncation
Onboarding: User Freedom
Search: Autocomplete, No Results
AI Interaction: Streaming
Spatial UI: Depth Layering
Sustainability: Auto-Play Video, Asset Weight

### Low Severity (11 patterns)
Navigation: Breadcrumbs
Animation: Easing Functions
Touch: Pull to Refresh, Haptic Feedback
Content: Date Formatting, Number Formatting, Placeholder Content
Data Entry: Bulk Actions
AI Interaction: Feedback Loop
