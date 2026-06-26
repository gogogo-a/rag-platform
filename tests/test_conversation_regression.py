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
        self.save = AsyncMock()
        self.delete = AsyncMock(side_effect=self._delete)

    async def _insert(self):
        FakeCaseModel.records.append(self)
        FakeCaseModel.created.append(self)

    async def _delete(self):
        FakeCaseModel.records = [item for item in FakeCaseModel.records if item is not self]

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


class RaisingObjectIdCaseModel(FakeCaseModel):
    @classmethod
    async def get(cls, case_id):
        raise ValueError("Id must be of type PydanticObjectId")


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
        self.assertIn("flow:campus_demo_trip", case_ids)
        self.assertIn("flow:long_context_single", case_ids)
        self.assertNotIn("flow:location_trip", case_ids)
        self.assertNotIn("flow:multi_agent_review", case_ids)

    def test_default_cases_are_grounded_in_current_database_content(self):
        combined_text = "\n".join(
            turn["content"]
            for case in DEFAULT_REGRESSION_CASES
            for turn in case.get("turns", [])
        )

        self.assertIn("企业级 RAG 智能问答平台生产化方案", combined_text)
        self.assertIn("甲方无人系统", combined_text)
        self.assertIn("北华航天工业学院", combined_text)
        self.assertIn("耿浩简历", combined_text)
        self.assertNotIn("帮我查一个公开资料", combined_text)
        self.assertNotIn("上海人民广场", combined_text)

    def test_flow_cases_use_long_continuous_context_and_repeated_tool_checks(self):
        cases = {item["case_id"]: item for item in DEFAULT_REGRESSION_CASES}

        self.assertGreaterEqual(len(cases["flow:long_context_single"]["turns"]), 10)
        self.assertGreaterEqual(len(cases["flow:campus_demo_trip"]["turns"]), 8)
        self.assertGreaterEqual(len(cases["agent:supervisor"]["turns"]), 5)
        campus_tool_turns = [
            turn for turn in cases["flow:campus_demo_trip"]["turns"]
            if turn.get("required_tools")
        ]
        self.assertGreaterEqual(len(campus_tool_turns), 4)
        self.assertIn("必须引用前面已经确认", cases["flow:campus_demo_trip"]["turns"][-1]["content"])
        self.assertIn("保持和前面分类一致", cases["flow:long_context_single"]["turns"][-1]["content"])

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

    def test_seed_default_cases_removes_stale_builtin_cases(self):
        stale = FakeCaseModel(
            case_id="flow:multi_agent_review",
            name="旧测试集",
            suite_type="flow",
            agent_mode="expert",
            target_agent="",
            required_tools=[],
            turns=[{"content": "旧问题"}],
            min_score=0.8,
            enabled=True,
            created_at=datetime.now(),
        )
        FakeCaseModel.records = [stale]
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        asyncio.run(service.ensure_default_cases())

        self.assertNotIn("flow:multi_agent_review", {case.case_id for case in FakeCaseModel.records})

    def test_get_case_uses_case_id_before_object_id_lookup(self):
        case = RaisingObjectIdCaseModel(**DEFAULT_REGRESSION_CASES[0])
        RaisingObjectIdCaseModel.records = [case]
        service = ConversationRegressionService(
            case_model=RaisingObjectIdCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        data = asyncio.run(service.get_case("mcp:knowledge_search"))

        self.assertEqual(data["case_id"], "mcp:knowledge_search")

    def test_create_case_adds_custom_case(self):
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        data = asyncio.run(service.create_case({
            "case_id": "mcp:stock_query",
            "name": "股票查询",
            "suite_type": "mcp",
            "agent_mode": "single",
            "required_tools": ["stock_query"],
            "turns": [{"content": "帮我查询苹果公司的股价情况。"}],
            "min_score": 0.82,
            "enabled": True,
            "description": "验证股票查询能力",
        }))

        self.assertEqual(data["case_id"], "mcp:stock_query")
        self.assertEqual(data["required_tools"], ["stock_query"])
        self.assertEqual(data["turn_count"], 1)
        self.assertEqual(len(FakeCaseModel.records), 1)

    def test_create_case_rejects_duplicate_case_id(self):
        FakeCaseModel.records = [FakeCaseModel(**DEFAULT_REGRESSION_CASES[0])]
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        with self.assertRaises(ValueError):
            asyncio.run(service.create_case(DEFAULT_REGRESSION_CASES[0]))

    def test_update_case_changes_editable_fields(self):
        case = FakeCaseModel(**DEFAULT_REGRESSION_CASES[0])
        FakeCaseModel.records = [case]
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        data = asyncio.run(service.update_case("mcp:knowledge_search", {
            "name": "知识检索回归",
            "min_score": 0.9,
            "turns": [{"content": "新的问题"}],
        }))

        self.assertEqual(data["name"], "知识检索回归")
        self.assertEqual(data["min_score"], 0.9)
        self.assertEqual(data["turn_count"], 1)
        case.save.assert_awaited_once()

    def test_delete_case_removes_case(self):
        case = FakeCaseModel(**DEFAULT_REGRESSION_CASES[0])
        FakeCaseModel.records = [case]
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        result = asyncio.run(service.delete_case("mcp:knowledge_search"))

        self.assertTrue(result)
        self.assertEqual(FakeCaseModel.records, [])
        case.delete.assert_awaited_once()

    def test_get_case_returns_serialized_detail(self):
        FakeCaseModel.records = [FakeCaseModel(**DEFAULT_REGRESSION_CASES[0])]
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        data = asyncio.run(service.get_case("mcp:knowledge_search"))

        self.assertEqual(data["case_id"], "mcp:knowledge_search")
        self.assertGreaterEqual(data["turn_count"], 1)

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

    def test_run_cases_executes_enabled_cases_in_current_suite(self):
        FakeCaseModel.records = [
            FakeCaseModel(
                case_id="mcp:weather_query",
                name="天气查询",
                suite_type="custom",
                agent_mode="single",
                target_agent="",
                required_tools=["weather_query"],
                turns=[{"content": "今天廊坊天气如何？"}],
                min_score=0.8,
                enabled=True,
                created_at=datetime(2026, 1, 1, 10, 0, 0),
            ),
            FakeCaseModel(
                case_id="agent:location",
                name="位置专家",
                suite_type="agent",
                agent_mode="expert",
                target_agent="location",
                required_tools=["route_planning"],
                turns=[{"content": "规划去学校的路线"}],
                min_score=0.8,
                enabled=True,
                created_at=datetime(2026, 1, 1, 11, 0, 0),
            ),
            FakeCaseModel(
                case_id="mcp:disabled",
                name="停用测试",
                suite_type="custom",
                agent_mode="single",
                target_agent="",
                required_tools=[],
                turns=[{"content": "不应执行"}],
                min_score=0.8,
                enabled=False,
                created_at=datetime(2026, 1, 1, 12, 0, 0),
            ),
        ]
        message_service = FakeMessageService()
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=message_service,
            llm_quality_evaluator=FakeQualityEvaluator(),
        )

        result = asyncio.run(service.run_cases(user_id="admin", send_name="管理员", suite_type="custom"))

        self.assertEqual(result["total_cases"], 1)
        self.assertEqual(result["completed_cases"], 1)
        self.assertEqual(result["failed_cases"], 0)
        self.assertEqual(result["total_turns"], 1)
        self.assertEqual(result["items"][0]["case"]["case_id"], "mcp:weather_query")
        self.assertEqual(len(message_service.calls), 1)

    def test_llm_scoring_receives_previous_turn_context(self):
        class CapturingQualityEvaluator(FakeQualityEvaluator):
            def __init__(self):
                self.contexts = []

            async def evaluate(self, question, answer, contexts, evaluation_type="normal_reply"):
                self.contexts.append(list(contexts))
                return await super().evaluate(question, answer, contexts, evaluation_type)

        case = FakeCaseModel(
            case_id="flow:context_scoring",
            name="上下文评分",
            suite_type="flow",
            agent_mode="single",
            target_agent="",
            required_tools=[],
            turns=[{"content": "第一轮结论是 A"}, {"content": "基于上一轮继续总结"}],
            min_score=0.8,
            enabled=True,
            created_at=datetime.now(),
        )
        FakeCaseModel.records = [case]
        evaluator = CapturingQualityEvaluator()
        service = ConversationRegressionService(
            case_model=FakeCaseModel,
            evaluation_model=FakeEvaluationRecord,
            message_service=FakeMessageService(),
            llm_quality_evaluator=evaluator,
        )

        asyncio.run(service.run_case("flow:context_scoring", user_id="admin", send_name="管理员"))

        self.assertFalse(any("前序第" in item for item in evaluator.contexts[0]))
        self.assertTrue(any("前序第 1 轮" in item for item in evaluator.contexts[1]))
        self.assertTrue(any("第一轮结论是 A" in item for item in evaluator.contexts[1]))

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
