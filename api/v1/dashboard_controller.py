"""Admin dashboard API."""
from fastapi import APIRouter, Request

from api.v1.response_controller import json_response
from internal.service.dashboard_service import dashboard_service
from log import logger
from pkg.middleware.auth import get_user_from_request


router = APIRouter(prefix="/dashboard", tags=["系统总览"])


def _require_admin(request: Request):
    user = get_user_from_request(request)
    if user.get("is_admin") != 1:
        raise PermissionError("无权访问")
    return user


@router.get("/overview", summary="获取系统总览")
async def get_dashboard_overview(request: Request):
    try:
        _require_admin(request)
        return json_response("查询成功", 0, await dashboard_service.get_overview())
    except PermissionError as e:
        return json_response(str(e), -2)
    except Exception as e:
        logger.error(f"获取系统总览失败: {e}", exc_info=True)
        return json_response("系统总览暂时无法读取", -1)
