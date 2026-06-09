# NEGATIVE fixture: copy of guard's own patterns (the recursive self-reference test)
# Guard SHOULD NOT fire on this (path is in tests/, which is suppressed)
# This proves the recursive case: guard doesn't flag its own documentation

# These are the patterns the guard detects — for documentation purposes:
PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions?",
    r"you\s+are\s+now\s+(?:a|an|my)",
    r"(?:^|\n)\s*system\s*:",
    r"\[INST\]|\[/INST\]",
    r"forget\s+(?:all\s+)?(?:previous|earlier|your)\s+(?:instructions?|commands?|rules?)",
    r"disregard\s+(?:all\s+)?(?:previous|above|prior)",
    r"jailbreak|unchained|unrestricted",
]
