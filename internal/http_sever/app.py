"""
FastAPI 应用工厂
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from .routes import setup_routes
from pkg.middleware.auth import JWTAuthMiddleware
from pkg.middleware.response_logger import ReturnLoggingMiddleware
from log import logger
import os


def create_app() -> FastAPI:
    """
    创建并配置 FastAPI 应用
    
    Returns:
        FastAPI: 配置好的应用实例
    """
    # 创建应用
    app = FastAPI(
        title="RAG Platform API",
        description="无人系统云端 RAG 智能问答平台",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc"
    )
    
    # ==================== CORS 配置 ====================
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # 生产环境应该指定具体域名
        allow_credentials=True,
        allow_methods=["*"],  # 允许所有 HTTP 方法
        allow_headers=["*"],  # 允许所有请求头
    )
    
    # ==================== JWT 认证中间件 ====================
    # 全局应用JWT认证，白名单路径除外
    app.add_middleware(JWTAuthMiddleware)
    logger.info("✓ JWT 认证中间件已全局应用")

    app.add_middleware(ReturnLoggingMiddleware)
    logger.info("✓ 返回日志中间件已全局应用")
    
    # ==================== 注册路由 ====================
    setup_routes(app)
    
    # ==================== 静态文件服务 ====================
    # 挂载上传文件目录（文档、图片等）
    uploads_dir = "uploads"
    os.makedirs(uploads_dir, exist_ok=True)
    
    # 挂载静态文件目录，访问路径: /uploads/*
    app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")
    logger.info(f"✓ 静态文件服务已挂载: /uploads -> {uploads_dir}")
    
    # ==================== 根路由 ====================
    @app.get("/")
    async def root():
        return {
            "name": "RAG Platform API",
            "version": "1.0.0",
            "status": "running",
            "docs": "/docs"
        }
    
    @app.get("/health")
    async def health_check():
        return {"status": "healthy"}
    
    logger.info("✓ FastAPI 应用创建完成")
    
    return app

