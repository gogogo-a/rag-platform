"""
无人系统云端 RAG 应用主程序
基于 FastAPI + LangChain + MongoDB + Milvus + Kafka + Redis
使用 Beanie ODM 进行 MongoDB 对象映射
"""
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from internal.db.mongodb import init_mongodb, close_mongodb
from internal.db.milvus import milvus_client  # 直接导入全局单例实例
from internal.db.redis import redis_client  # 直接导入全局单例实例
from internal.document_client.document_processor import document_processor
from internal.http_sever.app import create_app
from internal.monitor import start_resource_monitoring, stop_resource_monitoring
from pkg.agent_tools_mcp import mcp_manager  # 🔥 导入 MCP 管理器
from log import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时初始化所有连接，关闭时清理资源
    """
    logger.info("=" * 80)
    logger.info("🚀 RAG Platform 启动中...")
    logger.info("=" * 80)
    
    try:
        # ==================== 初始化 MongoDB ====================
        logger.info("📦 正在连接 MongoDB...")
        await init_mongodb()
        logger.info("✓ MongoDB 连接成功")
        
        # ==================== 初始化 Milvus ====================
        # 直接使用导入的全局单例实例，无需重新实例化
        logger.info("🔍 正在连接 Milvus...")
        milvus_client.connect()
        logger.info("✓ Milvus 连接成功")
        
        # ==================== 初始化 Redis ====================
        # 直接使用导入的全局单例实例，无需重新实例化
        logger.info("⚡ 正在连接 Redis...")
        redis_client.connect()
        if redis_client.ping():
            logger.info("✓ Redis 连接成功")
        else:
            logger.warning("⚠️  Redis 连接失败")
        
        # ==================== 启动文档处理服务 ====================
        logger.info("📝 正在启动文档处理服务...")
        document_processor.start_processing()
        logger.info("✓ 文档处理服务已启动（Kafka 消费者运行中）")
        
        # ==================== 启动资源监控 ====================
        logger.info("📊 正在启动资源监控...")
        start_resource_monitoring(interval=60)  # 每 60 秒监控一次
        logger.info("✓ 资源监控已启动（CPU、内存、GPU、MongoDB、Milvus）")
        
        # ==================== 启动 MCP 服务 ====================
        logger.info("🔌 正在启动 MCP 工具服务...")
        await mcp_manager.start_all()
        logger.info("✓ MCP 工具服务已启动")
        
        logger.info("=" * 80)
        logger.info("✅ 所有服务启动完成")
        logger.info("=" * 80)
        logger.info("📡 API 服务地址: http://0.0.0.0:8000")
        logger.info("📚 API 文档地址: http://localhost:8000/docs")
        logger.info("📊 性能监控数据: json_monitor/YY_MM_DD_monitor/*.json")
        logger.info("=" * 80)
        
        yield  # 应用运行期间
        
    except Exception as e:
        logger.error(f"❌ 启动失败: {e}", exc_info=True)
        raise
    
    finally:
        # ==================== 清理资源 ====================
        logger.info("=" * 80)
        logger.info("🛑 RAG Platform 关闭中...")
        logger.info("=" * 80)
        
        try:
            await close_mongodb()
            logger.info("✓ MongoDB 连接已关闭")
        except Exception as e:
            logger.error(f"关闭 MongoDB 失败: {e}")
        
        try:
            milvus_client.disconnect()
            logger.info("✓ Milvus 连接已关闭")
        except Exception as e:
            logger.error(f"关闭 Milvus 失败: {e}")
        
        try:
            document_processor.stop()
            logger.info("✓ 文档处理服务已停止")
        except Exception as e:
            logger.error(f"停止文档处理服务失败: {e}")
        
        try:
            stop_resource_monitoring()
            logger.info("✓ 资源监控已停止")
        except Exception as e:
            logger.error(f"停止资源监控失败: {e}")
        
        try:
            await mcp_manager.stop_all()
            logger.info("✓ MCP 工具服务已停止")
        except Exception as e:
            logger.error(f"停止 MCP 服务失败: {e}")
        
        logger.info("=" * 80)
        logger.info("👋 应用已关闭")
        logger.info("=" * 80)


# 创建应用实例
app = create_app()
app.router.lifespan_context = lifespan


if __name__ == "__main__":
    # 启动服务器
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
