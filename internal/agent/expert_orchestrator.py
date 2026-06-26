"""Supervisor-driven expert mode orchestration."""

import json
import asyncio
import uuid
import re
from typing import Any, Callable, Dict, List, Optional

from internal.agent.expert_agent_registry import ExpertAgentRegistry
from internal.agent.expert_context_builder import ExpertContextBuilder
from internal.agent.prompted_react_agent import PromptedReActAgent
from internal.agent.expert_task_queue import expert_result_store, ExpertResultStore, ExpertTaskQueue
from pkg.constants.constants import AGENT_MAX_ITERATIONS, EXPERT_MAX_STEPS, EXPERT_TASK_MAX_RETRIES


EXPERT_RESULT_WAIT_TIMEOUT_SECONDS = 1.0


class ExpertOrchestrator:
    def __init__(
        self,
        llm_service,
        tool_map: Dict[str, Any],
        history: Optional[List[Dict[str, Any]]] = None,
        callback: Optional[Callable] = None,
        max_steps: int = EXPERT_MAX_STEPS,
    ):
        self.llm_service = llm_service
        self.registry = ExpertAgentRegistry(tool_map)
        self.context_builder = ExpertContextBuilder()
        self.history = history or []
        self.callback = callback
        self.max_steps = max_steps
        self.original_question = ""
        self.question_id = ""
        self._step_index = 0
        self.task_queue = ExpertTaskQueue(
            client=None,
            topics=self._resolve_queue_topics(),
            max_retries=min(EXPERT_TASK_MAX_RETRIES, 2),
        )
        self.result_store = expert_result_store
        self.dead_letter_tasks: List[Dict[str, Any]] = []
        self._emitted_expert_process_keys = set()
        self.agent_context_usage = {
            "primary_agent_usage": None,
            "child_agent_usages": [],
        }

    def _emit(self, event_type: str, content: Any) -> None:
        if self.callback:
            self.callback(event_type, content)

    def _next_step(self) -> int:
        self._step_index += 1
        return self._step_index

    def _emit_agent_process(
        self,
        scope: str,
        agent_key: str,
        agent_name: str,
        phase: str,
        content: Any,
        step_index: int,
    ) -> None:
        if content is None:
            return
        text = str(content).strip()
        if not text:
            return
        self._emit(
            "agent_process",
            {
                "scope": scope,
                "agent_key": agent_key,
                "agent_name": agent_name,
                "phase": phase,
                "content": self._clean_process_display_text(phase, text) if scope == "expert" else self._clean_display_text(text),
                "step_index": step_index,
            },
        )

    def _build_expert_callback(
        self,
        expert_name: str,
        expert_display_name: str,
        documents: List[Dict[str, Any]],
        rag_results: List[Dict[str, Any]],
        raw_process: Optional[List[Dict[str, Any]]] = None,
    ) -> Callable:
        step_index = 0
        raw_process = raw_process if raw_process is not None else []

        def expert_callback(event_type: str, content: Any) -> None:
            nonlocal step_index
            if event_type == "tool_result" and isinstance(content, dict):
                documents.extend(content.get("documents", []))
                rag_results.extend(content.get("results", []))
                self._emit(event_type, content)
                return

            if event_type in {"llm_chunk", "action", "observation", "final_answer"}:
                phase = "thought" if event_type == "llm_chunk" else event_type
                text = str(content or "").strip()
                if not text:
                    return
                step_index += 1
                raw_process.append({
                    "phase": phase,
                    "content": text,
                    "step_index": step_index,
                })
                definition = self.registry.get_definition(expert_name)
                self._emit_expert_process_once(definition, phase, text)

        return expert_callback

    async def run_stream(self, user_message: str) -> str:
        self.original_question = user_message
        self.question_id = str(uuid.uuid4())
        await self.registry.load()
        self._capture_primary_context_usage(user_message)
        if self.task_queue.client is None:
            self.task_queue.client = self._resolve_queue_client()
        self._emit("expert_manifest", {"experts": await self.registry.get_manifest()})
        self._emit("expert_question", {"question_id": self.question_id})

        tasks = await self._plan_tasks(user_message)
        if not tasks:
            return "抱歉，当前没有可用专家处理这个问题。"

        selected_names = [
            self.registry.get_definition(task["expert_key"]).display_name
            for task in tasks[: self.max_steps]
        ]
        self._emit_agent_process(
            "supervisor",
            "supervisor",
            "主助手",
            "thought",
            f"识别到需要调用：{'、'.join(selected_names)}",
            self._next_step(),
        )

        running_tasks = [
            asyncio.create_task(self._dispatch_and_run_task(task))
            for task in tasks[: self.max_steps]
        ]
        if running_tasks:
            await asyncio.gather(*running_tasks)

        results = self.result_store.get_results(self.question_id)
        self.dead_letter_tasks = self.result_store.get_dead_letters(self.question_id)
        answer = self._compose_answer(results)
        await self._save_experience(answer, results)
        self._emit("agent_context_usage", self.agent_context_usage)
        return answer

    def _capture_primary_context_usage(self, user_message: str) -> None:
        try:
            from internal.service.message.context_usage_service import context_usage_service

            supervisor_input = self.context_builder.build_supervisor_input(user_message, self.history)
            self.agent_context_usage["primary_agent_usage"] = context_usage_service.build_text_section_usage(
                agent_key="supervisor",
                agent_name="主助手",
                title="当前上下文",
                content=supervisor_input,
                section_type="current_context",
            )
        except Exception:
            self.agent_context_usage["primary_agent_usage"] = None

    def _capture_child_context_usage(self, task: Dict[str, Any], definition) -> None:
        try:
            from internal.service.message.context_usage_service import context_usage_service

            expert_input = self.context_builder.build_expert_input(
                expert_name=task.get("expert_key", ""),
                task=task.get("task", ""),
                original_question=self.original_question,
                history=self.history,
            )
            usage = context_usage_service.build_text_section_usage(
                agent_key=definition.name,
                agent_name=definition.display_name,
                title="当前任务",
                content=expert_input,
                section_type="current_task",
            )
            existing_keys = {
                item.get("agent_key")
                for item in self.agent_context_usage["child_agent_usages"]
            }
            if definition.name not in existing_keys:
                self.agent_context_usage["child_agent_usages"].append(usage)
        except Exception:
            return

    def _normalize_task(self, tool_input: Any, kwargs: Dict[str, Any]) -> str:
        if kwargs:
            return json.dumps(kwargs, ensure_ascii=False)
        if isinstance(tool_input, dict):
            return json.dumps(tool_input, ensure_ascii=False)
        if tool_input is None:
            return self.original_question
        return str(tool_input)

    async def _ask_expert(self, expert_name: str, task: str) -> str:
        expert_tools = self.registry.get_tools_for_expert(expert_name)
        if not expert_tools:
            return json.dumps(
                {
                    "answer": "当前专家没有可用工具。",
                    "used_tools": [],
                    "documents": [],
                    "rag_results": [],
                    "confidence": 0,
                },
                ensure_ascii=False,
            )

        documents: List[Dict[str, Any]] = []
        rag_results: List[Dict[str, Any]] = []
        raw_process: List[Dict[str, Any]] = []

        expert_input = self.context_builder.build_expert_input(
            expert_name=expert_name,
            task=task,
            original_question=self.original_question,
            history=self.history,
        )
        expert_prompt = await self.registry.get_prompt_for_expert(expert_name)
        expert = PromptedReActAgent(
            llm_service=self.llm_service,
            tools=expert_tools,
            prompt_template=expert_prompt,
            max_iterations=AGENT_MAX_ITERATIONS,
            verbose=False,
            callback=self._build_expert_callback(
                expert_name,
                self.registry.get_definition(expert_name).display_name,
                documents,
                rag_results,
                raw_process,
            ),
        )
        answer = await expert.run_stream(expert_input)
        return json.dumps(
            {
                "answer": answer,
                "used_tools": list(expert_tools.keys()),
                "documents": documents,
                "rag_results": rag_results,
                "process_summary": self._summarize_process(raw_process),
                "raw_process": raw_process,
                "confidence": 1,
            },
            ensure_ascii=False,
        )

    async def _plan_tasks(self, user_message: str) -> List[Dict[str, Any]]:
        available = {definition.name: definition for definition in await self.registry.available_experts()}
        lowered = user_message.lower()
        selected: List[str] = []

        for expert_key, definition in available.items():
            text = f"{definition.display_name} {definition.description}".lower()
            if any(word and word in user_message for word in self._selection_terms(definition)):
                selected.append(expert_key)
                continue
            if any(word in lowered for word in ["email", "mail"]) and "邮件" in text:
                selected.append(expert_key)

        if not selected and available:
            selected.append(next(iter(available.keys())))

        context = self.context_builder.build_expert_input(
            expert_name="",
            task="",
            original_question=self.original_question,
            history=self.history,
        )
        tasks = []
        for expert_key in dict.fromkeys(selected):
            definition = available[expert_key]
            tasks.append(self.task_queue.build_task(
                question_id=self.question_id,
                expert_key=expert_key,
                task=f"{definition.display_name}处理：{user_message}",
                context=context,
            ))
        return tasks

    @staticmethod
    def _selection_terms(definition) -> List[str]:
        text = f"{definition.display_name} {definition.description}"
        common_terms = ["知识库", "文档", "资料", "制度", "搜索", "攻略", "推荐", "新闻", "查询", "官网", "天气", "路线", "位置", "地址", "景点", "附近", "经纬度", "邮件"]
        return [term for term in common_terms if term in text]

    async def _dispatch_and_run_task(self, task: Dict[str, Any]) -> None:
        expert_key = task["expert_key"]
        definition = self.registry.get_definition(expert_key)
        self._capture_child_context_usage(task, definition)
        self.task_queue.send_task(task)
        self._emit("expert_task_status", {
            "question_id": self.question_id,
            "task_id": task["task_id"],
            "expert_key": expert_key,
            "status": "created",
            "message": f"{definition.display_name}已开始处理。",
        })
        self._emit_agent_process(
            "supervisor",
            "supervisor",
            "主助手",
            "call",
            f"{definition.display_name}\n任务：{task.get('task', '')}",
            self._next_step(),
        )

        await self._wait_for_task_result(task)

    async def _wait_for_task_result(self, task: Dict[str, Any]) -> None:
        question_id = task["question_id"]
        task_id = task["task_id"]
        known_count = len(self.result_store.get_results(question_id)) + len(self.result_store.get_dead_letters(question_id))
        waited = 0.0

        while True:
            results = self.result_store.get_results(question_id)
            for result in results:
                if result.get("task_id") == task_id and int(result.get("retry_count") or 0) == int(task.get("retry_count") or 0):
                    await self._handle_task_result(task, result)
                    return

            dead_letters = self.result_store.get_dead_letters(question_id)
            for failed_task in dead_letters:
                if failed_task.get("task_id") == task_id and int(failed_task.get("retry_count") or 0) == int(task.get("retry_count") or 0):
                    self._emit_dead_letter_status(task, failed_task)
                    return

            wait_slice = 0.2
            await asyncio.to_thread(self.result_store.wait_for_update, question_id, known_count, wait_slice)
            waited += wait_slice
            known_count = len(self.result_store.get_results(question_id)) + len(self.result_store.get_dead_letters(question_id))
            if waited >= EXPERT_RESULT_WAIT_TIMEOUT_SECONDS:
                result = await self._run_task_locally(task)
                self.result_store.add_result(result)
                await self._handle_task_result(task, result)
                return

    async def _run_task_locally(self, task: Dict[str, Any]) -> Dict[str, Any]:
        expert_key = task["expert_key"]
        try:
            payload = json.loads(await self._ask_expert(expert_key, task["task"]))
            answer_text = str(payload.get("answer") or "").strip()
            success = self._is_useful_answer(answer_text)
            return {
                "question_id": task["question_id"],
                "task_id": task["task_id"],
                "expert_key": expert_key,
                "answer": answer_text,
                "process_summary": payload.get("process_summary", ""),
                "raw_process": payload.get("raw_process", []),
                "documents": payload.get("documents", []),
                "rag_results": payload.get("rag_results", []),
                "success": success,
                "error": "" if success else "结果不可用",
                "retry_count": task.get("retry_count", 0),
            }
        except Exception as exc:
            return {
                "question_id": task["question_id"],
                "task_id": task["task_id"],
                "expert_key": expert_key,
                "answer": "",
                "process_summary": "",
                "raw_process": [],
                "documents": [],
                "rag_results": [],
                "success": False,
                "error": str(exc),
                "retry_count": task.get("retry_count", 0),
            }

    async def _handle_task_result(self, task: Dict[str, Any], result: Dict[str, Any]) -> None:
        expert_key = task["expert_key"]
        definition = self.registry.get_definition(expert_key)
        answer_text = str(result.get("answer") or "").strip()
        success = bool(result.get("success")) and self._is_useful_answer(answer_text)
        raw_process = result.get("raw_process", [])
        self._emit_expert_processes(definition, raw_process)

        if success:
            self._emit("expert_task_status", {
                "question_id": self.question_id,
                "task_id": task["task_id"],
                "expert_key": expert_key,
                "status": "completed",
                "message": f"{definition.display_name}已返回结果。",
                "result": {
                    "answer": result["answer"],
                    "process_summary": result.get("process_summary", ""),
                    "success": True,
                },
            })
            self._emit_agent_process(
                "supervisor",
                "supervisor",
                "主助手",
                "observation",
                f"{definition.display_name}输出：{answer_text}",
                self._next_step(),
            )
            return

        retry_count = int(task.get("retry_count") or 0)
        if retry_count + 1 >= self.task_queue.max_retries:
            failure = {
                **task,
                "success": False,
                "error": result.get("error", "结果不可用"),
                "raw_process": result.get("raw_process", []),
                "retry_count": retry_count,
            }
            if self.task_queue.client:
                self.task_queue.client.send_message(
                    topic=self.task_queue.topics["dead_letters"],
                    message=failure,
                    key=task.get("question_id"),
                )
            self.result_store.add_dead_letter(failure)
            self._emit_dead_letter_status(task, failure)
            return

        task["retry_count"] = retry_count + 1
        task["feedback"] = self.task_queue.build_retry_feedback(
            result.get("error", "结果不可用"),
            result.get("raw_process", []),
        )

        self._emit("expert_task_status", {
            "question_id": self.question_id,
            "task_id": task["task_id"],
            "expert_key": expert_key,
            "status": "retrying",
            "message": f"{definition.display_name}正在重新处理。",
        })
        await self._dispatch_and_run_task(task)

    def _emit_expert_processes(self, definition, raw_process: List[Dict[str, Any]]) -> None:
        for item in self._merge_expert_processes(raw_process):
            phase = str(item.get("phase") or "").strip()
            if not phase:
                continue
            self._emit_expert_process_once(definition, phase, str(item.get("content") or ""))

    def _emit_expert_process_once(self, definition, phase: str, content: Any) -> None:
        cleaned = self._clean_process_display_text(phase, str(content or ""))
        if not cleaned:
            return
        process_key = (definition.name, phase, cleaned)
        if process_key in self._emitted_expert_process_keys:
            return
        self._emitted_expert_process_keys.add(process_key)
        self._emit_agent_process(
            "expert",
            definition.name,
            definition.display_name,
            phase,
            cleaned,
            self._next_step(),
        )

    @classmethod
    def _merge_expert_processes(cls, raw_process: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        for item in raw_process:
            phase = str(item.get("phase") or "").strip()
            content = str(item.get("content") or "")
            if not phase or not content.strip():
                continue
            if cls._is_process_marker_only(content):
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

    def _emit_dead_letter_status(self, task: Dict[str, Any], result: Dict[str, Any]) -> None:
        expert_key = task["expert_key"]
        definition = self.registry.get_definition(expert_key)
        self.dead_letter_tasks.append(result)
        self._emit("expert_task_status", {
            "question_id": self.question_id,
            "task_id": task["task_id"],
            "expert_key": expert_key,
            "status": "dead_letter",
            "message": f"{definition.display_name}暂时无法返回可用结果。",
            "result": {
                "answer": "",
                "process_summary": "",
                "success": False,
                "error": result.get("error", ""),
            },
        })

    def _compose_answer(self, results: List[Dict[str, Any]]) -> str:
        useful = [item for item in results if item.get("success") and item.get("answer")]
        if not useful:
            return "抱歉，当前专家暂时没有返回可用结果。"
        if len(useful) == 1:
            return useful[0]["answer"]
        parts = []
        for item in useful:
            definition = self.registry.get_definition(item["expert_key"])
            parts.append(f"{definition.display_name}：{item['answer']}")
        if self.dead_letter_tasks:
            parts.append("部分内容暂时无法确认，已基于可用结果整理。")
        return "\n\n".join(parts)

    async def _save_experience(self, answer: str, results: List[Dict[str, Any]]) -> None:
        try:
            from internal.service.ai.expert_experience_store import expert_experience_store

            experience_id = await expert_experience_store.save_experience(
                question_id=self.question_id,
                question=self.original_question,
                answer=answer,
                expert_results=results,
                failed_tasks=self.dead_letter_tasks,
                should_cache=bool(results or self.dead_letter_tasks),
            )
            if experience_id:
                self._emit("expert_experience", {"experience_chain_id": experience_id})
        except Exception:
            return

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
    def _clean_display_text(text: str) -> str:
        blocked = ["debug", "stack", "trace", "topic=", "kafka", "接口", "代码", "修改"]
        lowered = text.lower()
        if any(word in lowered for word in blocked):
            return ""
        return text

    @classmethod
    def _clean_process_display_text(cls, phase: str, text: str) -> str:
        text = str(text or "").strip()
        if not text:
            return ""
        cleaned = cls._clean_display_text(text)
        if not cleaned:
            return ""
        if cleaned.strip().lower() in {"question", "question:", "开始！", "开始!"}:
            return ""

        marker_pattern = r"^\s*(thought|action input|observation|final answer|finalanswer)\s*:\s*"
        cleaned = re.sub(marker_pattern, "", cleaned, count=1, flags=re.I).strip()
        cleaned = re.sub(r"^\s*[:：]\s*", "", cleaned).strip()
        marker_labels = {
            "thought": "思考",
            "action": "操作",
            "action input": "操作",
            "observation": "观测",
            "final answer": "输出",
            "finalanswer": "输出",
        }

        def localize_marker(match):
            label = marker_labels.get(match.group(1).lower(), match.group(1))
            return f"{label}："

        return re.sub(
            r"\b(thought|action|action input|observation|final answer|finalanswer)\s*:\s*",
            localize_marker,
            cleaned,
            flags=re.I,
        ).strip()

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

    @staticmethod
    def _resolve_queue_client():
        try:
            from internal.document_client.message_client import message_client

            return message_client.client if message_client.mode == "kafka" else None
        except Exception:
            return None

    @staticmethod
    def _resolve_queue_topics() -> Dict[str, str]:
        try:
            from internal.document_client.config_loader import config

            topics = config.get("kafka.topics", {}) or {}
            return {
                "tasks": topics.get("expert_tasks", "expert_tasks"),
                "results": topics.get("expert_results", "expert_results"),
                "dead_letters": topics.get("expert_dead_letters", "expert_dead_letters"),
            }
        except Exception:
            return {}
