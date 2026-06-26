import asyncio
import unittest
from datetime import datetime
from unittest.mock import AsyncMock

from internal.service.evaluation.conversation_regression_service import (
    ConversationRegressionService,
    DEFAULT_REGRESSION_CASES,
)


class FakeEvaluationRecord:
    records = []
    suite_type = object()
    created_at = object()

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.insert = AsyncMock(side_effect=self._insert)

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


class FakeCaseModel:
    records = []
    created = []
    suite_type = object()
    enabled = object()
    created_at = object()

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.id = kwargs.get("case_id")
        self.insert = AsyncMock(side_effect=self._insert)

    async def _insert(self):
        FakeCaseModel.records.append(self)
        FakeCaseModel.created.append(self)

    @classmethod
    def find(cls, *_conditions):
        return FakeCaseQuery(cls.records)

    @classmethod
    async def get(cls, case_id):
        for record in cls.records:
            if record.case_id == case_id or str(getattr(record, "id", "")) == case_id:
                return record
        return None


class FakeCaseQuery:
    def __init__(self, records):
        self.records = list(records)

    def sort(self, *_args):
        self.records.sort(key=lambda item: item.created_at, reverse=True)
        return self

    async def to_list(self):
        return self.records


class FakeMessageService:
    def __init__(self):
        self.calls = []

    async def send_message_stream(self, **kwargs):
        self.calls.append(kwargs)
        session_id = kwargs.get("session_id") or "session-created"
        yield {"event": "session_created", "data": {"session_id": session_id, "session_name": "固定测试"}}
        if "天气" in kwargs["content"]:
            yield {"event": "action", "data": {"content": "查询天气"}}
        if kwargs.get("agent_mode") == "expert":
            yield {"event": "expert_result", "data": {"agent_key": "location", "answer": "位置建议"}}
        yield {"event": "answer_chunk", "data": {"content": f"回答：{kwargs['content']}"}}
        yield {"event": "ai_message_saved", "data": {"uuid": f"ai-{len(self.calls)}"}}
        yield {"event": "done", "data": {}}


class FakeQualityEvaluator:
    async def evaluate(self, question, answer, contexts, evaluation_type="normal_reply"):
        if "评分失败" in question:
            raise RuntimeError("score failed")
        return {"score": 0.91, "reason": "回答完整，表达清楚。"}


class ConversationRegressionServiceTest(unittest.TestCase):
    def setUp(self):
        FakeEvaluationRecord.records = []
        FakeCaseModel.records = []
        FakeCaseModel.created = []

    def test_default_cases_are_grouped_by_mcp_agent_and_flow(self):
        suite_types = {item["suite_type"] for item in DEFAULT_REGRESSION_CASES}
        case_ids = {item["case_id"] for item in DEFAULT_REGRESSION_CASES}

        self.assertEqual(suite_types, {"mcp", "agent", "flow"})
        self.assertIn("mcp:knowledge_search", case_ids)
        self.assertIn("agent:location", case_ids)
        self.assertIn("flow:long_context_single", case_ids)

    def test_seed_default_cases_does_not_duplicate_existing_cases(self):
        FakeCaseModel.records = [FakeCaseModel(**DEFAULT_REGRESSION_CASES[0])]
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        created = asyncio.run(service.ensure_default_cases())

        self.assertEqual(created, len(DEFAULT_REGRESSION_CASES) - 1)
        self.assertEqual(len({case.case_id for case in FakeCaseModel.records}), len(DEFAULT_REGRESSION_CASES))

    def test_run_case_reuses_session_and_writes_scores_for_each_turn(self):
        case = FakeCaseModel(
            case_id="mcp:weather_query",
            name="天气查询",
            suite_type="mcp",
            agent_mode="single",
            target_agent="",
            required_tools=["weather_query"],
            turns=[{"content": "今天上海天气如何？"}, {"content": "适合出门吗？"}],
            min_score=0.8,
            enabled=True,
            created_at=datetime.now(),
        )
        FakeCaseModel.records = [case]
        message_service = FakeMessageService()
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=message_service,
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        result = asyncio.run(service.run_case("mcp:weather_query", user_id="admin", send_name="管理员"))

        self.assertEqual(result["total_turns"], 2)
        self.assertEqual(result["completed_turns"], 2)
        self.assertEqual(message_service.calls[0]["session_id"], None)
        self.assertEqual(message_service.calls[1]["session_id"], "session-created")
        self.assertTrue(all(call["skip_cache"] for call in message_service.calls))
        self.assertEqual(len(FakeEvaluationRecord.records), 2)
        self.assertEqual(FakeEvaluationRecord.records[0].suite_type, "mcp")
        self.assertEqual(FakeEvaluationRecord.records[0].case_id, "mcp:weather_query")
        self.assertEqual(FakeEvaluationRecord.records[0].required_tools, ["weather_query"])
        self.assertEqual(FakeEvaluationRecord.records[0].evaluation_type, "tool_call")
        self.assertEqual(FakeEvaluationRecord.records[0].queue_status, "completed")

    def test_expert_case_is_saved_as_multi_agent(self):
        case = FakeCaseModel(
            case_id="agent:location",
            name="位置专家",
            suite_type="agent",
            agent_mode="expert",
            target_agent="location",
            required_tools=["poi_search"],
            turns=[{"content": "帮我找附近适合开会的地方"}],
            min_score=0.8,
            enabled=True,
            created_at=datetime.now(),
        )
        FakeCaseModel.records = [case]
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        asyncio.run(service.run_case("agent:location", user_id="admin", send_name="管理员"))

        self.assertEqual(FakeEvaluationRecord.records[0].evaluation_type, "multi_agent")
        self.assertEqual(FakeEvaluationRecord.records[0].target_agent, "location")

    def test_scoring_failure_records_failed_turn_and_continues(self):
        case = FakeCaseModel(
            case_id="flow:failure",
            name="失败不中断",
            suite_type="flow",
            agent_mode="single",
            target_agent="",
            required_tools=[],
            turns=[{"content": "评分失败"}, {"content": "继续回答"}],
            min_score=0.8,
            enabled=True,
            created_at=datetime.now(),
        )
        FakeCaseModel.records = [case]
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        result = asyncio.run(service.run_case("flow:failure", user_id="admin", send_name="管理员"))

        self.assertEqual(result["total_turns"], 2)
        self.assertEqual(result["failed_turns"], 1)
        self.assertEqual(len(FakeEvaluationRecord.records), 2)
        self.assertEqual(FakeEvaluationRecord.records[0].queue_status, "failed")
        self.assertEqual(FakeEvaluationRecord.records[1].queue_status, "completed")


if __name__ == "__main__":
    unittest.main()
