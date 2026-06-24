"""RAGAS 评估队列。"""
from __future__ import annotations

from typing import Any, Dict


RAG_EVALUATION_TOPIC = "rag_evaluation"


class RAGEvaluationQueueProducer:
    """RAGAS Kafka 队列生产者。"""

    def __init__(self, topic: str = RAG_EVALUATION_TOPIC):
        self.topic = topic

    def enqueue(self, record: Any) -> bool:
        try:
            from internal.document_client.message_client import message_client

            return message_client.send_message(
                message=self.build_message(record),
                topic=self.topic,
                key=str(getattr(record, "id", "") or getattr(record, "target_id", "")),
            )
        except Exception:
            return False

    def build_message(self, record: Any) -> Dict[str, Any]:
        created_at = getattr(record, "created_at", None)
        return {
            "evaluation_id": str(getattr(record, "id", "") or ""),
            "question": getattr(record, "question", "") or "",
            "answer": getattr(record, "answer", "") or "",
            "retrieved_text": getattr(record, "retrieved_text", "") or "",
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else "",
        }


queue_producer = RAGEvaluationQueueProducer()
