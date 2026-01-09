"""
QA 缓存管理 API 控制器
"""
from fastapi import APIRouter, Query, Path

from internal.service.orm.qa_cache_service import qa_cache_service
from api.v1.response_controller import json_response
from log import logger

router = APIRouter(prefix="/qa-cache", tags=["QA缓存管理"])


@router.get("", summary="获取 QA 缓存列表")
async def get_cache_list(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: str = Query(default=None, description="搜索关键词")
):
    """
    获取 QA 缓存列表（分页 + 搜索）
    
    返回已缓存到 Milvus 的问答对
    """
    try:
        message, ret, data = await qa_cache_service.get_cache_list(
            page=page,
            page_size=page_size,
            keyword=keyword
        )
        
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"获取 QA 缓存列表失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/{cache_id}", summary="获取 QA 缓存详情")
async def get_cache_detail(
    cache_id: str = Path(..., description="缓存ID（思维链UUID）")
):
    """
    获取 QA 缓存详情
    
    包含完整的问题、答案、思维链、引用文档等
    """
    try:
        message, ret, data = await qa_cache_service.get_cache_detail(cache_id)
        
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"获取 QA 缓存详情失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.delete("/{cache_id}", summary="删除 QA 缓存")
async def delete_cache(
    cache_id: str = Path(..., description="缓存ID（思维链UUID）")
):
    """
    删除 QA 缓存
    
    同时从 MongoDB 和 Milvus 中删除
    """
    try:
        message, ret = await qa_cache_service.delete_cache(cache_id)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"删除 QA 缓存失败: {e}", exc_info=True)
        return json_response("系统错误", -1)
