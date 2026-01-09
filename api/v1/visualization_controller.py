"""
3D 可视化 API 控制器
"""
from fastapi import APIRouter, Query

from internal.service.visualization import document_3d_service, qa_cache_3d_service
from api.v1.response_controller import json_response
from log import logger

router = APIRouter(prefix="/visualization", tags=["3D可视化"])


@router.get("/documents/3d", summary="获取文档 3D 可视化数据")
async def get_documents_3d(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=200, ge=1, le=500, description="每页数量（最大500）"),
    keyword: str = Query(default=None, description="搜索关键词")
):
    """
    获取文档的 3D 可视化数据
    
    返回每个文档的：
    - uuid: 文档唯一标识
    - filename: 文件名
    - file_type: 文件类型（pdf/docx/txt 等）
    - text_preview: 文本预览（前 100 字符）
    - x, y, z: 3D 坐标（UMAP 降维后）
    - created_at: 创建时间
    """
    try:
        message, ret, data = await document_3d_service.get_document_vectors(
            page=page,
            page_size=page_size,
            keyword=keyword
        )
        
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"获取 3D 可视化数据失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.post("/documents/3d/refresh", summary="刷新 3D 可视化缓存")
async def refresh_3d_cache():
    """
    清空 3D 可视化缓存，下次请求时重新计算
    """
    try:
        document_3d_service.clear_cache()
        return json_response("缓存已清空", 0)
    except Exception as e:
        logger.error(f"刷新缓存失败: {e}", exc_info=True)
        return json_response("刷新失败", -1)


@router.get("/qa-cache/3d", summary="获取 QA 缓存 3D 可视化数据")
async def get_qa_cache_3d(
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=200, ge=1, le=500, description="每页数量"),
    keyword: str = Query(default=None, description="搜索关键词")
):
    """
    获取 QA 缓存的 3D 可视化数据
    """
    try:
        message, ret, data = await qa_cache_3d_service.get_qa_vectors(
            page=page,
            page_size=page_size,
            keyword=keyword
        )
        
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"获取 QA 3D 可视化数据失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.post("/qa-cache/3d/refresh", summary="刷新 QA 缓存 3D 可视化缓存")
async def refresh_qa_cache_3d():
    """清空 QA 3D 可视化缓存"""
    try:
        qa_cache_3d_service.clear_cache()
        return json_response("缓存已清空", 0)
    except Exception as e:
        logger.error(f"刷新缓存失败: {e}", exc_info=True)
        return json_response("刷新失败", -1)
