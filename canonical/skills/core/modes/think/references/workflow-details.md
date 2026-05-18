# Think Mode Workflow - Detailed Sub-Steps

This document contains detailed sub-steps for the think mode workflow. The main SKILL.md provides the high-level workflow; refer here for implementation details.

## Step 1: Clarify

### Clarify Questions Template

Before writing the spec, ask 3-5 targeted questions to surface hidden constraints:

- "Who is the primary user and what's their context when they hit this?"
- "What's the definition of done — what does success look like in 30 days?"
- "Are there constraints I should know about (performance, platform, existing patterns)?"
- "What's explicitly out of scope for this?"
- "Is there existing code/design I should read before speccing this?"

**Important**: Only ask questions where the answer would change the spec. Don't ask for its own sake.

### Step 1b: Research Cache Check

Before starting new research, check the persistent research cache:

1. Run the maintained research cache CLI if available.
2. **If cached AND not stale**: Display prior findings to Director. Ask: "Prior research exists (saved [date], confidence: [level]). Re-research or use existing?"
3. **If cached AND stale**: Note "Prior research exists but is stale (refresh due [date]). Will re-research with prior findings as starting point."
4. **If not cached**: Proceed normally — no prior research exists for this topic

This prevents re-researching the same topics across sessions.

## Step 2: Explore

Generate 2-3 approaches with complete trade-off analysis:
- **Pros**: What makes this approach attractive
- **Cons**: What are the downsides and risks
- **Complexity**: Implementation difficulty (Simple/Medium/Complex)
- **Risk**: What could go wrong (Low/Medium/High)

### Step 2b: Source Quality Check

After collecting research sources, validate quality before proceeding:

1. Run `py interfaces/cli/source_ranker.py` on collected sources (or apply the scoring logic from `skills/domains/research/analysis.yml`)
2. **Check triangulation**: Do you have 3+ independent sources?
3. **Check source tier distribution**: Do you have any Tier 1 sources?
4. **Check for counter-arguments**: Are opposing viewpoints represented?
5. **If confidence < medium**: Flag gaps to Director before writing spec. "Research confidence is LOW — [specific gaps]. Collect more sources before speccing?"
6. **If confidence >= medium**: Note confidence level in spec and proceed

## Step 3: Recommend

Pick one approach with clear rationale explaining:
- Why this approach over the alternatives
- What constraints or priorities drove the decision
- What trade-offs are being accepted

### Step 3b: Risk Pre-population

Before writing the Edge Cases section of the spec:

1. Run `py interfaces/cli/spec_risk_check.py <topic>` to scan gotchas.yml and prior session history
2. Incorporate relevant gotchas as suggested edge cases in the spec
3. If prior sessions encountered issues with this topic, note them in the spec's Assumptions section

This ensures specs learn from past mistakes instead of repeating them.

## Step 4: Spec - Tool Recommendations

**Only if `--recommend-tools` flag is present**

### Process:

1. Extract keywords from user input and spec context (e.g., "video", "processing", "pipeline", "authentication")
2. Call tool search API: `POST /api/discovery/external/tools?query=<keywords>`
3. Filter results: confidence > 0.7 only
4. Limit to top 5 recommendations
5. Append "Recommended Tools" section to spec.md

### Format:

```markdown
## Recommended Tools

- **ffmpeg-python** (95% confidence) - Python bindings for FFmpeg video processing
  - Install: `pip install ffmpeg-python`
  - Why: High match for "video processing" keywords
  - Source: https://github.com/kkroening/ffmpeg-python

- **opencv-python** (88% confidence) - Computer vision and video analysis library
  - Install: `pip install opencv-python`
  - Why: Strong match for "video" and "pipeline" keywords
  - Source: https://opencv.org
```

### Integration Notes:

- **API endpoint**: `/api/discovery/external/tools`
- **Request**: `POST` with query parameter `?query=<space-separated keywords>`
- **Response**: JSON array with `{name, description, install_command, confidence, matched_keywords}`
- The tool_search.py module uses TF-IDF for keyword matching
- Only include tools where confidence >= 0.7 to avoid noise

## Step 4: Spec - Research Findings

**Only if `--research` flag is present**

### Process:

1. Extract research topics from user input and spec context (e.g., "NetworkX vs igraph", "best practices for authentication")
2. Extract focus areas from user input (e.g., "performance", "security", "ease of use", "community support")
3. Call research API: `POST /api/discovery/research` with JSON body:
   ```json
   {
     "topic": "<extracted research topic>",
     "focus_areas": ["<area1>", "<area2>"],
     "max_sources": 10
   }
   ```
4. Filter results: only include sources with tier <= 2 (Tier 1: official docs/repos, Tier 2: reputable blogs/articles)
5. Append "Research Findings" section to spec.md AFTER the decision rationale

### Format:

```markdown
## Research Findings

**Topic:** NetworkX vs igraph for graph analysis
**Confidence:** 0.85 (High) | **Triangulation:** 1.0 (6+ sources)

**Sources:**
- [NetworkX vs igraph benchmark](https://github.com/...) (Tier 1: GitHub)
- [Graph library comparison](https://realpython.com/...) (Tier 2: Blog)
- [NetworkX performance guide](https://networkx.org/...) (Tier 1: Docs)

**Summary:**
NetworkX is more Pythonic and easier to use, but igraph is 2-10x faster for large graphs (>10k nodes). NetworkX has better documentation and community support. igraph requires C dependencies but offers parallel processing. For prototype/analysis work, NetworkX is recommended; for production pipelines with large graphs, igraph is preferred.
```

### Integration Notes:

- **API endpoint**: `/api/discovery/research`
- **Request**: `POST` with JSON body containing `topic`, `focus_areas` (array), and optional `max_sources` (default: 10)
- **Response**: JSON object with:
  ```json
  {
    "topic": "string",
    "confidence": 0.85,
    "triangulation": 1.0,
    "source_count": 3,
    "sources": [
      {"url": "...", "title": "...", "tier": 1, "tier_label": "GitHub"},
      {"url": "...", "title": "...", "tier": 2, "tier_label": "Blog"}
    ],
    "summary": "string"
  }
  ```

### Source Tier Definitions:

- **Tier 1 (Official)**: GitHub repos, official documentation, primary sources
- **Tier 2 (Reputable)**: Established blogs (Real Python, CSS-Tricks, etc.), technical articles
- **Tier 3 (Community)**: Stack Overflow, Reddit, forums (excluded from research output)

### Confidence Thresholds:

- **High (>0.75)**: Strong consensus across high-quality sources
- **Medium (0.5-0.75)**: Good sources but some conflicts or gaps
- **Low (<0.5)**: Few sources or significant disagreement

If confidence < 0.5, flag to Director: "Research confidence is LOW — consider collecting more sources or proceeding with caution"

## Combined Flags Example

When using both `--recommend-tools` and `--research`:

```
Input: "think: --recommend-tools --research Build a graph-based recommendation system"

Output: .planning/specs/graph-recommendation/spec.md
(standard spec content)
...
## Research Findings
(research content as shown above)

## Recommended Tools
(tool recommendations as shown above)
```

The research section should appear first (it informs the decision), followed by tool recommendations (which support implementation).
