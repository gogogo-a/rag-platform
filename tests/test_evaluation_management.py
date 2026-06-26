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
    queue_status = object()
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


class FakeEvaluationQuery:
    def __init__(self, records):
        self.records = list(records)

    def sort(self, *_args):
        self.records.sort(key=lambda item: item.created_at, reverse=True)
        return self

    async def to_list(self):
        return self.records


class FakeConfigRecord:
    def __init__(self, **kwargs):
        self.key = kwargs.get("key", "ragas")
        self.ragas_enabled = kwargs.get("ragas_enabled", True)
        self.ragas_queue_enabled = kwargs.get("ragas_queue_enabled", True)
        self.ragas_sample_rate = kwargs.get("ragas_sample_rate", 1.0)
        self.ragas_max_chunks_per_question = kwargs.get("ragas_max_chunks_per_question", 3)
        self.ragas_min_retrieval_score = kwargs.get("ragas_min_retrieval_score", 0.05)
        self.evaluation_enabled = kwargs.get("evaluation_enabled", True)
        self.evaluation_sample_rate = kwargs.get("evaluation_sample_rate", 0.3)
        self.updated_at = kwargs.get("updated_at", datetime.now())
        self.save = AsyncMock()


class FakeConfigModel:
    key = object()
    record = None

    def __init__(self, **kwargs):
        FakeConfigModel.record = FakeConfigRecord(**kwargs)
        self.__dict__.update(FakeConfigModel.record.__dict__)
        self.save = FakeConfigModel.record.save

    @classmethod
    def find_one(cls, *_conditions):
        return FakeConfigAwaitable(cls.record)


class FakeConfigAwaitable:
    def __init__(self, record):
        self.record = record

    def __await__(self):
        async def _result():
            return self.record
        return _result().__await__()


class FakeLLMQualityEvaluator:
    async def evaluate(self, question, answer, contexts, evaluation_type="rag"):
        return {
            "score": 0.92,
            "reason": "回答直接解决了问题，内容清楚且可执行。",
        }


class FakeQueueProducer:
    def __init__(self):
        self.messages = []

    def enqueue(self, record):
        self.messages.append(record)
        return True


class EvaluationManagementServiceTest(unittest.TestCase):
    def setUp(self):
        FakeEvaluationRecord.records = []
        FakeConfigModel.record = None

    def test_config_defaults_include_reply_evaluation_sample_rate(self):
        service = RAGEvaluationService(
            evaluation_model=FakeEvaluationRecord,
            config_model=FakeConfigModel,
        )

        config = asyncio.run(service.get_config())

        self.assertTrue(config["evaluation_enabled"])
        self.assertEqual(config["evaluation_sample_rate"], 0.3)

    def test_config_save_updates_reply_evaluation_sample_rate(self):
        FakeConfigModel.record = FakeConfigRecord()
        service = RAGEvaluationService(
            evaluation_model=FakeEvaluationRecord,
            config_model=FakeConfigModel,
        )

        config = asyncio.run(service.save_config({
            "evaluation_enabled": False,
            "evaluation_sample_rate": 0.65,
        }))

        self.assertFalse(config["evaluation_enabled"])
        self.assertEqual(config["evaluation_sample_rate"], 0.65)
        self.assertFalse(FakeConfigModel.record.evaluation_enabled)
        self.assertEqual(FakeConfigModel.record.evaluation_sample_rate, 0.65)

    def test_sample_rate_zero_skips_normal_reply_evaluation(self):
        service = self._service()
        service.update_config({"evaluation_sample_rate": 0.0})

        record = asyncio.run(service.save_reply_evaluation_record(
            question="你好",
            answer="你好，有什么可以帮你？",
            session_id="session-1",
            user_id="user-1",
            message_id="message-1",
            extra_data={},
        ))

        self.assertIsNone(record)
        self.assertEqual(FakeEvaluationRecord.records, [])

    def test_sample_rate_one_creates_normal_reply_evaluation(self):
        service = self._service()
        service.update_config({"evaluation_sample_rate": 1.0})

        record = asyncio.run(service.save_reply_evaluation_record(
            question="你好",
            answer="你好，有什么可以帮你？",
            session_id="session-1",
            user_id="user-1",
            message_id="message-1",
            extra_data={},
        ))

        self.assertEqual(record.evaluation_type, "normal_reply")
        self.assertEqual(record.llm_score, 0.92)
        self.assertEqual(record.rule_score, 1.0)
        self.assertEqual(record.overall_score, 0.936)
        self.assertEqual(record.score_reason, "回答直接解决了问题，内容清楚且可执行。")
        self.assertEqual(record.queue_status, "completed")

    def test_creates_long_context_evaluation(self):
        service = self._service()
        service.update_config({"evaluation_sample_rate": 1.0})

        record = asyncio.run(service.save_reply_evaluation_record(
            question="总结长文",
            answer="总结如下。",
            session_id="session-1",
            user_id="user-1",
            message_id="message-long",
            extra_data={"agent_context_usage": {"primary_agent_usage": {"percent": 82}}},
        ))

        self.assertEqual(record.evaluation_type, "long_context")

    def test_creates_tool_call_evaluation(self):
        service = self._service()
        service.update_config({"evaluation_sample_rate": 1.0})

        record = asyncio.run(service.save_reply_evaluation_record(
            question="查天气",
            answer="今天适合出行。",
            session_id="session-1",
            user_id="user-1",
            message_id="message-tool",
            extra_data={"actions": ["weather_query({})"]},
        ))

        self.assertEqual(record.evaluation_type, "tool_call")

    def test_creates_multi_agent_evaluation(self):
        service = self._service()
        service.update_config({"evaluation_sample_rate": 1.0})

        record = asyncio.run(service.save_reply_evaluation_record(
            question="让专家分析",
            answer="综合判断如下。",
            session_id="session-1",
            user_id="user-1",
            message_id="message-agent",
            extra_data={"expert_results": [{"answer": "结论"}]},
        ))

        self.assertEqual(record.evaluation_type, "multi_agent")

    def test_management_list_contains_all_evaluation_types(self):
        now = datetime.now()
        FakeEvaluationRecord.records = [
            self._record("eval-rag", "rag", now),
            self._record("eval-normal", "normal_reply", now),
            self._record("eval-long", "long_context", now),
            self._record("eval-tool", "tool_call", now),
            self._record("eval-agent", "multi_agent", now),
        ]
        service = self._service()

        data = asyncio.run(service.get_evaluation_management_list(page=1, page_size=20))

        self.assertEqual(data["type_counts"]["rag"], 1)
        self.assertEqual(data["type_counts"]["normal_reply"], 1)
        self.assertEqual(data["type_counts"]["long_context"], 1)
        self.assertEqual(data["type_counts"]["tool_call"], 1)
        self.assertEqual(data["type_counts"]["multi_agent"], 1)

    def test_management_list_exposes_regression_case_metadata(self):
        now = datetime.now()
        FakeEvaluationRecord.records = [
            self._record(
                "eval-case",
                "tool_call",
                now,
                case_id="mcp:weather_query",
                case_name="天气查询",
                suite_type="mcp",
                turn_index=1,
                agent_mode="single",
                target_agent="",
                required_tools=["weather_query"],
                triggered_tools=["weather_query"],
            )
        ]
        service = self._service()

        data = asyncio.run(service.get_evaluation_management_list(
            page=1,
            page_size=20,
            evaluation_type="tool_call",
        ))

        row = data["items"][0]
        self.assertEqual(row["case_id"], "mcp:weather_query")
        self.assertEqual(row["case_name"], "天气查询")
        self.assertEqual(row["suite_type"], "mcp")
        self.assertEqual(row["turn_index"], 1)
        self.assertEqual(row["agent_mode"], "single")
        self.assertEqual(row["required_tools"], ["weather_query"])
        self.assertEqual(row["triggered_tools"], ["weather_query"])

    def test_rag_evaluation_uses_unified_evaluation_sample_rate(self):
        queue = FakeQueueProducer()
        service = self._service(queue_producer=queue)
        service.update_config({
            "evaluation_sample_rate": 0.0,
            "ragas_enabled": True,
            "ragas_queue_enabled": True,
            "ragas_sample_rate": 1.0,
        })

        records = asyncio.run(service.save_rag_call_records(
            question="制度怎么查询？",
            answer="可以在知识库查询。",
            session_id="session-1",
            user_id="user-1",
            message_id="message-1",
            rag_results=[{"text": "制度查询说明正文", "metadata": {}, "vector_score": 0.71}],
        ))

        self.assertEqual(records[0].evaluation_type, "rag")
        self.assertEqual(records[0].queue_status, "skipped")
        self.assertEqual(len(queue.messages), 0)

    def _service(self, queue_producer=None):
        return RAGEvaluationService(
            evaluation_model=FakeEvaluationRecord,
            config_model=FakeConfigModel,
            queue_producer=queue_producer or FakeQueueProducer(),
            llm_quality_evaluator=FakeLLMQualityEvaluator(),
        )

    def _record(self, record_id, evaluation_type, now, **overrides):
        data = dict(
            id=record_id,
            target_type="rag_chunk" if evaluation_type == "rag" else "message",
            evaluation_type=evaluation_type,
            question="问题",
            answer="回答",
            retrieved_text="返回文本" if evaluation_type == "rag" else "",
            filename="",
            document_uuid="",
            chunk_index=0,
            vector_score=0.0,
            rerank_score=0.0,
            overall_score=0.9,
            llm_score=0.9,
            rule_score=0.9,
            score_reason="评分原因",
            score_breakdown={"weights": {"llm": 0.8, "rule": 0.2}},
            faithfulness=0.0,
            answer_relevance=0.0,
            context_precision=0.0,
            context_recall=0.0,
            ragas_status="completed",
            queue_status="completed",
            ragas_error="",
            queued_at=now,
            started_at=now,
            completed_at=now,
            retry_count=0,
            created_at=now,
        )
        data.update(overrides)
        return SimpleNamespace(**data)


if __name__ == "__main__":
    unittest.main()
