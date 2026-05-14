# UX Writing — Design Reference

Part of the dream-studio design reference library. Consult when writing UI copy, button labels, error messages, empty states, or any visible text in a design.

## Core Principles

**Button Labels**: Replace ambiguous terms ("OK", "Submit", "Yes/No") with specific action patterns. Use verb + object construction like "Save changes" or "Create account" to clarify outcomes.

**Destructive Actions**: Name the destruction explicitly. Use "Delete" (permanent) rather than "Remove" (recoverable), and include counts: "Delete 5 items" instead of "Delete selected."

## Error Message Framework

Every error should address three questions:
1. What happened?
2. Why did it happen?
3. How can the user fix it?

Rather than vague messaging like "Invalid input," provide actionable guidance: "Email address needs an @ symbol."

**Key templates by situation**:
- Format errors: "[Field] needs to be [format]. Example: [example]"
- Missing fields: "Please enter [what's missing]"
- Access issues: "You don't have access to [thing]. [What to do instead]"
- Network problems: "We couldn't reach [thing]. Check your connection and [action]."

**Never blame users**—reframe as guidance: "Please enter MM/DD/YYYY format" not "You entered an invalid date."

## Microcopy Strategy

**Empty States**: Frame as onboarding opportunities—acknowledge, explain value, provide action. Example: "No projects yet. Create your first one to get started."

**Loading States**: Be specific about what's happening: "Saving your draft..." rather than generic "Loading..."

**Voice vs. Tone**: Voice stays consistent (brand personality); tone adapts to context (celebratory for success, empathetic for errors, serious for destructive actions).

## Accessibility & Translation

**Accessibility essentials**:
- Link text must work standalone: "View pricing plans" not "Click here"
- Alt text describes information content, not images
- Icon buttons need `aria-label` attributes

**Translation planning**: Account for text expansion (German +30%, French +20%). Keep numbers separate, use complete sentences as single strings, avoid abbreviations.

## Consistency Requirements

Establish and enforce a terminology glossary. Example unified terms: Delete (not Remove/Trash), Settings (not Preferences/Options), Sign in (not Log in).

## Avoid List

- Jargon without explanation
- User-blaming language
- Vague errors ("Something went wrong")
- Terminology variation for variety's sake
- Humor in error messages (users are frustrated, not amused)
- Redundant copy that repeats UI elements
- Confirmation dialogs (prefer undo functionality)
