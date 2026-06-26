"""评估管理 API。"""
from fastapi import APIRouter, Query, Path
from pydantic import BaseModel
from typing import Optional

from api.v1.response_controller import json_response
from internal.service.evaluation import RAGEvaluationService
from log import logger

router = APIRouter(prefix="/evaluations", tags=["评估管理"])


class RAGEvaluationConfigRequest(BaseModel):
    ragas_enabled: Optional[bool] = None
    ragas_queue_enabled: Optional[bool] = None
    ragas_sample_rate: Optional[float] = None
    ragas_max_chunks_per_question: Optional[int] = None
    ragas_min_retrieval_score: Optional[float] = None


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
