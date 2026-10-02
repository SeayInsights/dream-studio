# Brand Profile — Schema and Contract

Every Power BI skill document under this domain (`custom-visuals.md`, `visual-verification.md`,
`pbir-gotchas.md`, `report-visual-json.md`, `quality-tiers-antipatterns.md`, `pbi-workflows.md`,
and the mode's own `SKILL.md`) refers to **"the active brand profile"** instead of naming a
client, a palette, a font, or a logo path directly. This file is the schema/contract for that
profile: what it contains, how an agent resolves which one is active, and the rules for when a
deviation from it is legitimate.

**No skill text in this domain may hardcode a client's brand identity** — not a hex code, not a
font name, not a logo path, not a sentiment color. If a concrete value is needed to illustrate a
pattern, write it as a reference into the active profile (e.g. "the active brand profile's
`palette.primary[0]` color") rather than a literal.

## Why this exists

The reference content in this domain carries real engineering value — PBIR gotchas, DAX
patterns, visual-verification tooling — that has nothing to do with any one client's colors or
logo. Baking a specific brand into the skill text would mean every new engagement requires
editing the skill itself. Instead, brand identity lives in a small, swappable profile file, and
the skill text only ever points at it.

## Resolving the active profile

1. If the user has already told the agent which engagement/client this work is for and a profile
   exists for it, use that profile.
2. If it's unclear which profile applies and the work involves theming, branding, or visual
   styling, **ask** — don't guess a client's colors.
3. If nothing else is specified (a scratch report, an internal demo, a first pass before a client
   profile exists), fall back to `brand-profiles/default.yml` — the neutral starter profile
   shipped alongside this file.
4. Once resolved, read the profile's fields and the theme file it points to before doing any
   theming, TMDL, JSON, or TypeScript work that touches color, font, or logo.

## Schema

A brand profile is a YAML file with this shape:

```yaml
name: "<profile display name>"

palette:
  primary:
    # Chart-series colors double as the profile's primary identity colors, in order.
    # role is a stable identifier other skill text can reference; hex is the value.
    - role: default_text          # body/label text color
      hex: "#1F2933"
    - role: primary_series        # first data-series / chart color
      hex: "#1F2933"
    - role: accent_selected       # accent / selected-state color
      hex: "#2E6FDB"
    # Additional entries extend the series palette (role: series_3, series_4, ...)

  secondary:
    # Dividers, backgrounds, alternating row shading — the quiet colors.
    - role: divider
      hex: "#D7DEE5"
    - role: background_alt
      hex: "#F4F6F8"
    - role: row_alternate
      hex: "#EDF1F4"

  accent:
    # sentiment_policy governs how positive/negative values are conveyed:
    #   neutral       — no color-coded positive/negative. Direction is conveyed by
    #                   arrow glyphs (▲▼) plus a single text color; use bold weight
    #                   for emphasis instead of a second color.
    #   accent-coded  — positive and negative/attention accent colors below are
    #                   applied directly to values, fonts, or conditional formatting.
    sentiment_policy: neutral        # "neutral" | "accent-coded"
    positive: null                   # hex; required when sentiment_policy = accent-coded
    negative: null                   # hex; required when sentiment_policy = accent-coded
    attention: "#2E6FDB"             # "deserves a look" accent — used under either policy

typography:
  # Power BI only renders fonts actually installed on the VIEWER'S machine — a
  # brand guide's print/display font is not safe here. Use a system/Microsoft-suite
  # font (Segoe UI, Calibri, Arial) unless the engagement has confirmed the display
  # font is installed tenant-wide.
  font_family: "Segoe UI"
  roles:
    title:    { size: 32, weight: "bold" }
    header:   { size: 14, weight: "semibold" }
    callout:  { size: 22, weight: "bold" }      # card / big-number values
    label:    { size: 11, weight: "regular" }
    footnote: { size: 9,  weight: "italic" }

logo:
  # Each variant is a PATH PLACEHOLDER. The active engagement supplies the actual
  # asset; a brand profile never bundles a logo file itself (see "Never bundle
  # assets" below).
  variants:
    full_color: ""      # for light backgrounds
    white: ""            # for dark/saturated backgrounds
    on_dark: ""           # alias of white, kept distinct in case the engagement
                          # wants a different asset for a dark-but-not-brand-color bg
  selection_rule: >
    Light or neutral page background -> full_color. Dark or saturated brand-color
    background -> white (or on_dark if supplied separately).

page_chrome:
  # Layout conventions for the header/footer band — not pixel positions (those
  # live in report-visual-json.md's generic canvas-grid convention), just which
  # slot each chrome element occupies.
  logo_position: "top-left"
  refresh_indicator_position: "top-right"
  footnote_style: "footer band, italic, footnote-size, divider-color text"

theme_file: "brand-profiles/default-theme.json"
  # Path to the actual Power BI theme JSON for this profile. Import it in Power BI
  # Desktop via View -> Themes -> Browse for themes. See pbi-workflows.md.

decision_rules:
  # When it's correct to deviate from the active profile instead of applying it.
  - "White-label client deliverable: use the client's own theme instead of the active profile."
  - "One-off accent moment explicitly requested by the user: apply at the visual
     level only (objects / conditional formatting on that one visual) — never
     promote a one-off into the theme or into other visuals."
```

### Field notes

- **`palette.primary`** — a brand's "primary colors" double as its ordered chart-series palette.
  `role: primary_series` is index 0 into the theme's `dataColors[]`; later `series_N` entries are
  index 1, 2, 3... Skill text should say "`ColorId` indexes into the active brand profile's
  `dataColors` order" rather than naming a specific color at a specific index (see
  `report-visual-json.md`'s `ThemeDataColor` section).
- **`palette.accent.sentiment_policy`** — this is the field that replaces every "no traffic-light
  red/green, use Navy + arrows" or "green/orange sentiment, no red" rule from a specific brand
  guide. A profile with `neutral` policy gets direction from glyph + weight, never a second color.
  A profile with `accent-coded` policy gets `positive`/`negative` hexes applied directly.
- **`typography.font_family`** — must be a font Power BI can actually render for the audience.
  Prefer the Microsoft/Windows system font set (Segoe UI, Calibri, Arial) unless the engagement
  has verified tenant-wide font installation.
- **`logo.variants`** — always empty-string placeholders in a committed profile. Never commit an
  actual logo asset into this domain (see below).
- **`theme_file`** — points at an actual Power BI theme JSON, which is the file you import into
  Power BI Desktop. The profile YAML itself is not importable into Power BI; it's the
  skill-readable source of truth that the theme JSON (and any TypeScript/TMDL that needs a brand
  value) is generated from or kept in sync with.

## Never bundle client assets

A brand profile file (YAML or theme JSON) never contains or points at a committed logo image,
font file, or any other binary brand asset belonging to a real client. Logo paths are always
placeholders the active engagement fills in from its own workspace. This keeps the skill
repository free of any one client's intellectual property and keeps profiles trivially
swappable — the whole point of this mechanism.

## Using a profile in skill work

- **Theming a report:** read `theme_file`, apply it per `pbi-workflows.md`'s theme-application
  section.
- **Writing DAX/visual-JSON conditional color:** reference the resolved hex from the active
  profile's `palette.accent` (if `sentiment_policy: accent-coded`) or the `neutral` glyph/weight
  convention — never hardcode a hex in the measure or visual JSON itself beyond what the active
  profile resolved to for this one piece of work.
- **Scaffolding a custom visual:** derive the generated LESS variables and format-pane color
  defaults from the active profile's `palette` and `typography`, not from any example baked into
  this skill (see `custom-visuals.md` and `scripts/new-visual.ps1`'s `-BrandProfile` parameter).
- **No profile resolvable and the work doesn't need one yet:** proceed, but resolve before the
  first theming/branding/visual-styling decision actually has to be made.

## Default profile

`brand-profiles/default.yml` is a concrete, neutral profile conforming to this schema — the
fallback when no engagement-specific profile is supplied. It is intentionally plain: a dark
neutral slate for default text and the primary series, a mid-blue accent, light-grey secondary
tones, Segoe UI typography, and `sentiment_policy: neutral`. It carries no trace of any specific
client's brand identity. `brand-profiles/default-theme.json` is its paired, importable Power BI
theme JSON.
