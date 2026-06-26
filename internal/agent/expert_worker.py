"""Kafka-backed expert task worker."""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Callable, Dict, List, Optional

from internal.agent.expert_agent_registry import ExpertAgentRegistry
from internal.agent.expert_context_builder import ExpertContextBuilder
from internal.agent.expert_task_queue import ExpertTaskQueue
from internal.agent.prompted_react_agent import PromptedReActAgent
from pkg.constants.constants import AGENT_MAX_ITERATIONS, EXPERT_TASK_MAX_RETRIES


class ExpertTaskWorker:
    def __init__(
        self,
        llm_service,
        tool_map: Dict[str, Any],
        client: Any = None,
        topics: Optional[Dict[str, str]] = None,
    ):
        self.llm_service = llm_service
        self.registry = ExpertAgentRegistry(tool_map)
        self.context_builder = ExpertContextBuilder()
        self.queue = ExpertTaskQueue(
            client=client,
            topics=topics,
            max_retries=EXPERT_TASK_MAX_RETRIES,
        )

    async def handle_task(self, task: Dict[str, Any]) -> None:
        try:
            payload = json.loads(await self._ask_expert(task))
            answer_text = str(payload.get("answer") or "").strip()
            success = self._is_useful_answer(answer_text)
            result = {
                "question_id": task.get("question_id"),
                "task_id": task.get("task_id"),
                "expert_key": task.get("expert_key"),
                "answer": answer_text,
                "process_summary": payload.get("process_summary", ""),
                "raw_process": self._merge_processes(payload.get("raw_process", [])),
                "documents": payload.get("documents", []),
                "rag_results": payload.get("rag_results", []),
                "success": success,
                "error": "" if success else "结果不可用",
                "retry_count": task.get("retry_count", 0),
            }
        except Exception as exc:
            result = {
                "question_id": task.get("question_id"),
                "task_id": task.get("task_id"),
                "expert_key": task.get("expert_key"),
                "answer": "",
                "process_summary": "",
                "raw_process": [],
                "documents": [],
                "rag_results": [],
                "success": False,
                "error": str(exc),
                "retry_count": task.get("retry_count", 0),
            }

        self.queue.send_result(result)

    def handle_task_sync(self, task: Dict[str, Any]) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.handle_task(task))
            return
        asyncio.run_coroutine_threadsafe(self.handle_task(task), loop)

    async def _ask_expert(self, task: Dict[str, Any]) -> str:
        expert_name = str(task.get("expert_key") or "")
        expert_tools = self.registry.get_tools_for_expert(expert_name)
        if not expert_tools:
            return json.dumps(
                {
                    "answer": "当前专家没有可用工具。",
                    "used_tools": [],
                    "documents": [],
                    "rag_results": [],
                    "process_summary": "",
                    "raw_process": [],
                    "confidence": 0,
                },
                ensure_ascii=False,
            )

        documents: List[Dict[str, Any]] = []
        rag_results: List[Dict[str, Any]] = []
        raw_process: List[Dict[str, Any]] = []
        expert_input = self._build_expert_input(task)
        expert_prompt = await self.registry.get_prompt_for_expert(expert_name)
        expert = PromptedReActAgent(
            llm_service=self.llm_service,
            tools=expert_tools,
            prompt_template=expert_prompt,
            max_iterations=AGENT_MAX_ITERATIONS,
            verbose=False,
            callback=self._build_expert_callback(documents, rag_results, raw_process),
        )
        answer = await expert.run_stream(expert_input)
        return json.dumps(
            {
                "answer": answer,
                "used_tools": list(expert_tools.keys()),
                "documents": documents,
                "rag_results": rag_results,
                "process_summary": self._summarize_process(raw_process),
                "raw_process": self._merge_processes(raw_process),
                "confidence": 1,
            },
            ensure_ascii=False,
        )

    def _build_expert_input(self, task: Dict[str, Any]) -> str:
        parts = [
            f"问题编号：{task.get('question_id', '')}",
            str(task.get("context") or "").strip(),
        ]
        feedback = str(task.get("feedback") or "").strip()
        if feedback:
            parts.append(f"主助手反馈：{feedback}")
        return "\n\n".join(part for part in parts if part)

    @staticmethod
    def _build_expert_callback(
        documents: List[Dict[str, Any]],
        rag_results: List[Dict[str, Any]],
        raw_process: List[Dict[str, Any]],
    ) -> Callable:
        step_index = 0

        def expert_callback(event_type: str, content: Any) -> None:
            nonlocal step_index
            if event_type == "tool_result" and isinstance(content, dict):
                documents.extend(content.get("documents", []))
                rag_results.extend(content.get("results", []))
                return
            if event_type in {"llm_chunk", "action", "observation", "final_answer"}:
                phase = "thought" if event_type == "llm_chunk" else event_type
                text = str(content or "").strip()
                if text:
                    step_index += 1
                    raw_process.append({
                        "phase": phase,
                        "content": text,
                        "step_index": step_index,
                    })

        return expert_callback

    @classmethod
    def _merge_processes(cls, raw_process: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for item in raw_process:
            phase = str(item.get("phase") or "").strip()
            content = str(item.get("content") or "").strip()
            if not phase or not content or cls._is_process_marker_only(content):
                continue
            if phase == "thought" and merged and merged[-1].get("phase") == phase:
                merged[-1]["content"] = cls._join_process_text(str(merged[-1].get("content", "")), content)
                continue
            merged.append({**item, "phase": phase, "content": content})
        return merged

    @staticmethod
    def _is_process_marker_only(text: str) -> bool:
        return re.match(r"^\s*(thought|action|action input|observation|final answer|finalanswer|思考|操作|观测|输出|:|：)\s*$", str(text or ""), re.I) is not None

    @staticmethod
    def _join_process_text(left: str, right: str) -> str:
        first = str(left or "").strip()
        second = str(right or "").strip()
        if not first:
            return second
        if not second:
            return first
        if re.match(r"^[，。！？、；：,.!?;:]", second):
            return f"{first}{second}"
        if re.search(r"[（(\[{《“‘]$", first):
            return f"{first}{second}"
        return re.sub(r"\s+", " ", f"{first} {second}").strip()

    @staticmethod
    def _summarize_process(raw_process: List[Dict[str, Any]]) -> str:
        summary = []
        for item in raw_process:
            phase = item.get("phase")
            content = str(item.get("content") or "").strip()
            if phase in {"action", "observation"} and content:
                summary.append(content)
            if len(summary) >= 3:
                break
        return "；".join(summary)

    @staticmethod
    def _is_useful_answer(answer: str) -> bool:
        if not answer:
            return False
        unavailable_markers = [
            "抱歉，我无法回答",
            "无法回答这个问题",
            "暂时没有返回可用结果",
            "处理过程中出现错误",
            "Agent stopped due to iteration limit or time limit",
            "iteration limit",
            "time limit",
        ]
        return not any(marker in answer for marker in unavailable_markers)
