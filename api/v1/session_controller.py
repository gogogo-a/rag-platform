"""
会话管理 API 控制器 (RESTful 风格)
"""
from fastapi import APIRouter, Query, Path, Request
from internal.dto.request import UpdateSessionRequest
from internal.service.orm.session_sever import session_service
from api.v1.response_controller import json_response
from pkg.middleware.auth import get_user_from_request
from log import logger

router = APIRouter(prefix="/sessions", tags=["会话管理"])


@router.get("", summary="获取会话列表")
async def get_session_list(
    request: Request,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量")
):
    """
    获取用户的会话列表（用户ID从Token中自动解析）
    
    - **page**: 页码（从1开始，默认1）
    - **page_size**: 每页数量（默认20，最大100）
    
    返回会话列表：
    - total: 总会话数
    - sessions: 会话列表
      - uuid: 会话UUID
      - user_id: 用户ID
      - name: 会话名称
      - last_message: 最后一条消息
      - create_at: 创建时间
      - update_at: 更新时间
    """
    try:
        # 从token中获取用户ID
        current_user = get_user_from_request(request)
        user_id = current_user.get("user_id")
        
        logger.info(f"收到获取会话列表请求: user_id={user_id}, page={page}, page_size={page_size}")
        message, ret, data = await session_service.get_session_list(
            user_id=user_id,
            page=page,
            page_size=page_size
        )
        
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/{session_id}", summary="获取会话详情")
async def get_session_detail(
    session_id: str = Path(..., description="会话UUID")
):
    """
    获取会话详情
    
    - **session_id**: 会话UUID
    
    返回会话的完整信息：
    - uuid: 会话UUID
    - user_id: 用户ID
    - name: 会话名称
    - last_message: 最后一条消息
    - create_at: 创建时间
    - update_at: 更新时间
    """
    try:
        logger.info(f"收到获取会话详情请求: {session_id}")
        message, ret, data = await session_service.get_session_detail(session_id)
        
        if data:
            return json_response(message, ret, data)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"获取会话详情失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.patch("/{session_id}", summary="更新会话信息")
async def update_session(
    session_id: str = Path(..., description="会话UUID"),
    req: UpdateSessionRequest = None
):
    """
    更新会话信息
    
    - **session_id**: 会话UUID
    - **name**: 会话名称（可选）
    - **last_message**: 最后一条消息（可选）
    """
    try:
        # 将路径参数的 session_id 设置到 req 中
        req.uuid = session_id
        logger.info(f"收到更新会话请求: {session_id}")
        message, ret = await session_service.update_session(session_id, req)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"更新会话失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.delete("/{session_id}", summary="删除会话")
async def delete_session(
    request: Request,
    session_id: str = Path(..., description="会话UUID")
):
    """
    删除会话及其所有消息
    
    - **session_id**: 会话UUID
    
    注意：删除会话会同时删除该会话下的所有聊天记录，此操作不可恢复。
    """
    try:
        # 从token中获取用户ID
        current_user = get_user_from_request(request)
        user_id = current_user.get("user_id")
        
        logger.info(f"收到删除会话请求: session_id={session_id}, user_id={user_id}")
        message, ret = await session_service.delete_session(session_id, user_id)
        return json_response(message, ret)
        
    except Exception as e:
        logger.error(f"删除会话失败: {e}", exc_info=True)
        return json_response("系统错误", -1)
