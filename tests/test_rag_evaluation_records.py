import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from internal.service.evaluation.rag_evaluation_service import RAGEvaluationService


class FakeEvaluationRecord:
    records = []
    target_type = object()
    question = object()
    ragas_status = object()
    created_at = object()

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.insert = AsyncMock(side_effect=self._insert)
        self.save = AsyncMock()

    async def _insert(self):
        FakeEvaluationRecord.records.append(self)

    @classmethod
    def find(cls, *_conditions):
        return FakeEvaluationQuery(cls.records)

    @classmethod
    async def count(cls):
        return len(cls.records)


class FakeEvaluationQuery:
    def __init__(self, records):
        self.records = list(records)

    def sort(self, *_args):
        self.records.sort(key=lambda item: item.created_at, reverse=True)
        return self

    def skip(self, count):
        self.records = self.records[count:]
        return self

    def limit(self, count):
        self.records = self.records[:count]
        return self

    async def to_list(self):
        return self.records

    async def count(self):
        return len(self.records)


class FakeProductionRAGASEvaluator:
    async def evaluate_production(self, question, answer, contexts):
        return {
            "faithfulness": 0.82,
            "answer_relevance": 0.76,
            "context_precision": 0.91,
        }


class FailingProductionRAGASEvaluator:
    async def evaluate_production(self, question, answer, contexts):
        raise RuntimeError("ragas failed")


class FakeQueueProducer:
    def __init__(self, success=True):
        self.success = success
        self.messages = []

    def enqueue(self, record):
        self.messages.append(record)
        return self.success


class RAGEvaluationRecordServiceTest(unittest.TestCase):
    def setUp(self):
        FakeEvaluationRecord.records = []

    def test_save_rag_call_records_chunks_with_scores(self):
        queue = FakeQueueProducer()
        service = RAGEvaluationService(
            evaluation_model=FakeEvaluationRecord,
            ragas_evaluator=FakeProductionRAGASEvaluator(),
            queue_producer=queue,
        )

        records = asyncio.run(service.save_rag_call_records(
            question="制度怎么查询？",
            answer="可以在知识库查询。",
            session_id="session-1",
            user_id="user-1",
            message_id="message-1",
            rag_results=[
                {
                    "text": "制度查询说明正文",
                    "metadata": {
                        "document_uuid": "doc-1",
                        "filename": "制度说明.pdf",
                        "chunk_index": 2,
                    },
                    "vector_score": 0.71,
                    "rerank_score": 0.86,
                }
            ],
        ))

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].question, "制度怎么查询？")
        self.assertEqual(records[0].answer, "可以在知识库查询。")
        self.assertEqual(records[0].retrieved_text, "制度查询说明正文")
        self.assertEqual(records[0].document_uuid, "doc-1")
        self.assertEqual(records[0].filename, "制度说明.pdf")
        self.assertEqual(records[0].chunk_index, 2)
        self.assertEqual(records[0].vector_score, 0.71)
        self.assertEqual(records[0].rerank_score, 0.86)
        self.assertEqual(records[0].overall_score, 0.86)
        self.assertEqual(records[0].ragas_status, "queued")
        self.assertEqual(records[0].queue_status, "queued")
        self.assertIsNotNone(records[0].queued_at)
        self.assertEqual(len(queue.messages), 1)
        records[0].insert.assert_awaited_once()

    def test_no_rag_results_do_not_create_records(self):
        service = RAGEvaluationService(evaluation_model=FakeEvaluationRecord)

        records = asyncio.run(service.save_rag_call_records(
            question="你好",
            answer="你好",
            session_id="session-1",
            user_id="user-1",
            message_id="message-1",
            rag_results=[],
        ))

        self.assertEqual(records, [])
        self.assertEqual(FakeEvaluationRecord.records, [])

    def test_disabled_ragas_marks_records_skipped_without_queueing(self):
        queue = FakeQueueProducer()
        service = RAGEvaluationService(
            evaluation_model=FakeEvaluationRecord,
            queue_producer=queue,
        )
        service.update_config({"ragas_enabled": False})

        records = asyncio.run(service.save_rag_call_records(
            question="制度怎么查询？",
            answer="可以在知识库查询。",
            session_id="session-1",
            user_id="user-1",
            message_id="message-1",
            rag_results=[{"text": "制度查询说明正文", "metadata": {}, "vector_score": 0.71}],
        ))

        self.assertEqual(records[0].queue_status, "skipped")
        self.assertEqual(records[0].ragas_status, "skipped")
        self.assertEqual(queue.messages, [])

    def test_queue_failure_keeps_chat_path_non_blocking(self):
        queue = FakeQueueProducer(success=False)
        service = RAGEvaluationService(
            evaluation_model=FakeEvaluationRecord,
            queue_producer=queue,
        )

        records = asyncio.run(service.save_rag_call_records(
            question="制度怎么查询？",
            answer="可以在知识库查询。",
            session_id="session-1",
            user_id="user-1",
            message_id="message-1",
            rag_results=[{"text": "制度查询说明正文", "metadata": {}, "vector_score": 0.71}],
        ))

        self.assertEqual(records[0].queue_status, "failed")
        self.assertEqual(records[0].ragas_status, "failed")
        self.assertEqual(records[0].ragas_error, "评估任务入队失败")

    def test_ragas_success_updates_records(self):
        service = RAGEvaluationService(
            evaluation_model=FakeEvaluationRecord,
            ragas_evaluator=FakeProductionRAGASEvaluator(),
        )
        record = FakeEvaluationRecord(
            question="制度怎么查询？",
            answer="可以在知识库查询。",
            retrieved_text="制度查询说明正文",
            ragas_status="pending",
            created_at=datetime.now(),
        )

        asyncio.run(service.run_ragas_for_records([record]))

        self.assertEqual(record.queue_status, "completed")
        self.assertEqual(record.faithfulness, 0.82)
        self.assertEqual(record.answer_relevance, 0.76)
        self.assertEqual(record.context_precision, 0.91)
        self.assertEqual(record.context_recall, 0.0)
        self.assertEqual(record.ragas_status, "completed")
        self.assertEqual(record.ragas_error, "")
        self.assertEqual(record.save.await_count, 2)

    def test_ragas_failure_marks_failed_without_raising(self):
        service = RAGEvaluationService(
            evaluation_model=FakeEvaluationRecord,
            ragas_evaluator=FailingProductionRAGASEvaluator(),
        )
        record = FakeEvaluationRecord(
            question="制度怎么查询？",
            answer="可以在知识库查询。",
            retrieved_text="制度查询说明正文",
            ragas_status="pending",
            created_at=datetime.now(),
        )

        asyncio.run(service.run_ragas_for_records([record]))

        self.assertEqual(record.queue_status, "failed")
        self.assertEqual(record.ragas_status, "failed")
        self.assertEqual(record.ragas_error, "评估失败")
        self.assertEqual(record.save.await_count, 2)

    def test_get_rag_evaluation_list_filters_keyword_and_status(self):
        now = datetime.now()
        FakeEvaluationRecord.records = [
            SimpleNamespace(
                target_type="rag_chunk",
                question="制度怎么查询？",
                answer="可以在知识库查询。",
                retrieved_text="制度查询说明正文",
                filename="制度说明.pdf",
                document_uuid="doc-1",
                chunk_index=1,
                vector_score=0.7,
                rerank_score=0.8,
                overall_score=0.8,
                faithfulness=0.82,
                answer_relevance=0.76,
                context_precision=0.91,
                context_recall=0.0,
                ragas_status="completed",
                queue_status="completed",
                ragas_error="",
                queued_at=now,
                started_at=now,
                completed_at=now,
                retry_count=0,
                created_at=now,
            ),
            SimpleNamespace(
                target_type="rag_chunk",
                question="闲聊问题",
                answer="你好",
                retrieved_text="",
                filename="",
                document_uuid="",
                chunk_index=0,
                vector_score=0.0,
                rerank_score=0.0,
                overall_score=0.0,
                faithfulness=0.0,
                answer_relevance=0.0,
                context_precision=0.0,
                context_recall=0.0,
                ragas_status="queued",
                queue_status="queued",
                ragas_error="",
                queued_at=now,
                started_at=None,
                completed_at=None,
                retry_count=0,
                created_at=now,
            ),
        ]
        service = RAGEvaluationService(evaluation_model=FakeEvaluationRecord)

        data = asyncio.run(service.get_rag_evaluation_list(
            page=1,
            page_size=20,
            keyword="制度",
            ragas_status="completed",
        ))

        self.assertEqual(data["total"], 1)
        self.assertEqual(data["completed_count"], 1)
        self.assertEqual(data["pending_count"], 0)
        self.assertEqual(data["items"][0]["question"], "制度怎么查询？")
        self.assertEqual(data["items"][0]["retrieved_text"], "制度查询说明正文")

    def test_requeue_failed_record_marks_queued_and_enqueues(self):
        queue = FakeQueueProducer()
        record = FakeEvaluationRecord(
            question="制度怎么查询？",
            answer="可以在知识库查询。",
            retrieved_text="制度查询说明正文",
            queue_status="failed",
            ragas_status="failed",
            retry_count=1,
            created_at=datetime.now(),
        )
        service = RAGEvaluationService(evaluation_model=FakeEvaluationRecord, queue_producer=queue)

        result = asyncio.run(service.requeue_record(record))

        self.assertTrue(result)
        self.assertEqual(record.queue_status, "queued")
        self.assertEqual(record.ragas_status, "queued")
        self.assertEqual(record.retry_count, 2)
        self.assertEqual(len(queue.messages), 1)

    def test_consume_queue_task_moves_running_then_completed(self):
        record = FakeEvaluationRecord(
            question="制度怎么查询？",
            answer="可以在知识库查询。",
            retrieved_text="制度查询说明正文",
            queue_status="queued",
            ragas_status="queued",
            retry_count=0,
            created_at=datetime.now(),
        )
        service = RAGEvaluationService(
            evaluation_model=FakeEvaluationRecord,
            ragas_evaluator=FakeProductionRAGASEvaluator(),
        )

        asyncio.run(service.consume_queue_record(record))

        self.assertEqual(record.queue_status, "completed")
        self.assertEqual(record.ragas_status, "completed")
        self.assertIsNotNone(record.started_at)
        self.assertIsNotNone(record.completed_at)


if __name__ == "__main__":
    unittest.main()
