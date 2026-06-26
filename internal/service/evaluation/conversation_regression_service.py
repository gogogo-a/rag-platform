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
    "调试",
    "接口地址",
    "接口调用",
    "代码修改",
    "这里" + "用了",
    "新" + "修改",
    "工具名",
]

STALE_DEFAULT_CASE_IDS = {"flow:location_trip", "flow:multi_agent_review"}


DEFAULT_REGRESSION_CASES: List[Dict[str, Any]] = [
    {
        "case_id": "mcp:knowledge_search",
        "name": "知识库检索：RAG 生产化方案",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["knowledge_search"],
        "turns": [
            {"content": "根据知识库里的《企业级 RAG 智能问答平台生产化方案》，说明企业级 RAG 平台上线前最低要求有哪些。"},
            {"content": "继续基于同一份资料，列出固定评测集回归测试应该覆盖哪些指标。"},
            {"content": "沿用前两轮内容，把上下文快照、过程记录、评分结果分别归到验收材料、运行记录、质量结论三类。", "required_tools": ["knowledge_search"]},
            {"content": "现在只看质量结论这一类，说明哪些指标能证明回答没有跑题、没有丢上下文。", "required_tools": ["knowledge_search"]},
            {"content": "再回到运行记录这一类，说明需要保存哪些信息，回答要能给验收人员直接看。", "required_tools": ["knowledge_search"]},
            {"content": "最后把这几轮内容压缩成一份上线前检查清单，不要重新展开解释。"},
        ],
        "min_score": 0.8,
        "description": "验证能否命中真实 RAG 生产化方案文档，并在多轮追问中保持依据一致。",
    },
    {
        "case_id": "mcp:web_search",
        "name": "网页搜索：公开资料核对",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["web_search"],
        "turns": [
            {"content": "搜索北华航天工业学院 2025 年大学生创新创业训练计划相关公开信息，说明能确认到哪些公开要点。"},
            {"content": "继续核对公开信息里是否能看到校级推荐、省级项目、公示时间这些要点。", "required_tools": ["web_search"]},
            {"content": "把搜索结果和知识库里的公示材料做一个简短对照，只说能确认和不能确认的部分。"},
            {"content": "最后输出一段适合放进验收记录的核对结论，保留不能确认的风险点。"},
        ],
        "min_score": 0.8,
        "description": "验证搜索工具能否围绕当前知识库中的真实学校公示材料补充公开信息。",
    },
    {
        "case_id": "mcp:weather_query",
        "name": "天气查询：廊坊出行",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["weather_query"],
        "turns": [
            {"content": "查询廊坊今天的实时天气。"},
            {"content": "继续查询廊坊明天的天气，用来安排去北华航天工业学院的演示行程。", "required_tools": ["weather_query"]},
            {"content": "对比今天和明天，判断更适合携带电脑和材料出行的是哪一天。"},
            {"content": "最后给一条简短提醒，必须引用刚才查到的天气变化。"},
        ],
        "min_score": 0.8,
        "description": "验证天气查询工具和真实本地出行场景。",
    },
    {
        "case_id": "mcp:ip_location",
        "name": "IP 定位：当前城市判断",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["ip_location"],
        "turns": [
            {"content": "根据当前网络位置判断我大概在哪个城市。"},
            {"content": "重新确认一次当前网络位置是否仍然指向同一个城市。", "required_tools": ["ip_location"]},
            {"content": "如果我要去北华航天工业学院，基于刚才的位置判断给一句提醒。"},
            {"content": "最后说明这个位置判断适合做精确路线规划还是只适合作为粗略参考。"},
        ],
        "min_score": 0.75,
        "description": "验证 IP 定位和后续上下文承接。",
    },
    {
        "case_id": "mcp:geocode",
        "name": "地理编码：学校地址",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["geocode"],
        "turns": [
            {"content": "解析“北华航天工业学院”的位置，给出城市和大致位置判断。"},
            {"content": "再解析“廊坊站”的位置，为后续出行做准备。", "required_tools": ["geocode"]},
            {"content": "根据刚才两个地点，说明它们是否属于同一城市以及大致出行关系。"},
            {"content": "如果地址结果不够精确，说明还需要用户补充什么信息。"},
        ],
        "min_score": 0.75,
        "description": "验证地理编码工具在真实学校地点上的表现。",
    },
    {
        "case_id": "mcp:poi_search",
        "name": "周边搜索：学校附近服务",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["poi_search"],
        "turns": [
            {"content": "搜索北华航天工业学院附近适合打印材料或临时学习的地点。"},
            {"content": "再搜索学校附近适合临时沟通或等人的地点。", "required_tools": ["poi_search"]},
            {"content": "把两次结果合并，按打印材料、临时学习、等人沟通三类整理。"},
            {"content": "最后按离学校近、适合学生使用这两个标准给出建议。"},
        ],
        "min_score": 0.8,
        "description": "验证 POI 搜索能否服务真实校园周边场景。",
    },
    {
        "case_id": "mcp:route_planning",
        "name": "路线规划：廊坊站到学校",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["route_planning"],
        "turns": [
            {"content": "规划从廊坊站到北华航天工业学院的出行路线。"},
            {"content": "再规划从北华航天工业学院返回廊坊站的路线，方便演示结束后返程。", "required_tools": ["route_planning"]},
            {"content": "对比去程和返程，说明时间安排上需要预留什么余量。"},
            {"content": "如果我带电脑和材料，推荐更稳妥的出行方式。"},
        ],
        "min_score": 0.8,
        "description": "验证路线规划工具在真实校园出行路线上的表现。",
    },
    {
        "case_id": "mcp:email_sender",
        "name": "邮件发送：无效邮箱保护",
        "suite_type": "mcp",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["email_sender"],
        "turns": [
            {"content": "请发送一封邮件到 not-an-email，主题是“RAG 固定评测集确认”，正文说明：固定测试集已按 MCP、Agent、组合流程拆分。"},
            {"content": "根据刚才结果，告诉我发送是否成功；如果失败，只说明原因和需要修正的信息。"},
            {"content": "我把收件人改成 haogeng@example.com，请先判断信息是否已经足够发送，不要补写无关内容。", "required_tools": ["email_sender"]},
            {"content": "最后总结这次邮件任务的发送状态和还需要人工确认的内容。"},
        ],
        "min_score": 0.8,
        "description": "验证邮件工具会校验邮箱格式，避免真实测试误发邮件。",
    },
    {
        "case_id": "agent:knowledge",
        "name": "知识专家：甲方无人系统需求",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "knowledge",
        "required_tools": ["knowledge_search"],
        "turns": [
            {"content": "请让知识专家根据知识库回答：甲方无人系统项目里，系统架构是 B/S 还是 C/S？文档以什么格式为主？项目是否允许连外网？"},
            {"content": "继续让知识专家补充：甲方对文档分类、切片、标注、数据库扩充和模型微调有哪些要求。", "required_tools": ["knowledge_search"]},
            {"content": "把前两轮内容合成一份甲方需求约束清单，分为环境约束、资料处理、模型能力三类。"},
            {"content": "最后指出这份需求里哪些内容会影响演示准备。"},
        ],
        "min_score": 0.8,
        "description": "验证知识专家能否从真实甲方需求文档中提取约束和功能要求。",
    },
    {
        "case_id": "agent:search",
        "name": "搜索专家：学校公示公开核对",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "search",
        "required_tools": ["web_search"],
        "turns": [
            {"content": "请让搜索专家搜索北华航天工业学院 2025 大学生创新创业训练计划公示相关公开信息，并归纳可确认的公开要点。"},
            {"content": "继续让搜索专家复核是否有同一主题的不同来源信息，重点看公示时间和推荐名单。", "required_tools": ["web_search"]},
            {"content": "最后输出公开核对结论，只保留能确认、不能确认、建议人工复核三部分。"},
        ],
        "min_score": 0.8,
        "description": "验证搜索专家能否围绕真实学校公示材料做外部公开信息核对。",
    },
    {
        "case_id": "agent:location",
        "name": "位置专家：校园出行",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "location",
        "required_tools": ["geocode", "weather_query", "route_planning"],
        "turns": [
            {"content": "请让位置专家处理：我从廊坊站去北华航天工业学院，先确认学校位置，再查廊坊天气，最后给出路线和出行提醒。"},
            {"content": "继续让位置专家补充返程安排，仍然以廊坊站为终点。", "required_tools": ["route_planning"]},
            {"content": "把天气、去程、返程放到同一份出行清单里，突出携带电脑和材料的注意事项。"},
        ],
        "min_score": 0.8,
        "description": "验证位置专家能否组合地理编码、天气和路线规划。",
    },
    {
        "case_id": "agent:email",
        "name": "邮件专家：发送前校验",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "email",
        "required_tools": ["email_sender"],
        "turns": [
            {"content": "请让邮件专家发送到 not-an-email，主题“固定评测集调整”，正文“测试集已改为真实业务问题”。如果邮箱无效，直接说明不能发送。"},
            {"content": "把收件人改成 haogeng@example.com，主题和正文沿用上一轮，请邮件专家判断能否发送。", "required_tools": ["email_sender"]},
            {"content": "最后只总结发送结果、收件人、主题和需要人工确认的事项。"},
        ],
        "min_score": 0.8,
        "description": "验证邮件专家在邮箱无效时不会误报发送成功。",
    },
    {
        "case_id": "agent:supervisor",
        "name": "主助手分派：资料与出行组合",
        "suite_type": "agent",
        "agent_mode": "expert",
        "target_agent": "supervisor",
        "required_tools": ["knowledge_search", "weather_query", "route_planning"],
        "turns": [
            {"content": "请用专家模式完成一个组合任务：先基于知识库总结企业级 RAG 平台上线最低要求，再结合廊坊天气和从廊坊站到北华航天工业学院的路线，给出明天去学校做演示的准备建议。"},
            {"content": "继续让知识专家补充这次演示中最应该证明的评估指标。", "required_tools": ["knowledge_search"]},
            {"content": "继续让位置专家更新出行建议，重点考虑携带电脑和纸质材料。", "required_tools": ["weather_query", "route_planning"]},
            {"content": "把知识专家和位置专家的结果合并成半天演示安排。"},
            {"content": "最后列出现场验收时最可能被追问的 5 个问题，并引用前面已经确认的信息。"},
        ],
        "min_score": 0.8,
        "description": "验证主助手能否分派知识专家和位置专家完成真实组合任务。",
    },
    {
        "case_id": "flow:campus_demo_trip",
        "name": "组合流程：校园演示出行",
        "suite_type": "flow",
        "agent_mode": "expert",
        "target_agent": "",
        "required_tools": ["knowledge_search", "weather_query", "route_planning"],
        "turns": [
            {"content": "我要去北华航天工业学院讲企业级 RAG 平台，请先基于知识库列出这次演示必须覆盖的验收点。"},
            {"content": "把刚才的验收点拆成开场说明、功能演示、质量评估、风险说明四个环节。"},
            {"content": "现在查廊坊今天和明天的天气，判断演示当天携带电脑和纸质材料要注意什么。", "required_tools": ["weather_query"]},
            {"content": "规划廊坊站到北华航天工业学院的去程路线。", "required_tools": ["route_planning"]},
            {"content": "再规划演示结束后从北华航天工业学院回廊坊站的返程路线。", "required_tools": ["route_planning"]},
            {"content": "回到演示内容，继续基于知识库补充固定评测集应该展示哪些结果。", "required_tools": ["knowledge_search"]},
            {"content": "把天气、去程、返程和演示环节串成一个从出站到离校的时间安排。"},
            {"content": "最后把资料准备、出行安排和现场答疑重点合成一份简洁清单，必须引用前面已经确认的天气和路线信息。"},
        ],
        "min_score": 0.8,
        "description": "验证知识检索、天气查询、路线规划和多轮汇总的真实组合能力。",
    },
    {
        "case_id": "flow:long_context_single",
        "name": "长对话：RAG 验收方案",
        "suite_type": "flow",
        "agent_mode": "single",
        "target_agent": "",
        "required_tools": ["knowledge_search"],
        "turns": [
            {"content": "基于知识库里的企业级 RAG 生产化方案，先列出上线前最低要求。"},
            {"content": "继续说明为什么生产环境不能只关注回答是否流畅。"},
            {"content": "回到第一轮的最低要求，把它们按数据、模型、工具、审计四类重新归档。"},
            {"content": "把模型量化评估指标列出来，并解释每个指标看什么。", "required_tools": ["knowledge_search"]},
            {"content": "说明上下文管理要保存哪些 snapshot 内容。"},
            {"content": "说明工具调用链需要保存哪些字段。"},
            {"content": "继续说明多 Agent 的 Supervisor + Worker 分工，并和刚才的工具调用链联系起来。", "required_tools": ["knowledge_search"]},
            {"content": "假设现场问到缓存命中但答案变差，基于前面内容给出验收追问。"},
            {"content": "假设现场问到权限过滤，基于前面内容说明应该检查什么。"},
            {"content": "假设现场问到外部依赖失败，基于前面内容说明系统应该如何降级。"},
            {"content": "把第 4 到第 10 轮的评估、上下文、工具链、多 Agent、风险内容合成验收表。"},
            {"content": "最后汇总成一份可直接用于演示验收的 10 条检查清单，必须保持和前面分类一致。"},
        ],
        "min_score": 0.8,
        "description": "验证普通模式在真实 RAG 文档上的长对话、多轮追问和最终汇总能力。",
    },
    {
        "case_id": "flow:resume_project_interview",
        "name": "组合流程：简历项目面试",
        "suite_type": "flow",
        "agent_mode": "expert",
        "target_agent": "",
        "required_tools": ["knowledge_search"],
        "turns": [
            {"content": "请基于知识库里的耿浩简历，整理他的实习经历和项目经历。"},
            {"content": "继续结合企业级 RAG 平台生产化方案，提炼他讲 RAG 项目时可以强调的技术亮点。", "required_tools": ["knowledge_search"]},
            {"content": "把前两轮内容改成面试官能听懂的项目背景、个人职责、技术难点三段。"},
            {"content": "继续追问：如果面试官问评估体系怎么做，基于前面资料应该怎么回答。", "required_tools": ["knowledge_search"]},
            {"content": "继续追问：如果面试官问多 Agent 和工具调用怎么证明有效，应该怎么回答。"},
            {"content": "把这些回答压缩成 90 秒口述稿。"},
            {"content": "最后输出一版更适合简历项目介绍的短文，不要写开发说明。"},
        ],
        "min_score": 0.8,
        "description": "验证专家模式能否结合简历文档和 RAG 平台文档生成真实面试材料。",
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
        for item in existing:
            if getattr(item, "case_id", "") in STALE_DEFAULT_CASE_IDS:
                deleter = getattr(item, "delete", None)
                if deleter:
                    await deleter()
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
        prior_turns = []
        for index, turn in enumerate(getattr(case, "turns", []) or [], start=1):
            result = await self._run_turn(case, turn, index, session_id, user_id, send_name, prior_turns)
            session_id = result.get("session_id") or session_id
            results.append(result)
            prior_turns.append({
                "question": result.get("question", ""),
                "answer": result.get("answer", ""),
            })

        return {
            "case": self._serialize_case(case),
            "session_id": session_id,
            "total_turns": len(results),
            "completed_turns": sum(1 for item in results if item.get("status") == "completed"),
            "failed_turns": sum(1 for item in results if item.get("status") == "failed"),
            "avg_score": _average([item.get("overall_score", 0.0) for item in results]),
            "items": results,
        }

    async def run_cases(
        self,
        user_id: str,
        send_name: str = "管理员",
        suite_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self.ensure_default_cases()
        records = await self.case_model.find().sort("-created_at").to_list()
        cases = [
            item for item in records
            if bool(getattr(item, "enabled", True))
            and (not suite_type or getattr(item, "suite_type", "") == suite_type)
        ]
        results = []
        for case in cases:
            try:
                results.append(await self.run_case(
                    case_id=getattr(case, "case_id", ""),
                    user_id=user_id,
                    send_name=send_name,
                ))
            except Exception as exc:
                results.append({
                    "case": self._serialize_case(case),
                    "session_id": "",
                    "total_turns": len(getattr(case, "turns", []) or []),
                    "completed_turns": 0,
                    "failed_turns": len(getattr(case, "turns", []) or []),
                    "avg_score": 0.0,
                    "status": "failed",
                    "reason": str(exc) or "执行失败",
                    "items": [],
                })

        failed_cases = sum(1 for item in results if item.get("failed_turns", 0) > 0 or item.get("status") == "failed")
        return {
            "suite_type": suite_type or "",
            "total_cases": len(results),
            "completed_cases": len(results) - failed_cases,
            "failed_cases": failed_cases,
            "total_turns": sum(item.get("total_turns", 0) for item in results),
            "completed_turns": sum(item.get("completed_turns", 0) for item in results),
            "failed_turns": sum(item.get("failed_turns", 0) for item in results),
            "avg_score": _average([item.get("avg_score", 0.0) for item in results]),
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
        records = await self.case_model.find().to_list()
        for record in records:
            if getattr(record, "case_id", "") == case_id:
                return record

        getter = getattr(self.case_model, "get", None)
        if getter:
            try:
                record = await getter(case_id)
                if record:
                    return record
            except Exception:
                return None
        return None

    async def _run_turn(
        self,
        case: Any,
        turn: Dict[str, Any],
        turn_index: int,
        session_id: Optional[str],
        user_id: str,
        send_name: str,
        prior_turns: Optional[Sequence[Dict[str, str]]] = None,
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
                contexts=_build_contexts(case, extra_data, triggered_tools, prior_turns or []),
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


def _build_contexts(
    case: Any,
    extra_data: Dict[str, Any],
    triggered_tools: Sequence[str],
    prior_turns: Sequence[Dict[str, str]],
) -> List[str]:
    contexts = [
        f"测试集：{getattr(case, 'name', '')}",
        f"测试类型：{getattr(case, 'suite_type', '')}",
        f"目标能力：{', '.join(getattr(case, 'required_tools', []) or []) or '无'}",
        f"已覆盖能力：{', '.join(triggered_tools) or '无'}",
        f"过程数量：{len(extra_data.get('agent_processes', []) or [])}",
        f"专家结果数量：{len(extra_data.get('expert_results', []) or [])}",
    ]
    for index, item in enumerate(prior_turns[-6:], start=max(1, len(prior_turns) - 5)):
        question = str(item.get("question", "")).strip()
        answer = str(item.get("answer", "")).strip()
        if question or answer:
            contexts.append(f"前序第 {index} 轮：用户：{question}\n回答：{answer[:800]}")
    return contexts


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
