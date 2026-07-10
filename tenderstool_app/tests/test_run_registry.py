from pathlib import Path

from app.services import run_registry
from app.services.tenderstool_client import ExtractionResult


def _fake_result() -> ExtractionResult:
    return ExtractionResult(
        search_type="licitaciones",
        favorite_name="SAP > 1M",
        max_results=None,
        processed_count=5,
        partial_error_count=0,
        duration_seconds=12.3,
        excel_path=Path("fake.xlsx"),
        run_id="abc123",
    )


def test_create_and_get_returns_empty_state():
    run_registry.create("run-1")
    state = run_registry.get("run-1")
    assert state is not None
    assert state.steps == []
    assert state.done is False


def test_get_unknown_run_id_returns_none():
    assert run_registry.get("no-existe") is None


def test_append_step_accumulates_in_order():
    run_registry.create("run-2")
    run_registry.append_step("run-2", "paso 1")
    run_registry.append_step("run-2", "paso 2")
    assert run_registry.get("run-2").steps == ["paso 1", "paso 2"]


def test_append_step_on_unknown_run_id_does_not_raise():
    run_registry.append_step("no-existe", "paso")  # no debe lanzar


def test_finish_success_marks_done_with_result():
    run_registry.create("run-3")
    result = _fake_result()
    run_registry.finish_success("run-3", result)
    state = run_registry.get("run-3")
    assert state.done is True
    assert state.result is result
    assert state.error is None


def test_finish_error_marks_done_with_message_and_status():
    run_registry.create("run-4")
    run_registry.finish_error("run-4", "usr/pwd incorrectos", 401)
    state = run_registry.get("run-4")
    assert state.done is True
    assert state.error == "usr/pwd incorrectos"
    assert state.error_status == 401
    assert state.result is None


async def test_try_acquire_succeeds_when_free():
    acquired = await run_registry.try_acquire()
    assert acquired is True
    run_registry.release()


async def test_try_acquire_rejects_when_already_held():
    assert await run_registry.try_acquire() is True
    assert await run_registry.try_acquire() is False
    run_registry.release()


def test_release_when_not_locked_does_not_raise():
    run_registry.release()  # no debe lanzar aunque no haya nada que liberar
