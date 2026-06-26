"""Kafka management API."""
from typing import Optional

from fastapi import APIRouter, Query, Request

from api.v1.response_controller import json_response
from internal.service.kafka_management_service import kafka_management_service
from log import logger
from pkg.middleware.auth import get_user_from_request


router = APIRouter(prefix="/kafka", tags=["Kafka可视化"])


def _require_admin(request: Request):
    user = get_user_from_request(request)
    if user.get("is_admin") != 1:
        raise PermissionError("无权访问")
    return user


@router.get("/topics", summary="获取 Kafka 主题概览")
async def get_kafka_topics(request: Request):
    try:
        _require_admin(request)
        return json_response("查询成功", 0, await kafka_management_service.get_topics())
    except PermissionError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"获取 Kafka 主题概览失败: {e}", exc_info=True)
        return json_response("Kafka 暂时无法读取", -1)


@router.get("/messages", summary="获取 Kafka 消息列表")
async def get_kafka_messages(
    request: Request,
    topic: Optional[str] = Query(default=None, description="主题"),
    keyword: Optional[str] = Query(default=None, description="关键词"),
    user_id: Optional[str] = Query(default=None, description="用户ID"),
    session_id: Optional[str] = Query(default=None, description="会话ID"),
    question_id: Optional[str] = Query(default=None, description="问题ID"),
    task_id: Optional[str] = Query(default=None, description="任务ID"),
    expert_key: Optional[str] = Query(default=None, description="专家标识"),
    evaluation_id: Optional[str] = Query(default=None, description="评估ID"),
    document_uuid: Optional[str] = Query(default=None, description="文档ID"),
    status: Optional[str] = Query(default=None, description="状态"),
    start_time: Optional[str] = Query(default=None, description="开始时间"),
    end_time: Optional[str] = Query(default=None, description="结束时间"),
    limit: int = Query(default=200, ge=1, le=500, description="读取数量"),
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
):
    try:
        _require_admin(request)
        data = await kafka_management_service.list_messages(
            topic=topic,
            keyword=keyword,
            user_id=user_id,
            session_id=session_id,
            question_id=question_id,
            task_id=task_id,
            expert_key=expert_key,
            evaluation_id=evaluation_id,
            document_uuid=document_uuid,
            status=status,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            page=page,
            page_size=page_size,
        )
        return json_response("查询成功", 0, data)
    except PermissionError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"获取 Kafka 消息列表失败: {e}", exc_info=True)
        return json_response("Kafka 暂时无法读取", -1)


@router.get("/messages/detail", summary="获取 Kafka 消息详情")
async def get_kafka_message_detail(
    request: Request,
    topic: str = Query(..., description="主题"),
    partition: int = Query(..., ge=0, description="分区"),
    offset: int = Query(..., ge=0, description="偏移量"),
):
    try:
        _require_admin(request)
        data = await kafka_management_service.get_message_detail(topic, partition, offset)
        if not data:
            return json_response("消息不存在", -2)
        return json_response("查询成功", 0, data)
    except PermissionError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"获取 Kafka 消息详情失败: {e}", exc_info=True)
        return json_response("Kafka 暂时无法读取", -1)
