"""Action execution engine with simulation and validation."""

from __future__ import annotations
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from .model import RepoAction, ActionType


@dataclass
class ActionExecution:
    """Record of action execution with before/after state."""

    execution_id: str
    action_id: str
    repo: str
    target: str
    action_type: str

    status: str  # success | failed | partial
    before_state: Dict[str, any] = field(default_factory=dict)
    after_state: Dict[str, any] = field(default_factory=dict)

    execution_result: Dict[str, any] = field(default_factory=dict)
    diff_summary: Dict[str, any] = field(default_factory=dict)

    timestamp: str = ""


class ActionExecutor:
    """Execute repository actions with simulation and validation."""

    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path)
        self.executions: List[ActionExecution] = []

    def validate_action(self, action: RepoAction) -> tuple[bool, str]:
        """Validate action before execution.

        Args:
            action: Action to validate

        Returns:
            (is_valid, error_message)
        """
        # 1. Ensure traceability exists
        if not action.is_traceable():
            return False, "Action not traceable to system output"

        # 2. Ensure target exists (for file/module operations)
        if action.action_type in [ActionType.REFACTOR, ActionType.INSTRUMENT, ActionType.FIX]:
            target_path = self._resolve_target_path(action.target)
            if target_path and not target_path.exists():
                return False, f"Target file does not exist: {action.target}"

        # 3. Dependency safety check (basic)
        # For now, just warn on high-risk actions
        if action.risk_level.value == "high":
            # Would check dependency graph here
            pass

        return True, ""

    def generate_execution_plan(self, action: RepoAction) -> Dict[str, any]:
        """Generate structured execution plan for action.

        Args:
            action: Action to plan

        Returns:
            Execution plan dict
        """
        plan = {
            "action_id": action.action_id,
            "action_type": action.action_type.value,
            "target": action.target,
            "steps": [],
            "patches": [],
            "expected_changes": {},
        }

        if action.action_type == ActionType.INSTRUMENT:
            plan["steps"] = self._plan_instrument(action)
        elif action.action_type == ActionType.REFACTOR:
            plan["steps"] = self._plan_refactor(action)
        elif action.action_type == ActionType.FIX:
            plan["steps"] = self._plan_fix(action)
        elif action.action_type == ActionType.EXTRACT:
            plan["steps"] = self._plan_extract(action)
        elif action.action_type == ActionType.CONSOLIDATE:
            plan["steps"] = self._plan_consolidate(action)
        elif action.action_type == ActionType.DELETE:
            plan["steps"] = self._plan_delete(action)

        return plan

    def simulate_execution(self, action: RepoAction) -> ActionExecution:
        """Simulate action execution and compute expected changes.

        Args:
            action: Action to simulate

        Returns:
            ActionExecution with simulated results
        """
        execution_id = str(uuid.uuid4())[:8]

        # Capture before state
        before_state = self._capture_state(action)

        # Generate execution plan
        plan = self.generate_execution_plan(action)

        # Simulate changes (without actually modifying files)
        expected_after_state = self._simulate_changes(action, before_state, plan)

        # Compute diff
        diff = self._compute_diff(before_state, expected_after_state)

        execution = ActionExecution(
            execution_id=execution_id,
            action_id=action.action_id,
            repo=action.repo,
            target=action.target,
            action_type=action.action_type.value,
            status="simulated",
            before_state=before_state,
            after_state=expected_after_state,
            execution_result=plan,
            diff_summary=diff,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        self.executions.append(execution)
        return execution

    def _capture_state(self, action: RepoAction) -> Dict[str, any]:
        """Capture current state before execution.

        Args:
            action: Action to capture state for

        Returns:
            State dict
        """
        state = {
            "coupling_score": action.rationale.get("coupling_score", 0),
            "instrumentation_coverage": 0.0,  # Would query from coverage audit
            "orphan_decision_count": 0,  # Would query from integrity audit
            "risk_score": 0.0,  # Would query from audit system
            "module_exists": True,
            "loc": 0,
        }

        # Try to get actual file metrics
        target_path = self._resolve_target_path(action.target)
        if target_path and target_path.exists():
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                    state["loc"] = sum(1 for line in lines if line.strip())
            except Exception:
                pass

        return state

    def _simulate_changes(
        self, action: RepoAction, before_state: Dict[str, any], plan: Dict[str, any]
    ) -> Dict[str, any]:
        """Simulate expected changes from action.

        Args:
            action: Action being executed
            before_state: State before execution
            plan: Execution plan

        Returns:
            Expected after state
        """
        after_state = before_state.copy()

        if action.action_type == ActionType.REFACTOR:
            # Expect coupling reduction
            coupling = before_state.get("coupling_score", 0)
            reduction = min(coupling * 0.3, 10)  # 30% reduction or 10 points
            after_state["coupling_score"] = max(0, coupling - reduction)

        elif action.action_type == ActionType.INSTRUMENT:
            # Expect coverage increase
            coverage = before_state.get("instrumentation_coverage", 0.0)
            after_state["instrumentation_coverage"] = min(1.0, coverage + 0.01)

        elif action.action_type == ActionType.FIX:
            # Expect orphan count reduction
            orphans = before_state.get("orphan_decision_count", 0)
            after_state["orphan_decision_count"] = max(0, orphans - 1)

        elif action.action_type == ActionType.EXTRACT:
            # Expect coupling reduction and module split
            coupling = before_state.get("coupling_score", 0)
            after_state["coupling_score"] = max(0, coupling - 5)
            after_state["module_count"] = 2  # Split into 2 modules

        return after_state

    def _compute_diff(
        self, before_state: Dict[str, any], after_state: Dict[str, any]
    ) -> Dict[str, any]:
        """Compute state diff.

        Args:
            before_state: State before
            after_state: State after

        Returns:
            Diff summary
        """
        diff = {"changed_metrics": [], "deltas": {}}

        for key in before_state:
            if key in after_state:
                before_val = before_state[key]
                after_val = after_state[key]

                if before_val != after_val:
                    diff["changed_metrics"].append(key)
                    if isinstance(before_val, (int, float)) and isinstance(after_val, (int, float)):
                        delta = after_val - before_val
                        diff["deltas"][key] = {
                            "before": before_val,
                            "after": after_val,
                            "delta": delta,
                        }

        return diff

    def _plan_instrument(self, action: RepoAction) -> List[str]:
        """Plan instrumentation action.

        Args:
            action: Instrument action

        Returns:
            List of plan steps
        """
        coverage_id = action.coverage_finding_ids[0] if action.coverage_finding_ids else ""
        return [
            f"Locate decision point at {coverage_id}",
            f"Insert emit_decision() call",
            f"Add reasoning dict with policy reference",
            f"Verify decision emission",
        ]

    def _plan_refactor(self, action: RepoAction) -> List[str]:
        """Plan refactor action.

        Args:
            action: Refactor action

        Returns:
            List of plan steps
        """
        return [
            f"Analyze {action.target} coupling",
            f"Identify extraction candidates",
            f"Create new module boundaries",
            f"Move dependent code",
            f"Update imports",
            f"Verify tests pass",
        ]

    def _plan_fix(self, action: RepoAction) -> List[str]:
        """Plan fix action.

        Args:
            action: Fix action

        Returns:
            List of plan steps
        """
        decision_id = action.decision_ids[0] if action.decision_ids else ""
        return [
            f"Locate decision emission for {decision_id}",
            f"Find corresponding event emission",
            f"Add event_id parameter to emit_decision()",
            f"Verify causal link created",
        ]

    def _plan_extract(self, action: RepoAction) -> List[str]:
        """Plan extract action.

        Args:
            action: Extract action

        Returns:
            List of plan steps
        """
        return [
            f"Identify {action.target} API surface",
            f"Create new service/library structure",
            f"Move core logic",
            f"Define public API",
            f"Update callers",
            f"Deploy as standalone",
        ]

    def _plan_consolidate(self, action: RepoAction) -> List[str]:
        """Plan consolidate action.

        Args:
            action: Consolidate action

        Returns:
            List of plan steps
        """
        return [
            f"Compare {action.target} implementations across repos",
            f"Identify common interface",
            f"Create shared library",
            f"Migrate repo 1",
            f"Migrate repo 2",
            f"Deprecate duplicates",
        ]

    def _plan_delete(self, action: RepoAction) -> List[str]:
        """Plan delete action.

        Args:
            action: Delete action

        Returns:
            List of plan steps
        """
        return [
            f"Verify {action.target} has no references",
            f"Check git history for usage",
            f"Mark as deprecated",
            f"Wait 1 sprint",
            f"Delete if still unused",
        ]

    def _resolve_target_path(self, target: str) -> Optional[Path]:
        """Resolve target to file path.

        Args:
            target: Target module/file

        Returns:
            Path if resolvable, None otherwise
        """
        # Simple resolution: convert module path to file path
        target_file = target.replace(".", "/") + ".py"
        target_path = self.repo_path / target_file

        if not target_path.exists():
            # Try without .py extension (might be directory)
            target_path = self.repo_path / target.replace(".", "/")

        return target_path if target_path.exists() else None

    def get_executions(self) -> List[ActionExecution]:
        """Get all executions.

        Returns:
            List of executions
        """
        return self.executions
