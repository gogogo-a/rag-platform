"""Expert task queue helpers."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


DEFAULT_EXPERT_TOPICS = {
    "tasks": "expert_tasks",
    "results": "expert_results",
    "dead_letters": "expert_dead_letters",
}


class ExpertTaskQueue:
    def __init__(
        self,
        client: Any = None,
        topics: Optional[Dict[str, str]] = None,
        max_retries: int = 5,
    ):
        self.client = client
        self.topics = {**DEFAULT_EXPERT_TOPICS, **(topics or {})}
        self.max_retries = max_retries

    def build_task(
        self,
        question_id: str,
        expert_key: str,
        task: str,
        context: str,
        retry_count: int = 0,
        feedback: str = "",
    ) -> Dict[str, Any]:
        task_id = f"{question_id}-{expert_key}-{uuid.uuid4().hex[:8]}"
        return {
            "question_id": question_id,
            "task_id": task_id,
            "expert_key": expert_key,
            "task": task,
            "context": context,
            "feedback": feedback,
            "retry_count": retry_count,
            "created_at": datetime.now().isoformat(),
        }

    def send_task(self, task: Dict[str, Any]) -> bool:
        if not self.client:
            return True
        return bool(self.client.send_message(
            topic=self.topics["tasks"],
            message=task,
            key=task.get("question_id"),
        ))

    def send_result(self, result: Dict[str, Any]) -> bool:
        if not self.client:
            return True
        return bool(self.client.send_message(
            topic=self.topics["results"],
            message=result,
            key=result.get("question_id"),
        ))

    def route_failure(
        self,
        task: Dict[str, Any],
        error: str,
        raw_process: Optional[List[Any]] = None,
    ) -> str:
        retry_count = int(task.get("retry_count") or 0)
        failure = {
            **task,
            "success": False,
            "error": error,
            "raw_process": raw_process or [],
            "failed_at": datetime.now().isoformat(),
        }
        if retry_count + 1 >= self.max_retries:
            if self.client:
                self.client.send_message(
                    topic=self.topics["dead_letters"],
                    message=failure,
                    key=task.get("question_id"),
                )
            return "dead_letter"

        task["retry_count"] = retry_count + 1
        task["feedback"] = self.build_retry_feedback(error, raw_process or [])
        self.send_task(task)
        return "retry"

    @staticmethod
    def build_retry_feedback(error: str, raw_process: List[Any]) -> str:
        process_text = "；".join(str(item).strip() for item in raw_process if str(item).strip())
        if process_text:
            return f"上次结果不可用，原因：{error}。请补充修正：{process_text[:300]}"
        return f"上次结果不可用，原因：{error}。请重新处理。"


class ExpertResultStore:
    def __init__(self):
        self._results: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._dead_letters: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._condition = threading.Condition()

    def add_result(self, result: Dict[str, Any]) -> None:
        question_id = str(result.get("question_id") or "").strip()
        if not question_id:
            return
        with self._condition:
            task_id = str(result.get("task_id") or "")
            retry_count = int(result.get("retry_count") or 0)
            self._results[question_id] = [
                item
                for item in self._results.get(question_id, [])
                if not (
                    str(item.get("task_id") or "") == task_id
                    and int(item.get("retry_count") or 0) == retry_count
                )
            ]
            self._results[question_id].append(result)
            self._condition.notify_all()

    def get_results(self, question_id: str) -> List[Dict[str, Any]]:
        with self._condition:
            return list(self._results.get(question_id, []))

    def add_dead_letter(self, task: Dict[str, Any]) -> None:
        question_id = str(task.get("question_id") or "").strip()
        if not question_id:
            return
        with self._condition:
            self._dead_letters[question_id].append(task)
            self._condition.notify_all()

    def get_dead_letters(self, question_id: str) -> List[Dict[str, Any]]:
        with self._condition:
            return list(self._dead_letters.get(question_id, []))

    def wait_for_update(self, question_id: str, known_count: int, timeout: float = 0.2) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            while time.monotonic() < deadline:
                current_count = len(self._results.get(question_id, [])) + len(self._dead_letters.get(question_id, []))
                if current_count > known_count:
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
        return False


expert_result_store = ExpertResultStore()
