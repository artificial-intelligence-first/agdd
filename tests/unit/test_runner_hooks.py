import pytest

from agdd.core.permissions import ToolPermission
from agdd.runners.hooks import RunnerHooks


class DummyApprovalGate:
    def __init__(self, permission: ToolPermission = ToolPermission.ALWAYS):
        self.permission = permission

    def evaluate(self, tool_name, context):
        return self.permission


class RecordingStorage:
    def __init__(self):
        self.events = []

    async def append_event(
        self,
        *,
        run_id,
        agent_slug,
        event_type,
        timestamp,
        level=None,
        message=None,
        payload=None,
        span_id=None,
        parent_span_id=None,
        contract_id=None,
        contract_version=None,
    ):
        self.events.append(
            {
                "run_id": run_id,
                "agent_slug": agent_slug,
                "event_type": event_type,
                "level": level,
                "message": message,
                "payload": payload or {},
            }
        )


@pytest.mark.asyncio
async def test_runner_hooks_persists_success_events(monkeypatch):
    storage = RecordingStorage()

    async def fake_get_storage_backend():
        return storage

    monkeypatch.setattr("agdd.runners.hooks.get_storage_backend", fake_get_storage_backend)

    hooks = RunnerHooks(approval_gate=DummyApprovalGate(), enable_approvals=True)
    context = {"agent_slug": "mag.test", "run_id": "run-123"}
    tool_args = {"arg": "value"}
    result = {"status": "ok"}

    await hooks.pre_tool_execution("test_tool", tool_args, context)
    await hooks.post_tool_execution("test_tool", tool_args, result, context)

    assert [event["event_type"] for event in storage.events] == [
        "tool.permission.checked",
        "tool.executed",
    ]
    assert storage.events[0]["payload"]["tool"] == "test_tool"
    assert storage.events[1]["payload"]["tool"] == "test_tool"
    assert storage.events[1]["payload"]["result"]["status"] == "ok"


@pytest.mark.asyncio
async def test_runner_hooks_persists_error_events(monkeypatch):
    storage = RecordingStorage()

    async def fake_get_storage_backend():
        return storage

    monkeypatch.setattr("agdd.runners.hooks.get_storage_backend", fake_get_storage_backend)

    hooks = RunnerHooks(approval_gate=DummyApprovalGate(), enable_approvals=True)
    context = {"agent_slug": "mag.test", "run_id": "run-456"}
    tool_args = {"arg": "value"}

    error = RuntimeError("failure")
    await hooks.on_tool_error("test_tool", tool_args, error, context)

    assert len(storage.events) == 1
    event = storage.events[0]
    assert event["event_type"] == "tool.error"
    assert event["payload"]["tool"] == "test_tool"
    assert event["payload"]["error_type"] == "RuntimeError"
    assert event["payload"]["error_message"] == "failure"
