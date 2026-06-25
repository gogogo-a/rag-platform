"""Agent management API."""
from typing import List, Optional

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel

from api.v1.response_controller import json_response
from internal.service.orm.agent_config_service import agent_config_service
from pkg.middleware.auth import get_user_from_request
from log import logger


router = APIRouter(prefix="/agents", tags=["Agent管理"])


class AgentSaveRequest(BaseModel):
    agent_key: Optional[str] = None
    agent_name: Optional[str] = None
    description: Optional[str] = None
    mcp_tools: Optional[List[str]] = None
    prompt_key: Optional[str] = None
    enabled: Optional[bool] = None
    sort_order: Optional[int] = None


class AgentEnabledRequest(BaseModel):
    enabled: bool


def _require_admin(request: Request):
    user = get_user_from_request(request)
    if user.get("is_admin") != 1:
        raise PermissionError("无权访问")
    return user


@router.get("", summary="获取 Agent 列表")
async def list_agents(
    request: Request,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(default=None, description="搜索关键词"),
    enabled: Optional[bool] = Query(default=None, description="启用状态"),
):
    try:
        _require_admin(request)
        data = await agent_config_service.list_agents(
            page=page,
            page_size=page_size,
            keyword=keyword,
            enabled=enabled,
        )
        return json_response("查询成功", 0, data)
    except PermissionError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"获取 Agent 列表失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/options", summary="获取 Agent 可选项")
async def get_agent_options(request: Request):
    try:
        _require_admin(request)
        return json_response("查询成功", 0, await agent_config_service.get_options())
    except PermissionError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"获取 Agent 可选项失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.post("", summary="创建 Agent")
async def create_agent(request: Request, req: AgentSaveRequest):
    try:
        _require_admin(request)
        data = await agent_config_service.create_agent(req.model_dump(exclude_none=True))
        return json_response("保存成功", 0, data)
    except PermissionError as e:
        return json_response(str(e), -2)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"创建 Agent 失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.patch("/{agent_uuid}", summary="更新 Agent")
async def update_agent(
    request: Request,
    req: AgentSaveRequest,
    agent_uuid: str = Path(..., description="Agent ID"),
):
    try:
        _require_admin(request)
        data = await agent_config_service.update_agent(agent_uuid, req.model_dump(exclude_none=True))
        return json_response("保存成功", 0, data)
    except PermissionError as e:
        return json_response(str(e), -2)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"更新 Agent 失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.patch("/{agent_uuid}/enable", summary="设置 Agent 状态")
async def set_agent_enabled(
    request: Request,
    req: AgentEnabledRequest,
    agent_uuid: str = Path(..., description="Agent ID"),
):
    try:
        _require_admin(request)
        data = await agent_config_service.set_enabled(agent_uuid, req.enabled)
        return json_response("保存成功", 0, data)
    except PermissionError as e:
        return json_response(str(e), -2)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"设置 Agent 状态失败: {e}", exc_info=True)
        return json_response("系统错误", -1)
