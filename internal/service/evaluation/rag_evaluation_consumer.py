"""RAGAS 评估队列消费者。"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from internal.service.evaluation.rag_evaluation_queue import RAG_EVALUATION_TOPIC


def handle_rag_evaluation_message(message: Dict[str, Any]) -> None:
    """处理一条 RAGAS 评估消息。"""
    asyncio.run(_handle_message(message))


async def _handle_message(message: Dict[str, Any]) -> None:
    from internal.model.evaluation import EvaluationModel
    from internal.service.evaluation.rag_evaluation_service import RAGEvaluationService

    evaluation_id = message.get("evaluation_id")
    if not evaluation_id:
        return
    record = await EvaluationModel.get(evaluation_id)
    if not record:
        return
    service = RAGEvaluationService()
    await service.consume_queue_record(record)


def start_rag_evaluation_consumer() -> None:
    """启动 RAGAS 评估 Kafka 消费者。"""
    from internal.document_client.message_client import message_client

    message_client.start_consumer(
        handler=handle_rag_evaluation_message,
        topic=RAG_EVALUATION_TOPIC,
    )
