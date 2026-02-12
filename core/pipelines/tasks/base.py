"""Generic task-flow hub for pipeline subflow orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


TaskExecutor = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
TaskEnabledFn = Callable[[dict[str, Any]], bool]


@dataclass
class TaskFlowSpec:
    task_id: str
    pipeline: str
    system_name: str
    trigger_types: set[str] = field(default_factory=set)
    scheduler_type: str = "manual"
    dependencies: list[str] = field(default_factory=list)
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    handler_name: str = ""
    enabled_fn: TaskEnabledFn | None = None
    executor: TaskExecutor | None = None

    def is_trigger_compatible(self, trigger_type: str) -> bool:
        if not self.trigger_types:
            return True
        return trigger_type in self.trigger_types

    def is_enabled(self, flags: dict[str, bool]) -> bool:
        if self.enabled_fn is not None:
            return bool(self.enabled_fn(flags))
        return bool(flags.get(self.task_id, True))


class TaskFlowHub:
    """Resolve and execute registered task flows with dependency ordering."""

    def __init__(self, pipeline: str, system_name: str) -> None:
        self.pipeline = pipeline
        self.system_name = system_name
        self._flows: dict[str, TaskFlowSpec] = {}

    def register(self, spec: TaskFlowSpec) -> None:
        self._flows[spec.task_id] = spec

    def register_many(self, specs: list[TaskFlowSpec]) -> None:
        for spec in specs:
            self.register(spec)

    def list_flows(self, flags: dict[str, bool] | None = None) -> list[dict[str, Any]]:
        enabled_flags = flags or {}
        rows: list[dict[str, Any]] = []
        for spec in sorted(self._flows.values(), key=lambda item: item.task_id):
            rows.append(
                {
                    "task_id": spec.task_id,
                    "pipeline": spec.pipeline,
                    "system_name": spec.system_name,
                    "trigger_types": sorted(spec.trigger_types),
                    "scheduler_type": spec.scheduler_type,
                    "dependencies": list(spec.dependencies),
                    "description": spec.description,
                    "input_schema": spec.input_schema,
                    "output_schema": spec.output_schema,
                    "handler_name": spec.handler_name,
                    "enabled": spec.is_enabled(enabled_flags),
                }
            )
        return rows

    async def run(
        self,
        *,
        trigger_type: str,
        context: dict[str, Any],
        flags: dict[str, bool],
        selected_task_ids: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        ordered_ids = self._resolve_order(selected_task_ids)
        results: dict[str, dict[str, Any]] = {}

        for task_id in ordered_ids:
            spec = self._flows[task_id]
            if not spec.is_trigger_compatible(trigger_type):
                results[task_id] = {"status": "skipped", "reason": "trigger_mismatch", "task_id": task_id}
                continue
            if not spec.is_enabled(flags):
                results[task_id] = {"status": "skipped", "reason": "disabled", "task_id": task_id}
                continue
            if spec.executor is None:
                results[task_id] = {"status": "skipped", "reason": "no_executor", "task_id": task_id}
                continue

            dep_failed = False
            for dep in spec.dependencies:
                dep_result = results.get(dep, {})
                if dep_result.get("status") == "failed":
                    dep_failed = True
                    break
            if dep_failed:
                results[task_id] = {"status": "skipped", "reason": "dependency_failed", "task_id": task_id}
                continue

            try:
                results[task_id] = await spec.executor(context)
            except Exception as exc:
                results[task_id] = {"status": "failed", "task_id": task_id, "error": str(exc)}

        return results

    def _resolve_order(self, selected_task_ids: list[str] | None) -> list[str]:
        selected = set(selected_task_ids or self._flows.keys())
        resolved: list[str] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visited:
                return
            if task_id in visiting:
                return
            if task_id not in self._flows:
                return
            visiting.add(task_id)
            for dep in self._flows[task_id].dependencies:
                visit(dep)
            visiting.remove(task_id)
            visited.add(task_id)
            if task_id in selected:
                resolved.append(task_id)

        for task_id in sorted(selected):
            visit(task_id)
        return resolved
