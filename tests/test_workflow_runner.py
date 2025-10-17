import asyncio
from dataclasses import dataclass
from typing import Any, Dict

import pytest

from action_executor.templating import TemplateEngine
from action_executor.utils import topological_sort_nodes
from action_executor.workflow import WorkflowRunner


@dataclass
class SimpleEdge:
    source_node: str
    target_node: str


class StubLogger:
    def __init__(self) -> None:
        self.warnings = []
        self.errors = []

    def info(self, *args, **kwargs) -> None:  # pragma: no cover - not needed in tests
        pass

    def warning(self, message: str, *args, **kwargs) -> None:
        self.warnings.append((message, args))

    def error(self, message: str, *args, **kwargs) -> None:
        self.errors.append((message, args))


class StubModularRegistry:
    def get(self, action_id: str):  # pragma: no cover - not used in tests
        return None


class StubExecutor:
    async def execute(self, *args, **kwargs):  # pragma: no cover - not used in tests
        raise RuntimeError("executor should not be invoked in these tests")


@pytest.fixture
def workflow_runner() -> WorkflowRunner:
    logger = StubLogger()
    template_engine = TemplateEngine(logger=logger)
    return WorkflowRunner(
        logger=logger,
        modular_registry=StubModularRegistry(),
        template_engine=template_engine,
        http_executor=StubExecutor(),
        local_executor=StubExecutor(),
        modular_executor=StubExecutor(),
    )


def test_topological_sort_detects_cycle() -> None:
    nodes = {"A": object(), "B": object()}
    edges = [SimpleEdge("A", "B"), SimpleEdge("B", "A")]

    order, error = topological_sort_nodes(nodes, edges)

    assert order == []
    assert error is not None
    assert "循环依赖" in error


def test_topological_sort_returns_valid_order() -> None:
    nodes = {"A": object(), "B": object(), "C": object()}
    edges = [SimpleEdge("A", "B"), SimpleEdge("B", "C")]

    order, error = topological_sort_nodes(nodes, edges)

    assert error is None
    assert order == ["A", "B", "C"]


def test_evaluate_node_condition_expression(workflow_runner: WorkflowRunner) -> None:
    condition = {"mode": "expression", "expression": "{{ inputs.flag }}"}
    context = {"inputs": {"flag": "yes"}}

    result, error = asyncio.run(
        workflow_runner._evaluate_node_condition(  # pylint: disable=protected-access
            condition,
            node_id="node-1",
            condition_context=context,
        )
    )

    assert error is None
    assert result is True


def test_evaluate_node_condition_handles_error(workflow_runner: WorkflowRunner) -> None:
    condition = {"mode": "expression", "expression": "{{ 1 / 0 }}"}
    context: Dict[str, Any] = {"inputs": {}}

    result, error = asyncio.run(
        workflow_runner._evaluate_node_condition(  # pylint: disable=protected-access
            condition,
            node_id="node-2",
            condition_context=context,
        )
    )

    assert result is False
    assert error is not None
    assert "节点 ‘node-2’ 的条件计算失败" in error


def test_linked_condition_reads_inputs(workflow_runner: WorkflowRunner) -> None:
    condition = {"mode": "linked", "link": {"target_input": "flag"}}
    context = {"inputs": {"flag": "1"}}

    result, error = asyncio.run(
        workflow_runner._evaluate_node_condition(  # pylint: disable=protected-access
            condition,
            node_id="node-3",
            condition_context=context,
        )
    )

    assert error is None
    assert result is True
