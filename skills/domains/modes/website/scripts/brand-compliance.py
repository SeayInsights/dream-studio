"""
brand-compliance.py — Score HTML file against brand-tokens.json.

Usage:
    py scripts/brand-compliance.py brand-tokens.json output.html

Exit code 0 if score >= 70, exit code 1 if score < 70.
"""

import argparse
import json
import math
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def parse_hex(color_str: str):
    """Convert 3-digit or 6-digit hex string to (r, g, b) tuple."""
    s = color_str.strip().lstrip("#")
    if len(s) == 3:
        s = s[0] * 2 + s[1] * 2 + s[2] * 2
    if len(s) != 6:
        return None
    try:
        r = int(s[0:2], 16)
        g = int(s[2:4], 16)
        b = int(s[4:6], 16)
        return (r, g, b)
    except ValueError:
        return None


def parse_rgb(color_str: str):
    """Parse rgb(r, g, b) or rgba(r, g, b, a) to (r, g, b)."""
    m = re.match(
        r"rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)", color_str.strip(), re.IGNORECASE
    )
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def parse_hsl(color_str: str):
    """Parse hsl(h, s%, l%) to approximate (r, g, b)."""
    m = re.match(
        r"hsla?\(\s*([\d.]+)\s*,\s*([\d.]+)%\s*,\s*([\d.]+)%",
        color_str.strip(),
        re.IGNORECASE,
    )
    if not m:
        return None
    h = float(m.group(1)) / 360.0
    s = float(m.group(2)) / 100.0
    l = float(m.group(3)) / 100.0

    if s == 0:
        val = int(l * 255)
        return (val, val, val)

    def hue_to_rgb(p, q, t):
        if t < 0:
            t += 1
        if t > 1:
            t -= 1
        if t < 1 / 6:
            return p + (q - p) * 6 * t
        if t < 1 / 2:
            return q
        if t < 2 / 3:
            return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r = int(hue_to_rgb(p, q, h + 1 / 3) * 255)
    g = int(hue_to_rgb(p, q, h) * 255)
    b = int(hue_to_rgb(p, q, h - 1 / 3) * 255)
    return (r, g, b)


def color_str_to_rgb(color_str: str):
    """Try to parse any color string to (r, g, b)."""
    s = color_str.strip().lower()
    if s.startswith("#"):
        return parse_hex(s)
    if s.startswith("rgba"):
        return parse_rgb(s)
    if s.startswith("rgb"):
        return parse_rgb(s)
    if s.startswith("hsla") or s.startswith("hsl"):
        return parse_hsl(s)
    # Named whites/blacks
    if s in ("white", "#fff", "#ffffff"):
        return (255, 255, 255)
    if s in ("black", "#000", "#000000"):
        return (0, 0, 0)
    return None


def rgb_distance(c1, c2) -> float:
    """Euclidean distance in RGB space."""
    return math.sqrt(
        (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2
    )


# ---------------------------------------------------------------------------
# HTML extraction helpers
# ---------------------------------------------------------------------------

def _line_index(html: str) -> list:
    """Return list of character offsets at start of each line."""
    offsets = [0]
    for i, ch in enumerate(html):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _char_to_line(char_offset: int, line_index: list) -> int:
    """Return 1-based line number for a character offset."""
    lo, hi = 0, len(line_index) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if line_index[mid] <= char_offset:
            lo = mid
        else:
            hi = mid - 1
    return lo + 1


# Regex patterns for color extraction
_HEX_RE = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB_RE = re.compile(r"rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+(?:\s*,\s*[\d.]+)?\s*\)", re.IGNORECASE)
_HSL_RE = re.compile(r"hsla?\(\s*[\d.]+\s*,\s*[\d.]+%\s*,\s*[\d.]+%(?:\s*,\s*[\d.]+)?\s*\)", re.IGNORECASE)

# CSS property context — colors usually appear after : in style attributes or rules
_STYLE_BLOCK_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
_INLINE_STYLE_RE = re.compile(r'style\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)


def _extract_style_regions(html: str) -> list:
    """Return list of (css_text, base_char_offset) for all style regions."""
    regions = []
    for m in _STYLE_BLOCK_RE.finditer(html):
        regions.append((m.group(1), m.start(1)))
    for m in _INLINE_STYLE_RE.finditer(html):
        regions.append((m.group(1), m.start(1)))
    return regions


def extract_colors(html: str) -> list:
    """
    Return list of dicts: {raw, rgb, line}.
    Skips transparent / currentColor.
    White and black are included but flagged as always_brand.
    """
    line_idx = _line_index(html)
    results = []
    skip_values = {"transparent", "currentcolor", "inherit", "none", "initial", "unset"}

    for css_text, base_offset in _extract_style_regions(html):
        for pattern in (_HEX_RE, _RGB_RE, _HSL_RE):
            for m in pattern.finditer(css_text):
                raw = m.group(0).strip()
                if raw.lower() in skip_values:
                    continue
                rgb = color_str_to_rgb(raw)
                if rgb is None:
                    continue
                char_pos = base_offset + m.start()
                line = _char_to_line(char_pos, line_idx)
                results.append({"raw": raw, "rgb": rgb, "line": line})

    return results


def extract_fonts(html: str) -> list:
    """
    Return list of dicts: {family, line}.
    Extracts font-family declarations from style blocks and inline styles.
    """
    line_idx = _line_index(html)
    results = []
    # Match font-family: ... up to ; or end of a style block rule.
    # Value may contain quoted strings, so allow any char except ; and {}.
    _FONT_FAMILY_RE = re.compile(
        r"font-family\s*:\s*([^;{}]+)", re.IGNORECASE
    )

    for css_text, base_offset in _extract_style_regions(html):
        for m in _FONT_FAMILY_RE.finditer(css_text):
            value = m.group(1).strip().rstrip(";").strip()
            # Split comma-separated list, normalize each (strip surrounding quotes)
            families = [
                f.strip().strip("\"'").strip()
                for f in value.split(",")
                if f.strip()
            ]
            char_pos = base_offset + m.start()
            line = _char_to_line(char_pos, line_idx)
            results.append({"families": families, "raw": value, "line": line})

    return results


def extract_spacing(html: str) -> list:
    """
    Return list of dicts: {value_px, raw, line}.
    Extracts all margin/padding px values.
    """
    line_idx = _line_index(html)
    results = []
    _SPACING_PROP_RE = re.compile(
        r"(?:margin|padding)(?:-(?:top|right|bottom|left))?\s*:\s*([^;\"'{}]+)",
        re.IGNORECASE,
    )
    _PX_VALUE_RE = re.compile(r"([\d.]+)px")

    for css_text, base_offset in _extract_style_regions(html):
        for prop_m in _SPACING_PROP_RE.finditer(css_text):
            value_str = prop_m.group(1)
            char_pos = base_offset + prop_m.start()
            line = _char_to_line(char_pos, line_idx)
            for px_m in _PX_VALUE_RE.finditer(value_str):
                px_val = float(px_m.group(1))
                results.append({"value_px": px_val, "raw": px_m.group(0), "line": line})

    return results


def extract_css_vars(html: str) -> tuple:
    """
    Return (var_refs, total_declarations).
    var_refs = count of var(--...) usages
    total_declarations = count of all CSS property declarations
    """
    _VAR_RE = re.compile(r"var\(--[\w-]+\)", re.IGNORECASE)
    _DECL_RE = re.compile(r"[\w-]+\s*:\s*[^;{}]+", re.IGNORECASE)

    var_count = 0
    decl_count = 0

    for css_text, _ in _extract_style_regions(html):
        var_count += len(_VAR_RE.findall(css_text))
        decl_count += len(_DECL_RE.findall(css_text))

    return var_count, decl_count


# ---------------------------------------------------------------------------
# Brand token loading
# ---------------------------------------------------------------------------

def load_brand_tokens(path: str) -> dict:
    """Parse brand-tokens.json and return structured dict."""
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = json.load(f)

    tokens = {
        "colors": [],       # list of (r, g, b)
        "fonts": [],        # list of family name strings
        "spacing_base": 8,  # px base for spacing scale
        "css_vars": set(),  # set of --var-name strings
    }

    # --- Colors ---
    # Support flat list, nested dict, or common token shapes
    def _collect_colors(obj):
        if isinstance(obj, str):
            rgb = color_str_to_rgb(obj)
            if rgb:
                tokens["colors"].append(rgb)
        elif isinstance(obj, list):
            for item in obj:
                _collect_colors(item)
        elif isinstance(obj, dict):
            # Common token shapes: {value: "#hex"}, {color: "#hex"}, or direct key-value
            for k, v in obj.items():
                if k.lower() in ("value", "color", "hex", "default"):
                    _collect_colors(v)
                elif isinstance(v, (str, dict, list)):
                    _collect_colors(v)

    color_data = (
        raw.get("colors")
        or raw.get("color")
        or raw.get("palette")
        or raw.get("brand", {}).get("colors")
        or {}
    )
    _collect_colors(color_data)

    # Always include white and black
    tokens["colors"].append((255, 255, 255))
    tokens["colors"].append((0, 0, 0))

    # --- Fonts ---
    font_data = (
        raw.get("fonts")
        or raw.get("typography")
        or raw.get("font")
        or raw.get("brand", {}).get("fonts")
        or {}
    )

    def _collect_fonts(obj):
        if isinstance(obj, str):
            tokens["fonts"].append(obj.strip().strip("\"'"))
        elif isinstance(obj, list):
            for item in obj:
                _collect_fonts(item)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in ("family", "font-family", "display", "body", "heading", "value"):
                    _collect_fonts(v)
                elif isinstance(v, (str, dict, list)):
                    _collect_fonts(v)

    _collect_fonts(font_data)

    # --- Spacing base ---
    spacing_data = (
        raw.get("spacing")
        or raw.get("space")
        or raw.get("brand", {}).get("spacing")
        or {}
    )
    if isinstance(spacing_data, dict):
        base = spacing_data.get("base") or spacing_data.get("unit")
        if base is not None:
            try:
                val = float(str(base).replace("px", "").strip())
                if val > 0:
                    tokens["spacing_base"] = val
            except ValueError:
                pass
    elif isinstance(spacing_data, (int, float)):
        tokens["spacing_base"] = float(spacing_data)

    # --- CSS custom properties ---
    def _collect_vars(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                var_name = f"--{k}" if not k.startswith("--") else k
                tokens["css_vars"].add(var_name)
                _collect_vars(v, prefix=k)

    vars_data = (
        raw.get("cssVariables")
        or raw.get("css_variables")
        or raw.get("variables")
        or raw.get("vars")
        or {}
    )
    _collect_vars(vars_data)

    return tokens


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

_SYSTEM_FONT_STACKS = {
    "sans-serif", "serif", "monospace", "cursive", "fantasy",
    "system-ui", "-apple-system", "blinkmacsystemfont",
    "segoe ui", "helvetica neue", "arial", "verdana", "georgia",
    "times new roman", "courier new", "inherit", "initial", "unset",
}

_ALWAYS_BRAND_COLORS = {(255, 255, 255), (0, 0, 0)}


def score_colors(html: str, tokens: dict) -> tuple:
    """
    Returns (score, max=40, details_str, violations).
    """
    colors = extract_colors(html)
    if not colors:
        return 40, 40, "No colors found — full score", []

    brand_colors = tokens["colors"]
    violations = []

    on_brand = 0
    close = 0
    off_brand_count = 0

    for entry in colors:
        rgb = entry["rgb"]
        line = entry["line"]
        raw = entry["raw"]

        if rgb in _ALWAYS_BRAND_COLORS:
            on_brand += 1
            continue

        if not brand_colors:
            off_brand_count += 1
            violations.append({
                "type": "color",
                "line": line,
                "found": raw,
                "nearest_brand": "none",
                "distance": -1,
            })
            continue

        dists = [(rgb_distance(rgb, bc), bc) for bc in brand_colors]
        dists.sort(key=lambda x: x[0])
        nearest_dist, nearest_rgb = dists[0]

        nearest_hex = "#{:02x}{:02x}{:02x}".format(*nearest_rgb)

        if nearest_dist <= 10:
            on_brand += 1
        elif nearest_dist <= 30:
            close += 1
            violations.append({
                "type": "color",
                "line": line,
                "found": raw,
                "nearest_brand": nearest_hex,
                "distance": round(nearest_dist, 1),
                "severity": "close",
            })
        else:
            off_brand_count += 1
            violations.append({
                "type": "color",
                "line": line,
                "found": raw,
                "nearest_brand": nearest_hex,
                "distance": round(nearest_dist, 1),
                "severity": "off-brand",
            })

    total = len(colors)
    # Score: full for on-brand, half for close, zero for off-brand
    effective = on_brand + close * 0.5
    raw_score = 40 * (effective / total) if total > 0 else 40
    score = round(min(40, raw_score))

    details = f"{on_brand}/{total} on-brand, {close} close, {off_brand_count} off-brand"
    return score, 40, details, violations


def score_fonts(html: str, tokens: dict) -> tuple:
    """Returns (score, max=25, details_str, violations)."""
    font_entries = extract_fonts(html)
    if not font_entries:
        return 25, 25, "No font declarations found — full score", []

    brand_fonts_lower = {f.lower() for f in tokens["fonts"]}
    violations = []
    total_primary = 0
    brand_matches = 0

    for entry in font_entries:
        families = entry["families"]
        line = entry["line"]

        # Primary font = first non-system-stack family
        primary = None
        for fam in families:
            if fam.lower() not in _SYSTEM_FONT_STACKS:
                primary = fam
                break

        if primary is None:
            # All system fonts — that's OK, skip
            continue

        # var(--...) font references count as on-brand — they delegate to a token
        if primary.lower().startswith("var("):
            brand_matches += 1
            total_primary += 1
            continue

        total_primary += 1
        if primary.lower() in brand_fonts_lower:
            brand_matches += 1
        else:
            expected = tokens["fonts"][0] if tokens["fonts"] else "a brand font"
            violations.append({
                "type": "font",
                "line": line,
                "found": primary,
                "expected": expected,
            })

    if total_primary == 0:
        return 25, 25, "Only system fonts — full score", []

    score = round(25 * (brand_matches / total_primary))
    if brand_matches == total_primary:
        details = "All fonts match brand"
    else:
        details = f"{brand_matches}/{total_primary} font declarations match brand"
    return score, 25, details, violations


def score_spacing(html: str, tokens: dict) -> tuple:
    """Returns (score, max=20, details_str, violations)."""
    spacing_vals = extract_spacing(html)
    if not spacing_vals:
        return 20, 20, "No spacing values found — full score", []

    base = tokens["spacing_base"]
    # Build scale: multiples of base up to 200px
    scale = [base * i for i in range(1, int(200 / base) + 1)]

    on_grid = 0
    violations = []

    for entry in spacing_vals:
        val = entry["value_px"]
        line = entry["line"]
        raw = entry["raw"]

        nearest = min(scale, key=lambda s: abs(s - val))
        diff = abs(val - nearest)

        if diff <= 2:
            on_grid += 1
        else:
            violations.append({
                "type": "spacing",
                "line": line,
                "found": raw,
                "nearest_grid": f"{nearest:.0f}px",
            })

    total = len(spacing_vals)
    score = round(20 * (on_grid / total)) if total > 0 else 20
    details = f"{on_grid}/{total} values on-grid (base={base:.0f}px)"
    return score, 20, details, violations


def score_tokens(html: str) -> tuple:
    """Returns (score, max=15, details_str)."""
    var_refs, total_decls = extract_css_vars(html)

    if total_decls == 0:
        return 0, 15, "No CSS declarations found"

    # var_refs / total_decls ratio, capped at 15
    ratio = var_refs / total_decls
    raw_score = 15 * ratio
    score = round(min(15, raw_score))

    hardcoded = total_decls - var_refs
    details = f"{var_refs} var() references, {hardcoded} hardcoded"
    return score, 15, details


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Score an HTML file against brand-tokens.json."
    )
    parser.add_argument("brand_file", help="Path to brand-tokens.json")
    parser.add_argument("html_file", help="Path to HTML file")
    args = parser.parse_args()

    brand_path = Path(args.brand_file)
    html_path = Path(args.html_file)

    if not brand_path.exists():
        print(f"Error: brand file not found: {brand_path}", file=sys.stderr)
        sys.exit(2)
    if not html_path.exists():
        print(f"Error: HTML file not found: {html_path}", file=sys.stderr)
        sys.exit(2)

    tokens = load_brand_tokens(str(brand_path))
    html = html_path.read_text(encoding="utf-8", errors="replace")

    # --- Score each dimension ---
    color_score, color_max, color_details, color_violations = score_colors(html, tokens)
    font_score, font_max, font_details, font_violations = score_fonts(html, tokens)
    spacing_score, spacing_max, spacing_details, spacing_violations = score_spacing(html, tokens)
    token_score, token_max, token_details = score_tokens(html)

    total = color_score + font_score + spacing_score + token_score
    all_violations = color_violations + font_violations + spacing_violations

    # --- Build JSON output ---
    output = {
        "file": str(html_path),
        "brand_file": str(brand_path),
        "score": total,
        "breakdown": {
            "color_compliance": {
                "score": color_score,
                "max": color_max,
                "details": color_details,
            },
            "font_compliance": {
                "score": font_score,
                "max": font_max,
                "details": font_details,
            },
            "spacing_consistency": {
                "score": spacing_score,
                "max": spacing_max,
                "details": spacing_details,
            },
            "token_usage": {
                "score": token_score,
                "max": token_max,
                "details": token_details,
            },
        },
        "violations": all_violations,
    }

    # --- Print JSON ---
    print(json.dumps(output, indent=2))

    # --- Print human-readable summary ---
    print()
    print(f"Brand Compliance: {total}/100")
    print(f"  Color:   {color_score}/{color_max} ({color_details})")
    print(f"  Font:    {font_score}/{font_max} ({font_details})")
    print(f"  Spacing: {spacing_score}/{spacing_max} ({spacing_details})")
    print(f"  Tokens:  {token_score}/{token_max} ({token_details})")

    if all_violations:
        print()
        print("Top violations:")
        for v in all_violations[:10]:
            vtype = v.get("type")
            line = v.get("line", "?")
            if vtype == "color":
                sev = v.get("severity", "off-brand")
                print(
                    f"  L{line}: {sev.capitalize()} color {v['found']}"
                    f" (nearest: {v['nearest_brand']}, dE={v['distance']})"
                )
            elif vtype == "font":
                print(
                    f"  L{line}: Non-brand font '{v['found']}'"
                    f" (expected: '{v['expected']}')"
                )
            elif vtype == "spacing":
                print(
                    f"  L{line}: Off-grid spacing {v['found']}"
                    f" (nearest: {v['nearest_grid']})"
                )
    else:
        print()
        print("No violations found.")

    sys.exit(0 if total >= 70 else 1)


if __name__ == "__main__":
    main()
