"""固定对话测试集执行服务。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

from internal.service.evaluation.rag_evaluation_service import (
    LLMQualityEvaluator,
    LLM_SCORE_WEIGHT,
    RULE_SCORE_WEIGHT,
)


DEFAULT_FORBIDDEN_TERMS = [
    "debug",
    "接口",
    "代码",
    "这里" + "用了",
    "新" + "修改",
    "工具名",
]


DEFAULT_REGRESSION_CASES: List[Dict[str, Any]] = [
    {
        "case_id": "mcp:knowledge_search",
        "name": "知识库检索",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["knowledge_search"],
        "turns": [
            {"content": "请根据知识库说明 RAG 平台的主要能力。"},
            {"content": "把刚才的回答整理成三条要点。"},
        ],
        "min_score": 0.8,
        "description": "验证知识库检索和连续追问。",
    },
    {
        "case_id": "mcp:web_search",
        "name": "网页搜索",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["web_search"],
        "turns": [
            {"content": "帮我查一个公开资料并总结重点。"},
            {"content": "再补充它适合什么场景。"},
        ],
        "min_score": 0.8,
        "description": "验证公开信息搜索和归纳。",
    },
    {
        "case_id": "mcp:weather_query",
        "name": "天气查询",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["weather_query"],
        "turns": [
            {"content": "今天上海天气怎么样？"},
            {"content": "根据天气给我一个出行建议。"},
        ],
        "min_score": 0.8,
        "description": "验证天气查询和建议承接。",
    },
    {
        "case_id": "mcp:ip_location",
        "name": "位置识别",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["ip_location"],
        "turns": [
            {"content": "请判断我当前大概所在城市。"},
            {"content": "基于这个城市给出一句提醒。"},
        ],
        "min_score": 0.75,
        "description": "验证位置识别和上下文承接。",
    },
    {
        "case_id": "mcp:geocode",
        "name": "地址解析",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["geocode"],
        "turns": [
            {"content": "帮我解析上海人民广场的大概位置。"},
            {"content": "附近适合怎么安排行程？"},
        ],
        "min_score": 0.75,
        "description": "验证地址解析和追问。",
    },
    {
        "case_id": "mcp:poi_search",
        "name": "周边搜索",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["poi_search"],
        "turns": [
            {"content": "帮我找上海人民广场附近适合开会的咖啡店。"},
            {"content": "按安静程度给我排序。"},
        ],
        "min_score": 0.8,
        "description": "验证周边地点搜索和排序。",
    },
    {
        "case_id": "mcp:route_planning",
        "name": "路线规划",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["route_planning"],
        "turns": [
            {"content": "帮我规划从上海虹桥站到人民广场的路线。"},
            {"content": "如果我带行李，推荐哪种方式？"},
        ],
        "min_score": 0.8,
        "description": "验证路线规划和条件追问。",
    },
    {
        "case_id": "mcp:email_sender",
        "name": "邮件草拟",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["email_sender"],
        "turns": [
            {"content": "帮我写一封项目进度同步邮件，语气正式。"},
            {"content": "再压缩到 150 字以内。"},
        ],
        "min_score": 0.8,
        "description": "验证邮件能力和改写追问。",
    },
    {
        "case_id": "agent:knowledge",
        "name": "知识专家",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "knowledge",
        "required_tools": ["knowledge_search"],
        "turns": [
            {"content": "请让知识专家分析平台文档里的核心能力。"},
            {"content": "继续让它补充使用限制。"},
        ],
        "min_score": 0.8,
        "description": "验证知识专家调用知识能力。",
    },
    {
        "case_id": "agent:search",
        "name": "搜索专家",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "search",
        "required_tools": ["web_search"],
        "turns": [
            {"content": "请让搜索专家帮我查公开资料并归纳重点。"},
        ],
        "min_score": 0.8,
        "description": "验证搜索专家。",
    },
    {
        "case_id": "agent:location",
        "name": "位置专家",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "location",
        "required_tools": ["ip_location", "poi_search", "route_planning"],
        "turns": [
            {"content": "请让位置专家帮我找附近适合开会的地点并给出路线建议。"},
        ],
        "min_score": 0.8,
        "description": "验证位置专家组合位置能力。",
    },
    {
        "case_id": "agent:email",
        "name": "邮件专家",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "email",
        "required_tools": ["email_sender"],
        "turns": [
            {"content": "请让邮件专家帮我写一封给客户的进度同步邮件。"},
        ],
        "min_score": 0.8,
        "description": "验证邮件专家。",
    },
    {
        "case_id": "agent:supervisor",
        "name": "主助手分派",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "supervisor",
        "required_tools": [],
        "turns": [
            {"content": "请综合分析一个需要资料查询、地点建议和邮件输出的问题。"},
        ],
        "min_score": 0.8,
        "description": "验证主助手分派能力。",
    },
    {
        "case_id": "flow:location_trip",
        "name": "位置与路线组合",
        "suite_type": "flow",
        "agent_mode": "expert",
        "target_agent": "",
        "required_tools": ["ip_location", "poi_search", "route_planning"],
        "turns": [
            {"content": "我想找一个附近适合商务沟通的地方。"},
            {"content": "帮我规划过去的路线。"},
            {"content": "最后给我一个简洁行程建议。"},
        ],
        "min_score": 0.8,
        "description": "验证多个位置能力串联。",
    },
    {
        "case_id": "flow:long_context_single",
        "name": "普通模式长对话",
        "suite_type": "flow",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": [],
        "turns": [
            {"content": "我们要准备一个 RAG 平台演示，请先列出目标。"},
            {"content": "把目标拆成准备、演示、答疑三个阶段。"},
            {"content": "准备阶段需要哪些材料？"},
            {"content": "演示阶段按 5 分钟安排。"},
            {"content": "答疑阶段可能会问什么？"},
            {"content": "把风险点单独列出来。"},
            {"content": "给出最终演示流程。"},
            {"content": "总结这次对话的结论。"},
        ],
        "min_score": 0.8,
        "description": "验证普通模式长上下文承接。",
    },
    {
        "case_id": "flow:multi_agent_review",
        "name": "多专家协同",
        "suite_type": "flow",
        "agent_mode": "expert",
        "target_agent": "",
        "required_tools": ["knowledge_search", "web_search"],
        "turns": [
            {"content": "请多个专家协同分析 RAG 平台演示方案。"},
            {"content": "继续补充资料来源和用户关注点。"},
            {"content": "最后输出一个面向用户的简洁方案。"},
        ],
        "min_score": 0.8,
        "description": "验证专家协同和最终汇总。",
    },
]


class ConversationRegressionService:
    """固定对话测试集执行服务。"""

    def __init__(
        self,
        case_model: Any = None,
        evaluation_model: Any = None,
        message_service: Any = None,
        llm_quality_evaluator: Optional[Any] = None,
    ):
        if case_model is None:
            from internal.model.evaluation_case import EvaluationCaseModel
            case_model = EvaluationCaseModel
        if evaluation_model is None:
            from internal.model.evaluation import EvaluationModel
            evaluation_model = EvaluationModel
        if message_service is None:
            from internal.service.orm.message_sever import message_service as default_message_service
            message_service = default_message_service

        self.case_model = case_model
        self.evaluation_model = evaluation_model
        self.message_service = message_service
        self.llm_quality_evaluator = llm_quality_evaluator or LLMQualityEvaluator()

    async def ensure_default_cases(self) -> int:
        existing = await self.case_model.find().to_list()
        existing_ids = {getattr(item, "case_id", "") for item in existing}
        created = 0
        for case_data in DEFAULT_REGRESSION_CASES:
            if case_data["case_id"] in existing_ids:
                continue
            row = self.case_model(
                **{
                    **case_data,
                    "blocked_terms": list(DEFAULT_FORBIDDEN_TERMS),
                    "enabled": True,
                    "created_at": datetime.now(),
                    "updated_at": datetime.now(),
                }
            )
            await row.insert()
            created += 1
        return created

    async def list_cases(self, suite_type: Optional[str] = None, enabled: Optional[bool] = None) -> Dict[str, Any]:
        await self.ensure_default_cases()
        records = await self.case_model.find().sort("-created_at").to_list()
        filtered = list(records)
        if suite_type:
            filtered = [item for item in filtered if getattr(item, "suite_type", "") == suite_type]
        if enabled is not None:
            filtered = [item for item in filtered if bool(getattr(item, "enabled", True)) is enabled]
        return {
            "total": len(filtered),
            "items": [self._serialize_case(item) for item in filtered],
            "suite_counts": {
                item_type: sum(1 for item in records if getattr(item, "suite_type", "") == item_type)
                for item_type in ("mcp", "agent", "flow")
            },
        }

    async def get_case(self, case_id: str) -> Dict[str, Any]:
        await self.ensure_default_cases()
        case = await self._get_case(case_id)
        if not case:
            raise ValueError("测试集不存在")
        return self._serialize_case(case)

    async def create_case(self, values: Dict[str, Any]) -> Dict[str, Any]:
        data = _normalize_case_values(values, require_case_id=True)
        if await self._get_case(data["case_id"]):
            raise ValueError("测试集已存在")
        now = datetime.now()
        row = self.case_model(
            **{
                **data,
                "created_at": now,
                "updated_at": now,
            }
        )
        await row.insert()
        return self._serialize_case(row)

    async def update_case(self, case_id: str, values: Dict[str, Any]) -> Dict[str, Any]:
        case = await self._get_case(case_id)
        if not case:
            raise ValueError("测试集不存在")

        data = _normalize_case_values(values, require_case_id=False)
        new_case_id = data.get("case_id")
        if new_case_id and new_case_id != getattr(case, "case_id", ""):
            existing = await self._get_case(new_case_id)
            if existing:
                raise ValueError("测试集已存在")

        for key, value in data.items():
            setattr(case, key, value)
        case.updated_at = datetime.now()
        await case.save()
        return self._serialize_case(case)

    async def delete_case(self, case_id: str) -> bool:
        case = await self._get_case(case_id)
        if not case:
            raise ValueError("测试集不存在")
        await case.delete()
        return True

    async def run_case(self, case_id: str, user_id: str, send_name: str = "管理员") -> Dict[str, Any]:
        await self.ensure_default_cases()
        case = await self._get_case(case_id)
        if not case:
            raise ValueError("测试集不存在")
        if not getattr(case, "enabled", True):
            raise ValueError("测试集未启用")

        session_id = None
        results = []
        for index, turn in enumerate(getattr(case, "turns", []) or [], start=1):
            result = await self._run_turn(case, turn, index, session_id, user_id, send_name)
            session_id = result.get("session_id") or session_id
            results.append(result)

        return {
            "case": self._serialize_case(case),
            "session_id": session_id,
            "total_turns": len(results),
            "completed_turns": sum(1 for item in results if item.get("status") == "completed"),
            "failed_turns": sum(1 for item in results if item.get("status") == "failed"),
            "avg_score": _average([item.get("overall_score", 0.0) for item in results]),
            "items": results,
        }

    async def get_case_results(self, case_id: str) -> Dict[str, Any]:
        records = await self.evaluation_model.find().sort("-created_at").to_list()
        filtered = [item for item in records if getattr(item, "case_id", "") == case_id]
        return {
            "total": len(filtered),
            "items": [self._serialize_result(item) for item in filtered],
        }

    async def _get_case(self, case_id: str) -> Any:
        getter = getattr(self.case_model, "get", None)
        if getter:
            record = await getter(case_id)
            if record:
                return record
        records = await self.case_model.find().to_list()
        for record in records:
            if getattr(record, "case_id", "") == case_id:
                return record
        return None

    async def _run_turn(
        self,
        case: Any,
        turn: Dict[str, Any],
        turn_index: int,
        session_id: Optional[str],
        user_id: str,
        send_name: str,
    ) -> Dict[str, Any]:
        question = str(turn.get("content") or "").strip()
        answer_parts: List[str] = []
        session_value = session_id
        message_id = ""
        extra_data = {
            "actions": [],
            "observations": [],
            "agent_processes": [],
            "expert_results": [],
            "documents": [],
            "agent_context_usage": None,
        }
        started_at = datetime.now()

        async for event in self.message_service.send_message_stream(
            content=question,
            user_id=user_id,
            send_name=send_name,
            send_avatar="",
            session_id=session_value,
            show_thinking=True,
            agent_mode=getattr(case, "agent_mode", "single") or "single",
            skip_cache=True,
        ):
            event_type = event.get("event", "")
            data = event.get("data", {}) or {}
            if event_type == "session_created":
                session_value = data.get("session_id") or session_value
            elif event_type == "answer_chunk":
                answer_parts.append(str(data.get("content") or ""))
            elif event_type == "ai_message_saved":
                message_id = data.get("uuid") or message_id
            elif event_type == "action":
                extra_data["actions"].append(str(data.get("content") or ""))
            elif event_type == "observation":
                extra_data["observations"].append(str(data.get("content") or ""))
            elif event_type == "agent_process":
                extra_data["agent_processes"].append(data)
            elif event_type == "expert_result":
                extra_data["expert_results"].append(data)
            elif event_type == "documents":
                extra_data["documents"] = data.get("documents", [])
            elif event_type == "agent_context_usage":
                extra_data["agent_context_usage"] = data

        answer = "".join(answer_parts).strip()
        required_tools = _required_tools_for_turn(case, turn, turn_index)
        triggered_tools = _detect_triggered_tools(extra_data, required_tools)
        evaluation_type = _classify_case_evaluation_type(case, extra_data, triggered_tools)
        rule_score = _rule_score(case, answer, triggered_tools, required_tools)
        status = "completed"
        score_reason = ""
        llm_score = 0.0

        try:
            quality = await self.llm_quality_evaluator.evaluate(
                question=question,
                answer=answer,
                contexts=_build_contexts(case, extra_data, triggered_tools),
                evaluation_type=evaluation_type,
            )
            llm_score = _clamp_score(quality.get("score", 0.0))
            score_reason = str(quality.get("reason") or "").strip()
        except Exception:
            status = "failed"
            score_reason = "本轮评分未完成。"

        overall_score = _combine_scores(llm_score, rule_score)
        if status == "completed" and overall_score < float(getattr(case, "min_score", 0.0) or 0.0):
            status = "failed"

        record = self.evaluation_model(
            target_id=message_id or f"{getattr(case, 'case_id', '')}:{turn_index}",
            target_type="regression_case",
            question=question,
            answer=answer,
            session_id=session_value,
            user_id=user_id,
            message_id=message_id,
            tool_name=triggered_tools[0] if triggered_tools else "",
            document_uuid="",
            filename=getattr(case, "name", ""),
            chunk_index=turn_index,
            retrieved_text="",
            vector_score=0.0,
            rerank_score=0.0,
            evaluation_type=evaluation_type,
            llm_score=llm_score,
            rule_score=rule_score,
            score_reason=score_reason,
            score_breakdown={
                "llm_score": llm_score,
                "rule_score": rule_score,
                "weights": {"llm": LLM_SCORE_WEIGHT, "rule": RULE_SCORE_WEIGHT},
                "required_tools": list(getattr(case, "required_tools", []) or []),
                "turn_required_tools": required_tools,
                "triggered_tools": triggered_tools,
            },
            overall_score=overall_score,
            evaluator="llm",
            comment=score_reason,
            dataset_type="regression",
            ragas_status=status,
            ragas_error="" if status == "completed" else score_reason,
            queue_status=status,
            queued_at=started_at,
            started_at=started_at,
            completed_at=datetime.now(),
            retry_count=0,
            case_id=getattr(case, "case_id", ""),
            case_name=getattr(case, "name", ""),
            suite_type=getattr(case, "suite_type", ""),
            turn_index=turn_index,
            agent_mode=getattr(case, "agent_mode", ""),
            target_agent=getattr(case, "target_agent", ""),
            required_tools=required_tools,
            triggered_tools=triggered_tools,
            created_at=datetime.now(),
        )
        await record.insert()
        return self._serialize_result(record)

    def _serialize_case(self, item: Any) -> Dict[str, Any]:
        created_at = getattr(item, "created_at", None)
        updated_at = getattr(item, "updated_at", None)
        return {
            "id": str(getattr(item, "id", "") or ""),
            "case_id": getattr(item, "case_id", "") or "",
            "name": getattr(item, "name", "") or "",
            "suite_type": getattr(item, "suite_type", "") or "",
            "agent_mode": getattr(item, "agent_mode", "single") or "single",
            "target_agent": getattr(item, "target_agent", "") or "",
            "required_tools": list(getattr(item, "required_tools", []) or []),
            "blocked_terms": list(getattr(item, "blocked_terms", []) or []),
            "turns": list(getattr(item, "turns", []) or []),
            "turn_count": len(getattr(item, "turns", []) or []),
            "min_score": float(getattr(item, "min_score", 0.0) or 0.0),
            "enabled": bool(getattr(item, "enabled", True)),
            "description": getattr(item, "description", "") or "",
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else "",
            "updated_at": updated_at.isoformat() if hasattr(updated_at, "isoformat") else "",
        }

    def _serialize_result(self, item: Any) -> Dict[str, Any]:
        created_at = getattr(item, "created_at", None)
        return {
            "id": str(getattr(item, "id", "") or ""),
            "case_id": getattr(item, "case_id", "") or "",
            "case_name": getattr(item, "case_name", "") or "",
            "suite_type": getattr(item, "suite_type", "") or "",
            "turn_index": getattr(item, "turn_index", 0) or 0,
            "agent_mode": getattr(item, "agent_mode", "") or "",
            "target_agent": getattr(item, "target_agent", "") or "",
            "required_tools": list(getattr(item, "required_tools", []) or []),
            "triggered_tools": list(getattr(item, "triggered_tools", []) or []),
            "evaluation_type": getattr(item, "evaluation_type", "") or "",
            "question": getattr(item, "question", "") or "",
            "answer": getattr(item, "answer", "") or "",
            "overall_score": float(getattr(item, "overall_score", 0.0) or 0.0),
            "llm_score": float(getattr(item, "llm_score", 0.0) or 0.0),
            "rule_score": float(getattr(item, "rule_score", 0.0) or 0.0),
            "score_reason": getattr(item, "score_reason", "") or "",
            "queue_status": getattr(item, "queue_status", "") or "",
            "ragas_status": getattr(item, "ragas_status", "") or "",
            "session_id": getattr(item, "session_id", "") or "",
            "message_id": getattr(item, "message_id", "") or "",
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else "",
            "status": getattr(item, "queue_status", "") or getattr(item, "ragas_status", "") or "",
        }


def _classify_case_evaluation_type(case: Any, extra_data: Dict[str, Any], triggered_tools: Sequence[str]) -> str:
    if getattr(case, "agent_mode", "") == "expert" or getattr(case, "suite_type", "") == "agent" or extra_data.get("expert_results"):
        return "multi_agent"
    if triggered_tools or getattr(case, "required_tools", None):
        return "tool_call"
    if len(getattr(case, "turns", []) or []) >= 8:
        return "long_context"
    return "normal_reply"


def _detect_triggered_tools(extra_data: Dict[str, Any], required_tools: Sequence[str]) -> List[str]:
    text = " ".join([
        " ".join(str(item) for item in extra_data.get("actions", [])),
        " ".join(str(item) for item in extra_data.get("observations", [])),
        " ".join(str(item) for item in extra_data.get("agent_processes", [])),
    ])
    triggered = [tool for tool in required_tools if tool and tool in text]
    if not triggered and (extra_data.get("actions") or extra_data.get("observations") or extra_data.get("agent_processes")):
        triggered = list(required_tools)
    return list(dict.fromkeys(triggered))


def _required_tools_for_turn(case: Any, turn: Dict[str, Any], turn_index: int) -> List[str]:
    if "required_tools" in turn:
        return list(turn.get("required_tools") or [])
    if turn_index == 1:
        return list(getattr(case, "required_tools", []) or [])
    return []


def _rule_score(case: Any, answer: str, triggered_tools: Sequence[str], required_tools: Sequence[str]) -> float:
    score = 1.0
    required_tools = list(required_tools or [])
    if required_tools:
        score *= len(set(triggered_tools)) / len(set(required_tools))
    blocked_terms = list(getattr(case, "blocked_terms", []) or DEFAULT_FORBIDDEN_TERMS)
    if any(term and term in answer for term in blocked_terms):
        score *= 0.4
    if not answer:
        score = 0.0
    return round(_clamp_score(score), 4)


def _build_contexts(case: Any, extra_data: Dict[str, Any], triggered_tools: Sequence[str]) -> List[str]:
    return [
        f"测试集：{getattr(case, 'name', '')}",
        f"测试类型：{getattr(case, 'suite_type', '')}",
        f"目标能力：{', '.join(getattr(case, 'required_tools', []) or []) or '无'}",
        f"已覆盖能力：{', '.join(triggered_tools) or '无'}",
        f"过程数量：{len(extra_data.get('agent_processes', []) or [])}",
        f"专家结果数量：{len(extra_data.get('expert_results', []) or [])}",
    ]


def _normalize_case_values(values: Dict[str, Any], require_case_id: bool) -> Dict[str, Any]:
    source = values or {}
    allowed = {
        "case_id",
        "name",
        "suite_type",
        "agent_mode",
        "target_agent",
        "required_tools",
        "blocked_terms",
        "turns",
        "min_score",
        "enabled",
        "description",
    }
    data = {key: source[key] for key in allowed if key in source}
    if require_case_id and not str(data.get("case_id", "")).strip():
        raise ValueError("测试集标识不能为空")
    if "case_id" in data:
        data["case_id"] = str(data.get("case_id") or "").strip()
    if "name" in data:
        data["name"] = str(data.get("name") or "").strip()
    if require_case_id and not data.get("name"):
        raise ValueError("测试集名称不能为空")
    if "suite_type" in data:
        suite_type = str(data.get("suite_type") or "mcp").strip()
        data["suite_type"] = suite_type if suite_type in {"mcp", "agent", "flow"} else "mcp"
    elif require_case_id:
        data["suite_type"] = "mcp"
    if "agent_mode" in data:
        agent_mode = str(data.get("agent_mode") or "single").strip()
        data["agent_mode"] = agent_mode if agent_mode in {"single", "expert"} else "single"
    elif require_case_id:
        data["agent_mode"] = "single"
    if "target_agent" in data:
        data["target_agent"] = str(data.get("target_agent") or "").strip()
    elif require_case_id:
        data["target_agent"] = ""
    if "required_tools" in data:
        data["required_tools"] = _normalize_string_list(data.get("required_tools"))
    elif require_case_id:
        data["required_tools"] = []
    if "blocked_terms" in data:
        data["blocked_terms"] = _normalize_string_list(data.get("blocked_terms"))
    elif require_case_id:
        data["blocked_terms"] = list(DEFAULT_FORBIDDEN_TERMS)
    if "turns" in data:
        data["turns"] = _normalize_turns(data.get("turns"))
    elif require_case_id:
        data["turns"] = []
    if require_case_id and not data["turns"]:
        raise ValueError("测试轮次不能为空")
    if "min_score" in data:
        data["min_score"] = _clamp_score(data.get("min_score", 0.8))
    elif require_case_id:
        data["min_score"] = 0.8
    if "enabled" in data:
        data["enabled"] = bool(data.get("enabled"))
    elif require_case_id:
        data["enabled"] = True
    if "description" in data:
        data["description"] = str(data.get("description") or "").strip()
    elif require_case_id:
        data["description"] = ""
    return data


def _normalize_string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        items = value.split(",")
    elif isinstance(value, list):
        items = value
    else:
        items = []
    return [str(item).strip() for item in items if str(item).strip()]


def _normalize_turns(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    turns = []
    for item in value:
        if isinstance(item, dict):
            content = str(item.get("content") or "").strip()
            required_tools = _normalize_string_list(item.get("required_tools", []))
        else:
            content = str(item or "").strip()
            required_tools = []
        if not content:
            continue
        turn = {"content": content}
        if required_tools:
            turn["required_tools"] = required_tools
        turns.append(turn)
    return turns


def _combine_scores(llm_score: Any, rule_score: Any) -> float:
    return round(_clamp_score(llm_score) * LLM_SCORE_WEIGHT + _clamp_score(rule_score) * RULE_SCORE_WEIGHT, 4)


def _clamp_score(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    return round(min(1.0, max(0.0, number)), 4)


def _average(values: Sequence[Any]) -> float:
    scores = [_clamp_score(value) for value in values]
    return round(sum(scores) / len(scores), 4) if scores else 0.0
