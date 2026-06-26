"""评估管理 API。"""
from fastapi import APIRouter, Query, Path
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from api.v1.response_controller import json_response
from internal.service.evaluation import RAGEvaluationService
from internal.service.evaluation.conversation_regression_service import ConversationRegressionService
from log import logger

router = APIRouter(prefix="/evaluations", tags=["评估管理"])


class RAGEvaluationConfigRequest(BaseModel):
    ragas_enabled: Optional[bool] = None
    ragas_queue_enabled: Optional[bool] = None
    ragas_sample_rate: Optional[float] = None
    ragas_max_chunks_per_question: Optional[int] = None
    ragas_min_retrieval_score: Optional[float] = None
    evaluation_enabled: Optional[bool] = None
    evaluation_sample_rate: Optional[float] = None


class RunEvaluationCaseRequest(BaseModel):
    user_id: Optional[str] = None
    send_name: Optional[str] = None
    suite_type: Optional[str] = None


class EvaluationCaseRequest(BaseModel):
    case_id: Optional[str] = None
    name: Optional[str] = None
    suite_type: Optional[str] = None
    agent_mode: Optional[str] = None
    target_agent: Optional[str] = None
    required_tools: Optional[List[str]] = None
    blocked_terms: Optional[List[str]] = None
    turns: Optional[List[Dict[str, Any]]] = None
    min_score: Optional[float] = None
    enabled: Optional[bool] = None
    description: Optional[str] = None


@router.get("", summary="获取评估记录")
async def get_evaluations(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: str = Query(default=None, description="搜索关键词"),
    ragas_status: str = Query(default=None, description="评估状态"),
    evaluation_id: str = Query(default=None, description="评估ID"),
    evaluation_type: str = Query(default=None, description="评估类型")
):
    try:
        service = RAGEvaluationService()
        data = await service.get_evaluation_management_list(
            page=page,
            page_size=page_size,
            keyword=keyword,
            ragas_status=ragas_status,
            evaluation_id=evaluation_id,
            evaluation_type=evaluation_type,
        )
        return json_response("查询成功", 0, data)
    except Exception as e:
        logger.error(f"获取评估记录失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/rag", summary="获取 RAG 评估记录")
async def get_rag_evaluations(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: str = Query(default=None, description="搜索关键词"),
    ragas_status: str = Query(default=None, description="评估状态"),
    evaluation_id: str = Query(default=None, description="评估ID")
):
    try:
        service = RAGEvaluationService()
        data = await service.get_rag_evaluation_list(
            page=page,
            page_size=page_size,
            keyword=keyword,
            ragas_status=ragas_status,
            evaluation_id=evaluation_id,
        )
        return json_response("查询成功", 0, data)
    except Exception as e:
        logger.error(f"获取 RAG 评估记录失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/rag/config", summary="获取 RAG 评估配置")
async def get_rag_evaluation_config():
    try:
        service = RAGEvaluationService()
        data = await service.get_config()
        return json_response("查询成功", 0, data)
    except Exception as e:
        logger.error(f"获取 RAG 评估配置失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/cases", summary="获取固定测试集")
async def get_evaluation_cases(
    suite_type: str = Query(default=None, description="测试集类型"),
    enabled: Optional[bool] = Query(default=None, description="是否启用")
):
    try:
        service = ConversationRegressionService()
        data = await service.list_cases(suite_type=suite_type, enabled=enabled)
        return json_response("查询成功", 0, data)
    except Exception as e:
        logger.error(f"获取固定测试集失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.post("/cases", summary="新增固定测试集")
async def create_evaluation_case(req: EvaluationCaseRequest):
    try:
        service = ConversationRegressionService()
        data = await service.create_case(req.model_dump(exclude_none=True))
        return json_response("保存成功", 0, data)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"新增固定测试集失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.post("/cases/run-all", summary="执行固定测试集")
async def run_evaluation_cases(req: RunEvaluationCaseRequest = None):
    try:
        service = ConversationRegressionService()
        user_id = (req.user_id if req else None) or "admin"
        send_name = (req.send_name if req else None) or "管理员"
        suite_type = (req.suite_type if req else None) or None
        data = await service.run_cases(user_id=user_id, send_name=send_name, suite_type=suite_type)
        return json_response("执行完成", 0, data)
    except Exception as e:
        logger.error(f"执行固定测试集失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/cases/{case_id}", summary="获取固定测试集详情")
async def get_evaluation_case(case_id: str = Path(..., description="测试集ID")):
    try:
        service = ConversationRegressionService()
        data = await service.get_case(case_id)
        return json_response("查询成功", 0, data)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"获取固定测试集详情失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.patch("/cases/{case_id}", summary="编辑固定测试集")
async def update_evaluation_case(
    case_id: str = Path(..., description="测试集ID"),
    req: EvaluationCaseRequest = None,
):
    try:
        service = ConversationRegressionService()
        values = req.model_dump(exclude_none=True) if req else {}
        data = await service.update_case(case_id, values)
        return json_response("保存成功", 0, data)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"编辑固定测试集失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.delete("/cases/{case_id}", summary="删除固定测试集")
async def delete_evaluation_case(case_id: str = Path(..., description="测试集ID")):
    try:
        service = ConversationRegressionService()
        await service.delete_case(case_id)
        return json_response("删除成功", 0)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"删除固定测试集失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.post("/cases/{case_id}/run", summary="执行固定测试集")
async def run_evaluation_case(
    case_id: str = Path(..., description="测试集ID"),
    req: RunEvaluationCaseRequest = None,
):
    try:
        service = ConversationRegressionService()
        user_id = (req.user_id if req else None) or "admin"
        send_name = (req.send_name if req else None) or "管理员"
        data = await service.run_case(case_id=case_id, user_id=user_id, send_name=send_name)
        return json_response("执行完成", 0, data)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"执行固定测试集失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/cases/{case_id}/results", summary="获取固定测试集结果")
async def get_evaluation_case_results(case_id: str = Path(..., description="测试集ID")):
    try:
        service = ConversationRegressionService()
        data = await service.get_case_results(case_id)
        return json_response("查询成功", 0, data)
    except Exception as e:
        logger.error(f"获取固定测试集结果失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.patch("/rag/config", summary="更新 RAG 评估配置")
async def update_rag_evaluation_config(req: RAGEvaluationConfigRequest):
    try:
        service = RAGEvaluationService()
        data = await service.save_config(req.model_dump(exclude_none=True))
        return json_response("保存成功", 0, data)
    except Exception as e:
        logger.error(f"更新 RAG 评估配置失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.post("/rag/{evaluation_id}/requeue", summary="重新加入评估队列")
async def requeue_rag_evaluation(evaluation_id: str = Path(..., description="评估记录ID")):
    try:
        from internal.model.evaluation import EvaluationModel

        record = await EvaluationModel.get(evaluation_id)
        if not record:
            return json_response("记录不存在", -2)
        service = RAGEvaluationService()
        success = await service.requeue_record(record)
        return json_response("已加入队列" if success else "加入队列失败", 0 if success else -1)
    except Exception as e:
        logger.error(f"重新加入评估队列失败: {e}", exc_info=True)
        return json_response("系统错误", -1)
