"""Attribution coverage health threshold configuration."""

from __future__ import annotations

# Minimum fraction of token.consumed events that must be fully_attributed
# before the dashboard panel is considered healthy. Alert is logged (not raised)
# when coverage drops below this value.
ATTRIBUTION_COVERAGE_MIN: float = 0.90
