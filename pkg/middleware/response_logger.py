from typing import Any, Callable, Dict, Iterable, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from log import logger
from pkg.utils.return_logger import get_database_duration_summary, reset_database_duration


SKIP_PATH_PREFIXES = ("/uploads/",)
SKIP_PATHS = {"/docs", "/redoc", "/openapi.json"}
LOGGABLE_CONTENT_TYPES = ("application/json", "text/plain", "text/html")


class ReturnLoggingMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        log_sink: Optional[Callable[[Dict[str, Any]], None]] = None,
        skip_paths: Optional[Iterable[str]] = None,
        skip_path_prefixes: Optional[Iterable[str]] = None,
    ):
        super().__init__(app)
        self.log_sink = log_sink
        self.skip_paths = set(skip_paths or SKIP_PATHS)
        self.skip_path_prefixes = tuple(skip_path_prefixes or SKIP_PATH_PREFIXES)

    async def dispatch(self, request: Request, call_next):
        reset_database_duration()
        response = await call_next(request)
        database_summary = get_database_duration_summary()

        if self._should_skip(request, response):
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        body_text = body.decode(response.charset or "utf-8", errors="replace")
        record = {
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "body": body_text,
            **database_summary,
        }

        if self.log_sink:
            self.log_sink(record)
        else:
            logger.info(
                f"API返回 {record['method']} {record['path']} "
                f"{record['status_code']} "
                f"数据库耗时={record['database_duration_ms']}ms "
                f"数据库次数={record['database_query_count']}: {record['body']}"
            )

        return Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
            background=response.background,
        )

    def _should_skip(self, request: Request, response) -> bool:
        path = request.url.path
        if path in self.skip_paths:
            return True
        if any(path.startswith(prefix) for prefix in self.skip_path_prefixes):
            return True

        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            return True
        return not any(item in content_type for item in LOGGABLE_CONTENT_TYPES)
