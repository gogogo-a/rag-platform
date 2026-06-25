"""Expert task, result, and dead-letter consumers."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from log import logger
from internal.agent.expert_task_queue import expert_result_store
from internal.agent.expert_worker import ExpertTaskWorker


_worker: Optional[ExpertTaskWorker] = None
_consumer_loop: Optional[asyncio.AbstractEventLoop] = None
_started = False


def start_expert_consumers(llm_service=None, tool_map: Optional[Dict[str, Any]] = None) -> None:
    global _worker, _consumer_loop, _started
    if _started:
        return

    from internal.document_client.config_loader import config
    from internal.document_client.message_client import message_client

    try:
        _consumer_loop = asyncio.get_running_loop()
    except RuntimeError:
        _consumer_loop = None
    topics = config.get("kafka.topics", {}) or {}
    resolved_topics = {
        "tasks": topics.get("expert_tasks", "expert_tasks"),
        "results": topics.get("expert_results", "expert_results"),
        "dead_letters": topics.get("expert_dead_letters", "expert_dead_letters"),
    }
    client = message_client.client if message_client.mode == "kafka" else None
    _worker = ExpertTaskWorker(
        llm_service=llm_service or _build_worker_llm_service(),
        tool_map=tool_map or {},
        client=client,
        topics=resolved_topics,
    )

    message_client.start_consumer(handle_expert_task_message, topic=resolved_topics["tasks"])
    message_client.start_consumer(handle_expert_result_message, topic=resolved_topics["results"])
    message_client.start_consumer(handle_expert_dead_letter_message, topic=resolved_topics["dead_letters"])
    _started = True


def stop_expert_consumers() -> None:
    global _worker, _consumer_loop, _started
    _worker = None
    _consumer_loop = None
    _started = False


def handle_expert_task_message(message: Dict[str, Any]) -> None:
    if not _worker:
        return
    if _consumer_loop and _consumer_loop.is_running():
        asyncio.run_coroutine_threadsafe(_worker.handle_task(message), _consumer_loop)
        return
    try:
        asyncio.run(_worker.handle_task(message))
    except Exception as exc:
        logger.warning(f"专家任务处理失败: {exc}")


def handle_expert_result_message(message: Dict[str, Any]) -> None:
    expert_result_store.add_result(message)


def handle_expert_dead_letter_message(message: Dict[str, Any]) -> None:
    expert_result_store.add_dead_letter(message)


def _build_worker_llm_service():
    from internal.chat_service.chat_service import ChatService
    from pkg.model_list import DEEPSEEK_CHAT

    return ChatService(
        session_id="expert-worker",
        user_id="expert-worker",
        model_name=DEEPSEEK_CHAT.name,
        model_type=DEEPSEEK_CHAT.model_type,
        system_prompt="你是一个专业助手，回答要准确、简洁、清晰。",
        tools=[],
        auto_summary=False,
        max_history_count=5,
    ).llm_service
