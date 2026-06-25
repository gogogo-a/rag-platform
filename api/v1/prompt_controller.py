"""Prompt management API."""
from typing import Optional

from fastapi import APIRouter, Path, Query, Request
from pydantic import BaseModel

from api.v1.response_controller import json_response
from internal.service.orm.prompt_service import prompt_service
from pkg.middleware.auth import get_user_from_request
from log import logger


router = APIRouter(prefix="/prompts", tags=["Prompt管理"])


class PromptUpdateRequest(BaseModel):
    content: str
    save_copy: bool = False


def _require_admin(request: Request):
    user = get_user_from_request(request)
    if user.get("is_admin") != 1:
        raise PermissionError("无权访问")
    return user


@router.get("", summary="获取 Prompt 列表")
async def list_prompts(
    request: Request,
    page: int = Query(default=1, ge=1, description="页码"),
    page_size: int = Query(default=20, ge=1, le=100, description="每页数量"),
    keyword: Optional[str] = Query(default=None, description="搜索关键词"),
    category: Optional[str] = Query(default=None, description="类别"),
    agent_key: Optional[str] = Query(default=None, description="Agent标识"),
):
    try:
        _require_admin(request)
        data = await prompt_service.list_prompts(
            page=page,
            page_size=page_size,
            keyword=keyword,
            category=category,
            agent_key=agent_key,
        )
        return json_response("查询成功", 0, data)
    except PermissionError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"获取 Prompt 列表失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.get("/options", summary="获取 Prompt 可选项")
async def get_prompt_options(request: Request):
    try:
        _require_admin(request)
        return json_response("查询成功", 0, prompt_service.get_options())
    except PermissionError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"获取 Prompt 可选项失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.patch("/{prompt_uuid}", summary="更新 Prompt")
async def update_prompt(
    request: Request,
    req: PromptUpdateRequest,
    prompt_uuid: str = Path(..., description="Prompt ID"),
):
    try:
        _require_admin(request)
        data = await prompt_service.update_prompt(
            prompt_uuid=prompt_uuid,
            content=req.content,
            save_copy=req.save_copy,
        )
        return json_response("保存成功", 0, data)
    except PermissionError as e:
        return json_response(str(e), -2)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"保存 Prompt 失败: {e}", exc_info=True)
        return json_response("系统错误", -1)


@router.patch("/{prompt_uuid}/activate", summary="启用 Prompt")
async def activate_prompt(request: Request, prompt_uuid: str = Path(..., description="Prompt ID")):
    try:
        _require_admin(request)
        data = await prompt_service.activate_prompt(prompt_uuid)
        return json_response("启用成功", 0, data)
    except PermissionError as e:
        return json_response(str(e), -2)
    except ValueError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"启用 Prompt 失败: {e}", exc_info=True)
        return json_response("系统错误", -1)
