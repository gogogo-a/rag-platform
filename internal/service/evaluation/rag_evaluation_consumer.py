"""RAGAS 评估队列消费者。"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from internal.service.evaluation.rag_evaluation_queue import RAG_EVALUATION_TOPIC
from log import logger


_consumer_loop: asyncio.AbstractEventLoop | None = None


def handle_rag_evaluation_message(message: Dict[str, Any]) -> None:
    """处理一条 RAGAS 评估消息。"""
    try:
        if _consumer_loop and _consumer_loop.is_running():
            future = asyncio.run_coroutine_threadsafe(_handle_message(message), _consumer_loop)
            future.result()
        else:
            asyncio.run(_handle_message(message))
    except Exception as exc:
        logger.error(f"RAGAS 评估消息处理失败: {exc}", exc_info=True)


async def _handle_message(message: Dict[str, Any]) -> None:
    from internal.model.evaluation import EvaluationModel
    from internal.service.evaluation.rag_evaluation_service import RAGEvaluationService

    evaluation_id = message.get("evaluation_id")
    if not evaluation_id:
        logger.warning("RAGAS 评估消息缺少 evaluation_id")
        return
    record = await EvaluationModel.get(evaluation_id)
    if not record:
        logger.warning(f"RAGAS 评估记录不存在: {evaluation_id}")
        return
    service = RAGEvaluationService()
    await service.consume_queue_record(record)


def recover_pending_rag_evaluations() -> None:
    """恢复已经入库但未完成的 RAGAS 评估记录。"""
    try:
        recovered = asyncio.run(_recover_pending_records())
        if recovered:
            logger.info(f"已恢复待评估任务: {recovered}")
    except Exception as exc:
        logger.error(f"恢复待评估任务失败: {exc}", exc_info=True)


async def _recover_pending_records() -> int:
    from internal.service.evaluation.rag_evaluation_service import RAGEvaluationService

    service = RAGEvaluationService()
    return await service.recover_pending_queue_records()


def start_rag_evaluation_consumer() -> None:
    """启动 RAGAS 评估 Kafka 消费者。"""
    global _consumer_loop
    from internal.document_client.message_client import message_client

    try:
        _consumer_loop = asyncio.get_running_loop()
    except RuntimeError:
        _consumer_loop = None

    message_client.start_consumer(
        handler=handle_rag_evaluation_message,
        topic=RAG_EVALUATION_TOPIC,
    )
    try:
        loop = _consumer_loop or asyncio.get_running_loop()
    except RuntimeError:
        recover_pending_rag_evaluations()
    else:
        loop.create_task(_recover_pending_records())
