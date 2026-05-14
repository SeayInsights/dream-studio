"""Integration tests for execution graph and workflow integration.

Tests the complete flow:
- Node creation
- Status transitions
- Context compilation
- Event linking
- Output storage
- Token savings measurement

Created: 2026-05-07 (Phase 6)
"""

import unittest
import sys
import tempfile
import gc
from pathlib import Path
from datetime import datetime, timezone

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from core.execution.graph import ExecutionGraphManager
from core.execution.context_compiler import ContextCompiler
from core.execution.workflow_integration import WorkflowGraphIntegration
from core.config.database import DatabaseRuntime
from core.event_store.event_store import EventStore
from core.event_store.studio_db import _connect


def _install_isolated_database(testcase: unittest.TestCase) -> None:
    """Run execution graph integration tests against a migrated temp DB."""
    testcase._tmpdir = tempfile.TemporaryDirectory()
    testcase.db_path = Path(testcase._tmpdir.name) / "studio.db"
    _connect(testcase.db_path).close()
    event_store = EventStore(str(testcase.db_path), validator=None)
    event_store.db.close()
    DatabaseRuntime.reset_instance()
    DatabaseRuntime.get_instance(testcase.db_path)


def _cleanup_isolated_database(testcase: unittest.TestCase) -> None:
    DatabaseRuntime.reset_instance()
    gc.collect()
    testcase._tmpdir.cleanup()


class TestExecutionGraphIntegration(unittest.TestCase):
    """Test execution graph integration end-to-end."""

    def setUp(self):
        """Set up test fixtures."""
        _install_isolated_database(self)
        self.graph = ExecutionGraphManager()
        self.compiler = ContextCompiler()
        self.integration = WorkflowGraphIntegration()

    def tearDown(self):
        """Release the temp DB runtime before the next test."""
        _cleanup_isolated_database(self)

    def test_01_create_project_hierarchy(self):
        """Test creating complete project hierarchy."""
        # Create project
        project_id = self.graph.create_node(
            node_type="project",
            title="Test Project",
            description="Integration test project",
            metadata={"test": True},
        )
        self.assertIsNotNone(project_id)

        # Create PRD
        prd_id = self.graph.create_node(
            node_type="prd",
            title="Test PRD",
            parent_id=project_id,
            metadata={"requirements": ["Req 1", "Req 2"], "acceptance_criteria": ["AC 1", "AC 2"]},
        )
        self.assertIsNotNone(prd_id)

        # Create plan
        plan_id = self.graph.create_node(node_type="plan", title="Test Plan", parent_id=prd_id)
        self.assertIsNotNone(plan_id)

        # Verify hierarchy
        prd = self.graph.get_node(prd_id)
        self.assertEqual(prd.parent_id, project_id)

        plan = self.graph.get_node(plan_id)
        self.assertEqual(plan.parent_id, prd_id)

    def test_02_task_lifecycle(self):
        """Test complete task lifecycle."""
        # Create project and task
        project_id = self.graph.create_node(node_type="project", title="Lifecycle Test")

        task_id = self.graph.create_node(
            node_type="task",
            title="Test Task",
            parent_id=project_id,
            metadata={"estimated_hours": 2},
        )

        # Verify initial status
        task = self.graph.get_node(task_id)
        self.assertEqual(task.status, "pending")

        # Start task
        self.graph.update_status(task_id, "active")
        task = self.graph.get_node(task_id)
        self.assertEqual(task.status, "active")
        self.assertIsNotNone(task.started_at)

        # Complete task
        self.graph.update_status(task_id, "completed", duration_seconds=120)
        task = self.graph.get_node(task_id)
        self.assertEqual(task.status, "completed")
        self.assertIsNotNone(task.completed_at)

    def test_03_dependencies(self):
        """Test dependency creation and resolution."""
        project_id = self.graph.create_node(node_type="project", title="Dependency Test")

        task1_id = self.graph.create_node(node_type="task", title="Task 1", parent_id=project_id)

        task2_id = self.graph.create_node(node_type="task", title="Task 2", parent_id=project_id)

        # Add dependency: task2 blocks on task1
        dep_id = self.graph.add_dependency(
            source_node_id=task2_id,
            target_node_id=task1_id,
            dependency_type="blocks",
            reason="Task 2 needs output from Task 1",
        )
        self.assertIsNotNone(dep_id)

        # Verify dependency
        deps = self.graph.get_dependencies(task2_id)
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].target_node_id, task1_id)
        self.assertEqual(deps[0].dependency_type, "blocks")

    def test_04_output_storage(self):
        """Test output storage and retrieval."""
        project_id = self.graph.create_node(node_type="project", title="Output Test")

        task_id = self.graph.create_node(node_type="task", title="Test Task", parent_id=project_id)

        # Add output
        output_id = self.graph.add_output(
            node_id=task_id,
            output_type="code",
            output_summary="Created database migration",
            output_data={"migration_file": "migrations/001_create_users.py", "table": "users"},
            file_paths=["migrations/001_create_users.py"],
            tokens_produced=450,
        )
        self.assertIsNotNone(output_id)

        # Retrieve outputs
        outputs = self.graph.get_outputs(task_id)
        self.assertEqual(len(outputs), 1)
        self.assertEqual(outputs[0].output_type, "code")
        self.assertIn("migrations", outputs[0].file_paths[0])

    def test_05_context_compilation(self):
        """Test context compilation with dependencies."""
        # Create project hierarchy
        project_id = self.graph.create_node(
            node_type="project",
            title="Context Test Project",
            metadata={"tech_stack": ["Python", "FastAPI"]},
        )

        prd_id = self.graph.create_node(
            node_type="prd",
            title="Context Test PRD",
            parent_id=project_id,
            metadata={
                "requirements": ["Secure authentication", "JWT tokens"],
                "constraints": ["Use bcrypt", "Token expiry: 1 hour"],
            },
        )

        wave_id = self.graph.create_node(
            node_type="wave", title="Implementation Wave", parent_id=prd_id
        )

        # Create task 1 with output
        task1_id = self.graph.create_node(
            node_type="task",
            title="Create database schema",
            parent_id=wave_id,
            description="Design and implement user tables",
        )

        self.graph.update_status(task1_id, "completed", duration_seconds=300)
        self.graph.add_output(
            node_id=task1_id,
            output_type="code",
            output_summary="Created users and tokens tables",
            output_data={"tables": ["users", "tokens"]},
            file_paths=["migrations/001_users.py", "migrations/002_tokens.py"],
        )

        # Create task 2 that depends on task 1
        task2_id = self.graph.create_node(
            node_type="task",
            title="Implement authentication API",
            parent_id=wave_id,
            description="Create login and registration endpoints",
        )

        self.graph.add_dependency(
            source_node_id=task2_id,
            target_node_id=task1_id,
            dependency_type="blocks",
            reason="Needs database schema",
        )

        # Compile context for task 2
        compiled = self.compiler.compile_for_node(task2_id)

        # Verify compilation results
        self.assertIsNotNone(compiled)
        self.assertGreater(compiled.total_tokens, 0)
        self.assertLess(compiled.total_tokens, 7500)  # Should be much less than baseline
        self.assertGreater(compiled.savings_pct, 0)

        # Verify components
        self.assertIn("authentication API", compiled.goal)
        self.assertIsNotNone(compiled.parent_context)
        self.assertGreater(len(compiled.dependency_outputs), 0)
        self.assertIn(task1_id, compiled.dependency_outputs)

    def test_06_workflow_integration(self):
        """Test WorkflowGraphIntegration."""
        # Create project
        project_id = self.integration.create_project_node(
            project_title="Integration Test", metadata={"integration_test": True}
        )
        self.assertIsNotNone(project_id)

        # Create wave
        wave_id = self.integration.create_wave_node(
            wave_id="test_wave_001",
            wave_title="Test Wave",
            project_node_id=project_id,
            metadata={"wave_number": 1},
        )
        self.assertIsNotNone(wave_id)

        # Create tasks
        task1_id = self.integration.create_task_node(
            task_title="Task 1", wave_node_id=wave_id, metadata={"parallel_group": 1}
        )

        task2_id = self.integration.create_task_node(
            task_title="Task 2",
            wave_node_id=wave_id,
            dependencies=[task1_id],
            metadata={"parallel_group": 2},
        )

        # Execute lifecycle
        self.integration.start_node_execution(task1_id)
        self.integration.complete_node_execution(
            node_id=task1_id,
            duration_seconds=60,
            outputs=[
                {"type": "result", "summary": "Task 1 completed", "data": {"result": "success"}}
            ],
        )

        # Verify task 1 completed
        task1 = self.graph.get_node(task1_id)
        self.assertEqual(task1.status, "completed")

        # Verify task 2 has dependency on task 1
        deps = self.graph.get_dependencies(task2_id)
        self.assertEqual(len(deps), 1)
        self.assertEqual(deps[0].target_node_id, task1_id)

        # Get compiled context for task 2
        context = self.integration.get_compiled_context_for_task(task2_id)
        self.assertIsNotNone(context)
        self.assertIn("_metadata", context)
        self.assertIn("total_tokens", context["_metadata"])

    def test_07_token_savings_measurement(self):
        """Test token savings measurement."""
        # Create simple project structure
        project_id = self.graph.create_node(node_type="project", title="Token Test")

        task_id = self.graph.create_node(
            node_type="task",
            title="Simple Task",
            parent_id=project_id,
            description="A simple task for token measurement",
        )

        # Compile context
        compiled = self.compiler.compile_for_node(task_id)

        # Verify token metrics
        self.assertIsNotNone(compiled)
        self.assertGreater(compiled.total_tokens, 0)
        self.assertEqual(len(compiled.token_breakdown), 6)  # Should have 6 components

        # Verify savings calculation
        baseline = 7500
        savings = baseline - compiled.total_tokens
        expected_savings_pct = (savings / baseline) * 100
        self.assertAlmostEqual(compiled.savings_pct, expected_savings_pct, places=1)

    def test_08_execution_summary(self):
        """Test execution summary generation."""
        # Create project with multiple nodes
        project_id = self.graph.create_node(node_type="project", title="Summary Test")

        for i in range(3):
            task_id = self.graph.create_node(
                node_type="task", title=f"Task {i+1}", parent_id=project_id
            )

            if i == 0:
                self.graph.update_status(task_id, "completed", duration_seconds=30)
            elif i == 1:
                self.graph.update_status(task_id, "active")

        # Get summary
        summary = self.integration.get_execution_summary(project_id)

        # Verify summary structure
        self.assertIn("metrics", summary)
        self.assertIn("token_stats", summary)
        self.assertIn("task", summary["metrics"])

        # Verify counts
        task_metrics = summary["metrics"]["task"]
        self.assertEqual(task_metrics.get("completed", 0), 1)
        self.assertEqual(task_metrics.get("active", 0), 1)
        self.assertEqual(task_metrics.get("pending", 0), 1)


class TestContextCompilerPerformance(unittest.TestCase):
    """Test context compiler performance and accuracy."""

    def setUp(self):
        """Set up test fixtures."""
        _install_isolated_database(self)
        self.graph = ExecutionGraphManager()
        self.compiler = ContextCompiler()

    def tearDown(self):
        """Release the temp DB runtime before the next test."""
        _cleanup_isolated_database(self)

    def test_compilation_time(self):
        """Test that context compilation is fast."""
        import time

        # Create simple structure
        project_id = self.graph.create_node(node_type="project", title="Performance Test")

        task_id = self.graph.create_node(node_type="task", title="Test Task", parent_id=project_id)

        # Measure compilation time
        start = time.time()
        compiled = self.compiler.compile_for_node(task_id)
        duration = time.time() - start

        # Should compile in under 100ms
        self.assertLess(duration, 0.1)
        self.assertIsNotNone(compiled)

    def test_token_estimation_accuracy(self):
        """Test token estimation is reasonable."""
        project_id = self.graph.create_node(node_type="project", title="Estimation Test")

        task_id = self.graph.create_node(
            node_type="task",
            title="Test Task with a longer description that should consume more tokens",
            parent_id=project_id,
            description="This is a detailed description that adds more tokens to the context",
        )

        compiled = self.compiler.compile_for_node(task_id)

        # Token count should be proportional to text length
        # Goal has ~20 words = ~5 tokens (rough)
        self.assertGreater(compiled.token_breakdown["goal"], 0)

        # Total should be reasonable
        self.assertLess(compiled.total_tokens, 2000)  # Should be under 2K for simple case


def run_integration_tests():
    """Run all integration tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestExecutionGraphIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestContextCompilerPerformance))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(run_integration_tests())
