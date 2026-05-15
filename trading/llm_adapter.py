"""Optional adapter for running the real GoldBot backend workflow."""

from __future__ import annotations

import os
import tempfile
import time
from contextlib import suppress

import requests

GOLDBOT_API = os.getenv("GOLDBOT_API", "http://127.0.0.1:5001").rstrip("/")
GOLDBOT_TIMEOUT_SECONDS = int(os.getenv("GOLDBOT_TIMEOUT_SECONDS", "1800"))
GOLDBOT_POLL_SECONDS = int(os.getenv("GOLDBOT_POLL_SECONDS", "5"))
GOLDBOT_MAX_ROUNDS = int(os.getenv("GOLDBOT_MAX_ROUNDS", "6"))
GOLDBOT_PLATFORM = os.getenv("GOLDBOT_PLATFORM", "parallel")
GOLDBOT_USE_LLM_FOR_PROFILES = os.getenv("GOLDBOT_USE_LLM_FOR_PROFILES", "true").lower() == "true"
GOLDBOT_PARALLEL_PROFILE_COUNT = int(os.getenv("GOLDBOT_PARALLEL_PROFILE_COUNT", "4"))
GOLDBOT_KEEP_PROJECTS = os.getenv("GOLDBOT_KEEP_PROJECTS", "false").lower() == "true"


def _deadline() -> float:
    return time.time() + GOLDBOT_TIMEOUT_SECONDS


def _sleep() -> None:
    time.sleep(max(1, GOLDBOT_POLL_SECONDS))


def _extract(data: dict, *keys, default=None):
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default if current is None else current


def _wait_for_graph_build(session: requests.Session, task_id: str, deadline: float) -> dict:
    while time.time() < deadline:
        response = session.get(f"{GOLDBOT_API}/api/graph/task/{task_id}", timeout=30)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") or {}
        status = str(data.get("status", "")).lower()
        if status == "completed":
            return data
        if status == "failed":
            raise RuntimeError(f"GoldBot graph build failed: {data.get('error') or data.get('message')}")
        _sleep()
    raise TimeoutError("GoldBot graph build timed out")


def _wait_for_prepare(session: requests.Session, simulation_id: str, task_id: str | None, deadline: float) -> None:
    while time.time() < deadline:
        payload = {"simulation_id": simulation_id}
        if task_id:
            payload["task_id"] = task_id
        response = session.post(f"{GOLDBOT_API}/api/simulation/prepare/status", json=payload, timeout=30)
        response.raise_for_status()
        data = (response.json() or {}).get("data") or {}
        status = str(data.get("status", "")).lower()
        if status in {"ready", "completed"} or data.get("already_prepared"):
            return
        if status == "failed":
            raise RuntimeError(f"GoldBot prepare failed: {data.get('error') or data.get('message')}")
        _sleep()
    raise TimeoutError("GoldBot prepare timed out")


def _wait_for_run(session: requests.Session, simulation_id: str, deadline: float) -> None:
    while time.time() < deadline:
        response = session.get(f"{GOLDBOT_API}/api/simulation/{simulation_id}/run-status", timeout=30)
        response.raise_for_status()
        data = (response.json() or {}).get("data") or {}
        runner_status = str(data.get("runner_status", "")).lower()
        if runner_status in {"completed", "stopped"}:
            return
        if runner_status == "failed":
            raise RuntimeError(f"GoldBot run failed: {data.get('error') or 'runner failed'}")
        _sleep()
    raise TimeoutError("GoldBot simulation run timed out")


def _wait_for_report(session: requests.Session, simulation_id: str, task_id: str | None, deadline: float) -> None:
    while time.time() < deadline:
        payload = {"simulation_id": simulation_id}
        if task_id:
            payload["task_id"] = task_id
        response = session.post(f"{GOLDBOT_API}/api/report/generate/status", json=payload, timeout=30)
        response.raise_for_status()
        data = (response.json() or {}).get("data") or {}
        status = str(data.get("status", "")).lower()
        if status == "completed":
            return
        if status == "failed":
            raise RuntimeError(f"GoldBot report failed: {data.get('error') or data.get('message')}")
        _sleep()
    raise TimeoutError("GoldBot report generation timed out")


def run_real_goldbot_report(seed_text: str, simulation_requirement: str, project_name: str = "XAUUSD Trading Seed") -> str:
    """Run the real GoldBot backend workflow and return the generated report text."""
    deadline = _deadline()
    session = requests.Session()
    temp_path = ""
    project_id = ""

    try:
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as handle:
            handle.write(seed_text)
            temp_path = handle.name

        with open(temp_path, "rb") as upload_handle:
            upload_response = session.post(
                f"{GOLDBOT_API}/api/graph/ontology/generate",
                data={
                    "simulation_requirement": simulation_requirement,
                    "project_name": project_name,
                    "additional_context": "Trading analysis for XAUUSD. Return actionable directional reasoning.",
                },
                files={"files": (os.path.basename(temp_path), upload_handle, "text/markdown")},
                timeout=120,
            )
        upload_response.raise_for_status()
        upload_payload = upload_response.json()
        project_id = _extract(upload_payload, "data", "project_id")
        if not project_id:
            raise RuntimeError("GoldBot ontology generation did not return project_id")

        build_response = session.post(
            f"{GOLDBOT_API}/api/graph/build",
            json={"project_id": project_id, "graph_name": f"{project_name} Graph"},
            timeout=60,
        )
        build_response.raise_for_status()
        build_task_id = _extract(build_response.json(), "data", "task_id")
        if not build_task_id:
            raise RuntimeError("GoldBot graph build did not return task_id")
        _wait_for_graph_build(session, build_task_id, deadline)

        project_response = session.get(f"{GOLDBOT_API}/api/graph/project/{project_id}", timeout=30)
        project_response.raise_for_status()
        graph_id = _extract(project_response.json(), "data", "graph_id")
        if not graph_id:
            raise RuntimeError("GoldBot project did not expose graph_id after build")

        create_response = session.post(
            f"{GOLDBOT_API}/api/simulation/create",
            json={"project_id": project_id, "graph_id": graph_id, "enable_twitter": True, "enable_reddit": True},
            timeout=30,
        )
        create_response.raise_for_status()
        simulation_id = _extract(create_response.json(), "data", "simulation_id")
        if not simulation_id:
            raise RuntimeError("GoldBot simulation creation did not return simulation_id")

        prepare_response = session.post(
            f"{GOLDBOT_API}/api/simulation/prepare",
            json={
                "simulation_id": simulation_id,
                "use_llm_for_profiles": GOLDBOT_USE_LLM_FOR_PROFILES,
                "parallel_profile_count": GOLDBOT_PARALLEL_PROFILE_COUNT,
            },
            timeout=60,
        )
        prepare_response.raise_for_status()
        prepare_data = (prepare_response.json() or {}).get("data") or {}
        if not prepare_data.get("already_prepared"):
            _wait_for_prepare(session, simulation_id, prepare_data.get("task_id"), deadline)

        start_response = session.post(
            f"{GOLDBOT_API}/api/simulation/start",
            json={
                "simulation_id": simulation_id,
                "platform": GOLDBOT_PLATFORM,
                "max_rounds": GOLDBOT_MAX_ROUNDS,
                "enable_graph_memory_update": False,
                "force": False,
            },
            timeout=60,
        )
        start_response.raise_for_status()
        _wait_for_run(session, simulation_id, deadline)

        report_response = session.post(
            f"{GOLDBOT_API}/api/report/generate",
            json={"simulation_id": simulation_id, "force_regenerate": False},
            timeout=60,
        )
        report_response.raise_for_status()
        report_data = (report_response.json() or {}).get("data") or {}
        if str(report_data.get("status", "")).lower() != "completed" and not report_data.get("already_generated"):
            _wait_for_report(session, simulation_id, report_data.get("task_id"), deadline)

        final_report_response = session.get(f"{GOLDBOT_API}/api/report/by-simulation/{simulation_id}", timeout=30)
        final_report_response.raise_for_status()
        final_data = (final_report_response.json() or {}).get("data") or {}
        return (
            str(final_data.get("markdown_content") or "")
            or str(final_data.get("content") or "")
            or str(final_data.get("outline") or "")
        ).strip()
    finally:
        if project_id and not GOLDBOT_KEEP_PROJECTS:
            with suppress(Exception):
                session.delete(f"{GOLDBOT_API}/api/graph/project/{project_id}", timeout=20)
        session.close()
        if temp_path:
            with suppress(OSError):
                os.unlink(temp_path)
