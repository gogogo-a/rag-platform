"""
路由表配置
类似 Gin 的路由注册方式
"""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from api.v1.user_info_controller import router as user_router
from api.v1.document_controller import router as document_router
from api.v1.session_controller import router as session_router
from api.v1.message_controller import router as message_router
from api.v1.log_controller import router as log_router
from api.v1.monitor_controller import router as monitor_router
from api.v1.visualization_controller import router as visualization_router
from api.v1.qa_cache_controller import router as qa_cache_router
from log import logger


def setup_routes(app: FastAPI):
    """
    配置所有路由
    
    Args:
        app: FastAPI 应用实例
    """
    logger.info("正在注册路由...")
    
    # ==================== 静态文件 ====================
    # app.mount("/static/avatars", StaticFiles(directory="static/avatars"), name="avatars")
    # app.mount("/static/files", StaticFiles(directory="static/files"), name="files")
    
    # ==================== 用户相关路由 ====================
    app.include_router(user_router)
    
    # ==================== 文档相关路由 ====================
    app.include_router(document_router)
    
    # ==================== 会话相关路由 ====================
    app.include_router(session_router)
    
    # ==================== 消息相关路由 ====================
    app.include_router(message_router)
    
    # ==================== 日志查询路由 ====================
    app.include_router(log_router)
    
    # ==================== 监控查询路由 ====================
    app.include_router(monitor_router)
    
    # ==================== 3D 可视化路由 ====================
    app.include_router(visualization_router)
    
    # ==================== QA 缓存管理路由 ====================
    app.include_router(qa_cache_router)
    
    logger.info("✓ 路由注册完成")
    
    # 打印所有路由
    logger.info("已注册的路由:")
    for route in app.routes:
        if hasattr(route, 'methods'):
            methods = ','.join(route.methods)
            logger.info(f"  {methods:20} {route.path}")

