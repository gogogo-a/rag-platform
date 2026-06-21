import asyncio
import os
import sys

# 将项目根目录添加到路径
sys.path.append(os.getcwd())

from internal.db.mongodb import db
from internal.db.milvus import milvus_client
from pkg.constants.constants import MILVUS_COLLECTION_NAME, MILVUS_QA_COLLECTION_NAME
from log import logger

async def setup_mongodb():
    """初始化 MongoDB 集合和索引"""
    logger.info("🚀 正在初始化 MongoDB...")
    await db.connect_db()
    logger.info("✅ MongoDB 初始化完成")

def setup_milvus():
    """初始化 Milvus 集合和索引"""
    logger.info("🚀 正在初始化 Milvus...")
    milvus_client.connect()
    
    # 1. 初始化文档/分块集合
    # 维度 1024 对应 BGE-large-zh-v1.5
    logger.info(f"正在创建文档集合: {MILVUS_COLLECTION_NAME}...")
    milvus_client.create_collection(
        collection_name=MILVUS_COLLECTION_NAME,
        dimension=1024,
        description="企业级 RAG 文档与分块存储",
        metric_type="COSINE",
        index_type="HNSW"
    )
    
    # 2. 初始化问答缓存集合
    logger.info(f"正在创建问答缓存集合: {MILVUS_QA_COLLECTION_NAME}...")
    milvus_client.create_qa_cache_collection(
        dimension=1024,
        metric_type="COSINE"
    )
    
    logger.info("✅ Milvus 初始化完成")

async def main():
    try:
        # 初始化 MongoDB
        await setup_mongodb()
        
        # 初始化 Milvus
        setup_milvus()
        
        logger.info("✨ 所有后端数据库构建完成！")
        
    except Exception as e:
        logger.error(f"❌ 初始化失败: {e}")
        sys.exit(1)
    finally:
        await db.close_db()
        milvus_client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
