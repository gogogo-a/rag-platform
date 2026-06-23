import asyncio
import os
import sys

sys.path.append(os.getcwd())

from internal.db.mongodb import db
from internal.db.qdrant import qdrant_client, qa_qdrant_client
from pkg.constants.constants import QDRANT_COLLECTION_NAME, QDRANT_QA_COLLECTION_NAME, VECTOR_DIMENSION
from log import logger


async def setup_mongodb():
    """初始化 MongoDB 集合和索引。"""
    logger.info("正在初始化 MongoDB...")
    await db.connect_db()
    logger.info("MongoDB 初始化完成")


def setup_qdrant():
    """初始化 Qdrant 集合。"""
    logger.info("正在初始化 Qdrant...")
    qdrant_client.ensure_collection(QDRANT_COLLECTION_NAME, VECTOR_DIMENSION)
    qa_qdrant_client.ensure_collection(QDRANT_QA_COLLECTION_NAME, VECTOR_DIMENSION)
    logger.info("Qdrant 初始化完成")


async def main():
    try:
        await setup_mongodb()
        setup_qdrant()
        logger.info("后端数据库初始化完成")
    except Exception as e:
        logger.error(f"初始化失败: {e}")
        sys.exit(1)
    finally:
        await db.close_db()


if __name__ == "__main__":
    asyncio.run(main())
