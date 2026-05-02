"""
generate-tokens.py — Brand token generator (W3C DTCG format)

Usage:
    py scripts/generate-tokens.py brand-input.json
    py scripts/generate-tokens.py brand-input.json --output-dir ./tokens

Reads a brand-input.json file and outputs:
  - brand-tokens.json  (W3C DTCG 3-layer format)
  - brand.css          (CSS custom properties)
"""

import argparse
import colorsys
import json
import os
import sys


# ---------------------------------------------------------------------------
# Color classification helpers
# ---------------------------------------------------------------------------

def hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    """Convert #rrggbb to (h, s, l) where h is 0-360, s and l are 0-100."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    h, l, s = colorsys.rgb_to_hls(r, g, b)  # returns (h, l, s)
    h_deg = h * 360
    return h_deg, s * 100, l * 100


def classify_hue(h: float, s: float, l: float) -> str:
    """Return a color family name given HSL values."""
    # Near-white: very high lightness regardless of saturation → gray-50
    if l >= 95:
        return "gray-50"

    # Achromatic: very low saturation
    if s < 10:
        if l < 20:
            return "gray-950"
        if l < 40:
            return "gray-800"
        if l < 60:
            return "gray-500"
        if l < 80:
            return "gray-200"
        return "gray-50"

    # Chromatic — classify by hue angle
    if h < 15 or h >= 345:
        family = "red"
    elif h < 45:
        family = "orange"
    elif h < 65:
        family = "amber"
    elif h < 85:
        family = "yellow"
    elif h < 150:
        family = "green"
    elif h < 170:
        family = "teal"
    elif h < 200:
        family = "cyan"
    elif h < 215:
        family = "sky"
    elif h < 260:
        family = "blue"
    elif h < 285:
        family = "violet"
    elif h < 315:
        family = "purple"
    elif h < 345:
        family = "pink"
    else:
        family = "red"

    # Special override: low-saturation yellow/orange hues → gold
    if family in ("amber", "yellow", "orange") and 30 <= s <= 80 and 40 <= l <= 70:
        family = "gold"

    # Map lightness to a rough Tailwind-style numeric shade
    if l < 20:
        shade = 900
    elif l < 30:
        shade = 800
    elif l < 40:
        shade = 700
    elif l < 55:
        shade = 600
    elif l < 65:
        shade = 500
    elif l < 75:
        shade = 400
    elif l < 85:
        shade = 300
    elif l < 92:
        shade = 200
    else:
        shade = 100

    return f"{family}-{shade}"


def color_name_for(hex_color: str) -> str:
    """Return a descriptive token name like 'blue-600' for a hex color."""
    h, s, l = hex_to_hsl(hex_color)
    return classify_hue(h, s, l)


# ---------------------------------------------------------------------------
# Spacing scale
# ---------------------------------------------------------------------------

SPACING_MULTIPLIERS = [1, 2, 3, 4, 6, 8, 12]


def build_spacing(base: int) -> dict:
    """Return a dict mapping multiplier key → px value string."""
    return {str(m): f"{base * m}px" for m in SPACING_MULTIPLIERS}


# ---------------------------------------------------------------------------
# Status / utility colors (always included)
# ---------------------------------------------------------------------------

STATUS_COLORS = {
    "green-600": "#16a34a",
    "amber-500": "#f59e0b",
    "red-600":   "#dc2626",
    "blue-500":  "#3b82f6",
}


# ---------------------------------------------------------------------------
# Token builders
# ---------------------------------------------------------------------------

def build_primitives(brand: dict) -> tuple[dict, dict]:
    """Build the primitive layer from brand input. Returns (primitives, brand_to_primitive)."""
    colors_input = brand.get("colors", {})
    fonts_input = brand.get("fonts", {})
    spacing_base = brand.get("spacing_base", 8)

    # Build primitive color map, resolving name conflicts
    color_primitives: dict[str, dict] = {}
    # Mapping: brand role → primitive name (for semantic layer to reference)
    brand_to_primitive: dict[str, str] = {}

    for role, hex_val in colors_input.items():
        name = color_name_for(hex_val)
        # If name already used by a different hex, append role suffix
        if name in color_primitives and color_primitives[name]["$value"] != hex_val:
            name = f"{name}-{role}"
        color_primitives[name] = {"$value": hex_val, "$type": "color"}
        brand_to_primitive[role] = name

    # Add status colors (only if name not already present)
    for name, hex_val in STATUS_COLORS.items():
        if name not in color_primitives:
            color_primitives[name] = {"$value": hex_val, "$type": "color"}

    # Fonts
    font_primitives = {}
    for role, family in fonts_input.items():
        font_primitives[role] = {"$value": family, "$type": "fontFamily"}

    # Spacing
    spacing = build_spacing(spacing_base)
    spacing_primitives = {
        k: {"$value": v, "$type": "dimension"}
        for k, v in spacing.items()
    }

    return {
        "color": color_primitives,
        "font": font_primitives,
        "spacing": spacing_primitives,
    }, brand_to_primitive


def build_semantic(brand: dict, brand_to_primitive: dict) -> dict:
    """Build the semantic layer."""
    fonts_input = brand.get("fonts", {})

    # Map brand color roles to semantic names
    semantic_color_roles = {
        "primary":   "primary",
        "secondary": "secondary",
        "accent":    "accent",
        "surface":   "surface",
        "text":      "text",
    }

    color_semantics: dict[str, dict] = {}
    for brand_role, semantic_role in semantic_color_roles.items():
        if brand_role in brand_to_primitive:
            prim = brand_to_primitive[brand_role]
            color_semantics[semantic_role] = {
                "$value": f"{{primitive.color.{prim}}}",
                "$type": "color",
            }

    # Status semantics always present
    color_semantics["success"] = {"$value": "{primitive.color.green-600}", "$type": "color"}
    color_semantics["warning"] = {"$value": "{primitive.color.amber-500}", "$type": "color"}
    color_semantics["error"]   = {"$value": "{primitive.color.red-600}",   "$type": "color"}
    color_semantics["info"]    = {"$value": "{primitive.color.blue-500}",  "$type": "color"}

    # Font semantics
    font_semantics: dict[str, dict] = {}
    font_role_map = {"display": "heading", "body": "body"}
    for prim_role in fonts_input:
        sem_name = font_role_map.get(prim_role) or prim_role
        font_semantics[sem_name] = {
            "$value": f"{{primitive.font.{prim_role}}}",
            "$type": "fontFamily",
        }

    return {
        "color": color_semantics,
        "font": font_semantics,
    }


def build_components() -> dict:
    """Build the component layer (fixed structure, references semantic tokens)."""
    return {
        "button": {
            "bg":        {"$value": "{semantic.color.primary}", "$type": "color"},
            "text":      {"$value": "#ffffff",                  "$type": "color"},
            "radius":    {"$value": "6px",                      "$type": "dimension"},
            "padding-x": {"$value": "{primitive.spacing.3}",    "$type": "dimension"},
            "padding-y": {"$value": "{primitive.spacing.1}",    "$type": "dimension"},
        },
        "card": {
            "bg":      {"$value": "{semantic.color.surface}", "$type": "color"},
            "border":  {"$value": "#e2e8f0",                  "$type": "color"},
            "radius":  {"$value": "8px",                      "$type": "dimension"},
            "padding": {"$value": "{primitive.spacing.3}",    "$type": "dimension"},
            "shadow":  {"$value": "0 1px 3px rgba(0,0,0,0.1)", "$type": "shadow"},
        },
        "input": {
            "bg":      {"$value": "#ffffff",                               "$type": "color"},
            "border":  {"$value": "#d1d5db",                               "$type": "color"},
            "radius":  {"$value": "6px",                                   "$type": "dimension"},
            "padding": {"$value": "{primitive.spacing.1} {primitive.spacing.2}", "$type": "dimension"},
        },
    }


# ---------------------------------------------------------------------------
# CSS custom properties generator
# ---------------------------------------------------------------------------

def resolve_reference(value: str, prim_colors: dict, prim_fonts: dict,
                       prim_spacing: dict, sem_colors: dict, sem_fonts: dict) -> str:
    """
    Resolve a DTCG reference like {primitive.color.blue-600} to a CSS var()
    or return the raw value if it's not a reference.
    """
    value = value.strip()
    if not (value.startswith("{") and value.endswith("}")):
        return value

    # Handle space-separated references (e.g. "{primitive.spacing.1} {primitive.spacing.2}")
    parts = value.split()
    if len(parts) > 1:
        resolved = []
        for part in parts:
            resolved.append(resolve_reference(part, prim_colors, prim_fonts,
                                              prim_spacing, sem_colors, sem_fonts))
        return " ".join(resolved)

    ref = value[1:-1]  # strip braces
    segments = ref.split(".")

    if segments[0] == "primitive":
        layer = segments[1]
        key = ".".join(segments[2:])
        if layer == "color":
            return f"var(--color-{key})"
        if layer == "font":
            return f"var(--font-{key})"
        if layer == "spacing":
            return f"var(--space-{key})"
    elif segments[0] == "semantic":
        layer = segments[1]
        key = ".".join(segments[2:])
        if layer == "color":
            return f"var(--color-{key})"
        if layer == "font":
            return f"var(--font-{key})"

    # Fallback: return as-is
    return value


def token_to_css_var(layer: str, group: str, name: str) -> str:
    """Derive the CSS variable name from token path."""
    if layer in ("primitive", "semantic"):
        if group == "color":
            return f"--color-{name}"
        if group == "font":
            return f"--font-{name}"
        if group == "spacing":
            return f"--space-{name}"
    if layer == "component":
        return f"--{group}-{name}"
    return f"--{layer}-{group}-{name}"


def font_value_to_css(value: str) -> str:
    """Wrap a font family name in quotes and append fallback stack."""
    lower = value.lower()
    # Already a var() reference — leave alone
    if value.startswith("var("):
        return value
    # Generic keyword
    if value in ("serif", "sans-serif", "monospace", "cursive", "fantasy"):
        return value
    # Check for likely serif vs sans-serif
    serif_keywords = ("playfair", "georgia", "times", "garamond", "merriweather",
                      "lora", "eb garamond", "cormorant")
    fallback = "serif" if any(k in lower for k in serif_keywords) else "sans-serif"
    return f"'{value}', {fallback}"


def build_css(primitives: dict, semantic: dict, components: dict) -> str:
    """Generate CSS custom properties from token layers."""
    prim_colors  = primitives.get("color", {})
    prim_fonts   = primitives.get("font", {})
    prim_spacing = primitives.get("spacing", {})
    sem_colors   = semantic.get("color", {})
    sem_fonts    = semantic.get("font", {})

    lines = [":root {"]

    def add_comment(text: str):
        lines.append(f"\n  /* {text} */")

    def add_var(var_name: str, css_value: str):
        lines.append(f"  {var_name}: {css_value};")

    # ---- Primitive colors ----
    add_comment("Primitive — Colors")
    for name, token in prim_colors.items():
        add_var(f"--color-{name}", token["$value"])

    # ---- Primitive fonts ----
    add_comment("Primitive — Fonts")
    for name, token in prim_fonts.items():
        css_val = font_value_to_css(token["$value"])
        add_var(f"--font-{name}", css_val)

    # ---- Primitive spacing ----
    add_comment("Primitive — Spacing")
    for name, token in prim_spacing.items():
        add_var(f"--space-{name}", token["$value"])

    # ---- Semantic colors ----
    add_comment("Semantic — Colors")
    for name, token in sem_colors.items():
        css_val = resolve_reference(token["$value"], prim_colors, prim_fonts,
                                    prim_spacing, sem_colors, sem_fonts)
        add_var(f"--color-{name}", css_val)

    # ---- Semantic fonts ----
    add_comment("Semantic — Fonts")
    for name, token in sem_fonts.items():
        raw = token["$value"]
        css_val = resolve_reference(raw, prim_colors, prim_fonts,
                                    prim_spacing, sem_colors, sem_fonts)
        if not css_val.startswith("var("):
            css_val = font_value_to_css(css_val)
        add_var(f"--font-{name}", css_val)

    # ---- Component tokens ----
    for comp_name, comp_tokens in components.items():
        add_comment(f"Component — {comp_name.capitalize()}")
        for prop, token in comp_tokens.items():
            css_val = resolve_reference(token["$value"], prim_colors, prim_fonts,
                                        prim_spacing, sem_colors, sem_fonts)
            add_var(f"--{comp_name}-{prop}", css_val)

    lines.append("}\n")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate W3C DTCG brand tokens + CSS custom properties from a brand-input.json file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  py scripts/generate-tokens.py brand-input.json
  py scripts/generate-tokens.py brand-input.json --output-dir ./tokens
        """,
    )
    parser.add_argument(
        "input",
        help="Path to brand-input.json",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for output files (default: same directory as input file)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    input_path = os.path.abspath(args.input)
    if not os.path.isfile(input_path):
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as fh:
        brand = json.load(fh)

    output_dir = os.path.abspath(args.output_dir) if args.output_dir else os.path.dirname(input_path)
    os.makedirs(output_dir, exist_ok=True)

    # Build layers
    primitives, brand_to_primitive = build_primitives(brand)
    semantic = build_semantic(brand, brand_to_primitive)
    components = build_components()

    # Assemble DTCG token file
    token_doc = {
        "$schema": "https://design-tokens.github.io/community-group/format/",
        "primitive": primitives,
        "semantic": semantic,
        "component": components,
    }

    tokens_path = os.path.join(output_dir, "brand-tokens.json")
    css_path = os.path.join(output_dir, "brand.css")

    with open(tokens_path, "w", encoding="utf-8") as fh:
        json.dump(token_doc, fh, indent=2)
        fh.write("\n")

    css_content = build_css(primitives, semantic, components)
    with open(css_path, "w", encoding="utf-8") as fh:
        fh.write(css_content)

    # Summary counts
    n_prim = (
        len(primitives.get("color", {}))
        + len(primitives.get("font", {}))
        + len(primitives.get("spacing", {}))
    )
    n_sem = len(semantic.get("color", {})) + len(semantic.get("font", {}))
    n_comp = sum(len(v) for v in components.values())

    print(f"Generated {n_prim} primitives, {n_sem} semantic, {n_comp} component tokens")
    print(f"  -> {tokens_path}")
    print(f"  -> {css_path}")


if __name__ == "__main__":
    main()
