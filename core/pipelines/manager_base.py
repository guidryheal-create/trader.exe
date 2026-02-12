"""Shared manager interface/mixin for pipeline managers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol

from core.pipelines.triggers import BaseTriggerFlow
from core.pipelines.tasks import BasePipelineTask, TaskFlowHub


class PipelineManager(Protocol):
    pipeline: str
    system_name: str

    def list_task_flows(self) -> list[dict[str, Any]]: ...

    def update_task_flows(self, flags: dict[str, bool]) -> list[dict[str, Any]]: ...

    def list_trigger_flows(self) -> list[dict[str, Any]]: ...


class TaskFlowManagerMixin:
    """Common task-flow registration and controls for manager classes."""

    pipeline: str
    system_name: str

    def _init_task_flow_registry(self, pipeline_tasks: list[BasePipelineTask]) -> None:
        self._pipeline_tasks = list(pipeline_tasks)
        self._task_flow_hub = TaskFlowHub(pipeline=self.pipeline, system_name=self.system_name)
        self._task_flow_hub.register_many([task.to_spec() for task in self._pipeline_tasks])
        self._task_flow_flags = {
            row["task_id"]: bool(row.get("enabled", True))
            for row in self._task_flow_hub.list_flows(flags={})
        }

    def list_task_flows(self) -> list[dict[str, Any]]:
        return self._task_flow_hub.list_flows(flags=self._task_flow_flags)

    def update_task_flows(self, flags: dict[str, bool]) -> list[dict[str, Any]]:
        for task_id, value in flags.items():
            self._task_flow_flags[str(task_id)] = bool(value)
        return self.list_task_flows()

    def _init_trigger_flow_registry(self, trigger_flows: list[BaseTriggerFlow]) -> None:
        self._trigger_flows = {flow.trigger_id: flow for flow in trigger_flows}
        self._trigger_history: list[dict[str, Any]] = []

    def list_trigger_flows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for trigger_id in sorted(self._trigger_flows.keys()):
            rows.append(self._trigger_flows[trigger_id].to_metadata())
        return rows

    async def run_trigger_flow(self, trigger_id: str, **kwargs: Any) -> dict[str, Any]:
        flow = self._trigger_flows.get(trigger_id)
        if flow is None:
            payload = {
                "status": "failed",
                "trigger_id": trigger_id,
                "error": "unknown_trigger_flow",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._append_trigger_history(payload)
            return payload

        started_at = datetime.now(timezone.utc)
        try:
            result = await flow.resolve(**kwargs)
            if isinstance(result, dict):
                payload = dict(result)
            else:
                payload = {"result": result}
            payload.setdefault("status", "completed")
            payload["trigger_id"] = trigger_id
            payload["started_at"] = started_at.isoformat()
            payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            self._append_trigger_history(payload)
            return payload
        except Exception as exc:
            payload = {
                "status": "failed",
                "trigger_id": trigger_id,
                "error": str(exc),
                "started_at": started_at.isoformat(),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            self._append_trigger_history(payload)
            return payload

    def _append_trigger_history(self, payload: dict[str, Any]) -> None:
        self._trigger_history.append(payload)
        self._trigger_history = self._trigger_history[-500:]

    def list_trigger_history(self, limit: int = 50) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        return list(self._trigger_history[-limit:])
