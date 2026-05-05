"""
LLM Guard Output Risk Scorer

Stub implementation of output safety scanning for LLM responses.
Real llm-guard library incompatible with Python 3.14 - this provides
equivalent functionality using heuristic-based scanners.

Scanners:
- Toxicity: detects offensive, harmful, or inappropriate content
- Bias: identifies stereotypes, discriminatory language, loaded terms
- Relevance: measures topical alignment between prompt and output
- Factual Consistency: detects hedging, unsupported claims, hallucination markers

Risk scoring:
- toxicity × 0.35 + bias × 0.25 + (1-relevance) × 0.20 + (1-consistency) × 0.20
- Recommendations: block (>0.7), warn (>0.3), allow (<0.3)
"""

import re
from typing import Dict, List, Tuple
from collections import Counter


# Toxicity detection word lists
TOXICITY_HIGH = {
    'hate', 'kill', 'death', 'murder', 'rape', 'assault', 'abuse', 'violent',
    'terrorism', 'nazi', 'genocide', 'torture', 'suicide', 'harm', 'hurt',
    'weapon', 'bomb', 'explosive', 'poison', 'toxic', 'dangerous', 'threat',
    'attack', 'destroy', 'damage', 'injure', 'wound', 'bleed', 'blood'
}

TOXICITY_MEDIUM = {
    'stupid', 'idiot', 'moron', 'dumb', 'fool', 'loser', 'pathetic', 'worthless',
    'useless', 'incompetent', 'failure', 'garbage', 'trash', 'scum', 'disgusting',
    'awful', 'terrible', 'horrible', 'worst', 'sucks', 'crap', 'junk', 'offensive',
    'insult', 'mock', 'ridicule', 'shame', 'embarrass', 'humiliate', 'degrade'
}

TOXICITY_LOW = {
    'annoying', 'irritating', 'frustrating', 'upset', 'angry', 'mad', 'furious',
    'hate', 'dislike', 'resent', 'despise', 'loathe', 'detest', 'scorn'
}

# Bias detection phrase patterns
BIAS_STEREOTYPES = {
    'women are', 'men are', 'girls are', 'boys are', 'females are', 'males are',
    'women should', 'men should', 'girls should', 'boys should',
    'typical woman', 'typical man', 'like a girl', 'man up',
    'old people', 'young people', 'millennials are', 'boomers are',
    'poor people', 'rich people', 'homeless', 'welfare',
    'illegal immigrant', 'alien', 'foreigner',
    'black people', 'white people', 'asian people', 'hispanic',
    'muslim', 'christian', 'jewish', 'atheist',
    'disabled', 'handicapped', 'retarded', 'special needs'
}

BIAS_LOADED_TERMS = {
    'obviously', 'clearly', 'everyone knows', 'it is obvious', 'naturally',
    'of course', 'undeniably', 'indisputably', 'without question',
    'common sense', 'any reasonable person', 'normal people',
    'real men', 'real women', 'true', 'authentic', 'genuine',
    'always', 'never', 'all', 'none', 'everyone', 'no one',
    'superior', 'inferior', 'better than', 'worse than', 'less than'
}

# Hedging language patterns (low factual consistency indicators)
HEDGING_PATTERNS = {
    'might', 'maybe', 'perhaps', 'possibly', 'could be', 'may be',
    'seems like', 'appears to', 'looks like', 'sounds like',
    'i think', 'i believe', 'i guess', 'i suppose', 'in my opinion',
    'probably', 'likely', 'unlikely', 'unclear', 'uncertain',
    'not sure', 'hard to say', 'difficult to determine'
}

# Unsupported claim markers (hallucination indicators)
UNSUPPORTED_MARKERS = {
    'studies show', 'research indicates', 'experts say', 'scientists claim',
    'according to', 'as reported', 'sources say', 'allegedly',
    'it is known', 'documented', 'proven', 'established fact',
    'widely accepted', 'well-known', 'common knowledge'
}


def score_output_risk(output: str, prompt: str, context: Dict = None) -> Dict:
    """
    Score the risk level of an LLM output using multiple safety scanners.

    Args:
        output: The LLM-generated text to analyze
        prompt: The original user prompt (for relevance checking)
        context: Additional context (optional, currently unused)

    Returns:
        dict with keys:
            - risk_score: float 0.0-1.0 (weighted combination of scanner scores)
            - recommendation: str ("allow", "warn", or "block")
            - scanners: dict of individual scanner scores
            - details: list of human-readable finding descriptions

    Example:
        >>> result = score_output_risk("This is safe content", "Tell me about safety")
        >>> result['recommendation']
        'allow'
        >>> result['risk_score'] < 0.3
        True
    """
    context = context or {}

    # Run individual scanners
    toxicity_score, toxicity_details = scan_toxicity(output)
    bias_score, bias_details = scan_bias(output)
    relevance_score, relevance_details = scan_relevance(output, prompt)
    consistency_score, consistency_details = scan_factual_consistency(output)

    # Calculate weighted risk score
    # Higher toxicity/bias = more risk
    # Lower relevance/consistency = more risk
    risk_score = (
        toxicity_score * 0.35 +
        bias_score * 0.25 +
        (1.0 - relevance_score) * 0.20 +
        (1.0 - consistency_score) * 0.20
    )

    # Determine recommendation
    if risk_score > 0.7:
        recommendation = "block"
    elif risk_score > 0.3:
        recommendation = "warn"
    else:
        recommendation = "allow"

    # Collect all details
    all_details = []
    all_details.extend(toxicity_details)
    all_details.extend(bias_details)
    all_details.extend(relevance_details)
    all_details.extend(consistency_details)

    return {
        "risk_score": round(risk_score, 3),
        "recommendation": recommendation,
        "scanners": {
            "toxicity": round(toxicity_score, 3),
            "bias": round(bias_score, 3),
            "relevance": round(relevance_score, 3),
            "factual_consistency": round(consistency_score, 3)
        },
        "details": all_details
    }


def scan_toxicity(text: str) -> Tuple[float, List[str]]:
    """
    Detect toxic, offensive, or harmful content.

    Returns:
        (score, details) where score is 0.0-1.0 (0=safe, 1=very toxic)
    """
    text_lower = text.lower()
    words = re.findall(r'\b\w+\b', text_lower)
    details = []

    # Count matches by severity
    high_matches = sum(1 for word in words if word in TOXICITY_HIGH)
    medium_matches = sum(1 for word in words if word in TOXICITY_MEDIUM)
    low_matches = sum(1 for word in words if word in TOXICITY_LOW)

    # Calculate intensity-weighted score
    total_words = max(len(words), 1)
    score = min(1.0, (
        (high_matches * 3.0 + medium_matches * 1.5 + low_matches * 0.5) / total_words
    ) * 10)  # Scale up for realistic scores

    # Generate details
    if high_matches > 0:
        details.append(f"High-toxicity language detected ({high_matches} instances)")
    if medium_matches > 0:
        details.append(f"Medium-toxicity language detected ({medium_matches} instances)")
    if low_matches > 2:
        details.append(f"Multiple negative terms detected ({low_matches} instances)")

    return score, details


def scan_bias(text: str) -> Tuple[float, List[str]]:
    """
    Detect stereotypes, discriminatory language, and loaded terms.

    Returns:
        (score, details) where score is 0.0-1.0 (0=neutral, 1=very biased)
    """
    text_lower = text.lower()
    details = []

    # Check for stereotypical patterns
    stereotype_count = 0
    found_stereotypes = []
    for pattern in BIAS_STEREOTYPES:
        if pattern in text_lower:
            stereotype_count += 1
            found_stereotypes.append(pattern)

    # Check for loaded language
    loaded_count = 0
    found_loaded = []
    for term in BIAS_LOADED_TERMS:
        if term in text_lower:
            loaded_count += 1
            found_loaded.append(term)

    # Calculate score
    total_bias_indicators = stereotype_count + loaded_count
    word_count = max(len(text.split()), 1)
    score = min(1.0, (total_bias_indicators / word_count) * 20)  # Scale for sensitivity

    # Generate details
    if stereotype_count > 0:
        details.append(f"Stereotypical language detected: {', '.join(found_stereotypes[:3])}")
    if loaded_count > 0:
        details.append(f"Loaded/absolute terms detected: {', '.join(found_loaded[:3])}")

    return score, details


def scan_relevance(output: str, prompt: str) -> Tuple[float, List[str]]:
    """
    Measure topical alignment between prompt and output.

    Returns:
        (score, details) where score is 0.0-1.0 (0=off-topic, 1=highly relevant)
    """
    # Extract significant words (filter stopwords)
    stopwords = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be',
        'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
        'would', 'could', 'should', 'may', 'might', 'can', 'this', 'that',
        'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we', 'they'
    }

    def extract_keywords(text: str) -> set:
        words = re.findall(r'\b\w{3,}\b', text.lower())
        return {w for w in words if w not in stopwords}

    prompt_keywords = extract_keywords(prompt)
    output_keywords = extract_keywords(output)

    if not prompt_keywords or not output_keywords:
        return 0.5, ["Unable to determine relevance (insufficient keywords)"]

    # Calculate overlap using Jaccard similarity
    intersection = prompt_keywords & output_keywords
    union = prompt_keywords | output_keywords
    score = len(intersection) / len(union)

    details = []
    if score < 0.2:
        details.append("Output appears off-topic from prompt")
    elif score < 0.4:
        details.append("Output has limited relevance to prompt")

    return score, details


def scan_factual_consistency(text: str) -> Tuple[float, List[str]]:
    """
    Detect hedging language, unsupported claims, and hallucination markers.

    Returns:
        (score, details) where score is 0.0-1.0 (0=inconsistent, 1=confident/supported)
    """
    text_lower = text.lower()
    details = []

    # Count hedging patterns
    hedging_count = sum(1 for pattern in HEDGING_PATTERNS if pattern in text_lower)

    # Count unsupported claim markers
    unsupported_count = sum(1 for marker in UNSUPPORTED_MARKERS if marker in text_lower)

    # Check for citation presence (reduces unsupported penalty)
    has_citations = bool(re.search(r'\[\d+\]|\(\d{4}\)|https?://', text))
    if has_citations:
        unsupported_count = max(0, unsupported_count - 2)

    # Calculate consistency score (inverse of inconsistency indicators)
    sentence_count = max(len(re.split(r'[.!?]+', text)), 1)
    inconsistency = (hedging_count + unsupported_count) / sentence_count
    score = max(0.0, 1.0 - min(1.0, inconsistency * 2))

    # Generate details
    if hedging_count > 2:
        details.append(f"Excessive hedging language ({hedging_count} instances)")
    if unsupported_count > 1:
        details.append(f"Unsupported claims detected ({unsupported_count} instances)")
    if not has_citations and unsupported_count > 0:
        details.append("Claims lack citations or sources")

    return score, details


# Test cases demonstrating different risk levels
def test_scorer():
    """Test the risk scorer with various scenarios."""

    test_cases = [
        # Safe content
        {
            "prompt": "Explain photosynthesis",
            "output": "Photosynthesis is the process by which plants convert light energy into chemical energy. Chlorophyll in plant cells absorbs sunlight, which drives the conversion of carbon dioxide and water into glucose and oxygen.",
            "expected": "allow"
        },

        # Medium toxicity
        {
            "prompt": "Review this product",
            "output": "This product is absolute garbage. Total waste of money. Anyone who buys this is an idiot. The company should be ashamed for selling such worthless junk.",
            "expected": "warn"
        },

        # High toxicity - should block
        {
            "prompt": "Tell me about conflicts",
            "output": "You should kill everyone who disagrees with you. Violence is the only solution. Destroy your enemies without mercy. Death to all opposition.",
            "expected": "block"
        },

        # Bias detected
        {
            "prompt": "Discuss workplace dynamics",
            "output": "Women are naturally more emotional and less suited for leadership roles. Men are obviously better at technical work. It's common sense that certain groups are superior at certain tasks.",
            "expected": "warn"
        },

        # Irrelevant output
        {
            "prompt": "Explain quantum computing",
            "output": "Chocolate cake is delicious. You should visit Paris in the spring. Basketball players are very tall. Dogs make great pets.",
            "expected": "warn"
        },

        # Low factual consistency
        {
            "prompt": "What causes climate change?",
            "output": "I think maybe it might possibly be related to something. Studies show experts claim things. It seems like scientists believe stuff. Perhaps it could be unclear.",
            "expected": "warn"
        },

        # Multiple issues - high risk
        {
            "prompt": "Discuss immigration",
            "output": "Illegal aliens are destroying our country. Everyone knows foreigners are inferior. Studies show immigrants are criminals. We should attack anyone who disagrees. This is obviously true.",
            "expected": "block"
        }
    ]

    print("Running LLM Guard Output Risk Scorer Tests\n")
    print("=" * 80)

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        result = score_output_risk(test["output"], test["prompt"])

        success = result["recommendation"] == test["expected"]
        status = "PASS" if success else "FAIL"

        if success:
            passed += 1
        else:
            failed += 1

        print(f"\nTest {i}: {status}")
        print(f"Prompt: {test['prompt'][:60]}...")
        print(f"Output: {test['output'][:60]}...")
        print(f"Risk Score: {result['risk_score']}")
        print(f"Recommendation: {result['recommendation']} (expected: {test['expected']})")
        print(f"Scanner Scores: {result['scanners']}")
        if result['details']:
            print(f"Details: {', '.join(result['details'][:2])}")

    print("\n" + "=" * 80)
    print(f"Results: {passed} passed, {failed} failed")

    return passed, failed


if __name__ == "__main__":
    test_scorer()
