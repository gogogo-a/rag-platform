"""
MongoDB 数据库连接配置
使用 Beanie ODM 和 Motor 异步驱动
单例模式确保全局唯一连接
"""
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from typing import Optional
from pkg.constants.constants import MONGODB_URL, MONGODB_DATABASE

class MongoDB:
    """MongoDB 配置类（单例模式）"""
    
    _instance = None
    _initialized = False
    client: Optional[AsyncIOMotorClient] = None
    
    def __new__(cls):
        """单例模式：确保只有一个实例"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def connect_db(self):
        """连接到 MongoDB 数据库（防止重复连接）"""
        # 如果已经初始化，直接返回
        if self._initialized:
            print("⚠️ MongoDB 已连接，跳过重复初始化")
            return
        
        from internal.model.document import DocumentModel
        from internal.model.message import MessageModel
        from internal.model.user_info import UserInfoModel
        from internal.model.session import SessionModel
        from internal.model.thought_chain import ThoughtChainModel
        
        # MongoDB 连接 URL
        url = MONGODB_URL
        database_name = MONGODB_DATABASE
        
        try:
            # 创建 Motor 客户端（配置连接池）
            self.client = AsyncIOMotorClient(
                url,
                maxPoolSize=20,      # 最大连接数（默认 100）
                minPoolSize=5,       # 最小连接数（默认 0）
                maxIdleTimeMS=60000  # 空闲连接保持时间 60秒（默认永久）
            )
            
            # 测试连接
            await self.client.admin.command('ping')
            print("✓ MongoDB 连接成功！")
            print(f"✓ 连接池配置: maxPoolSize=20, minPoolSize=5")
            
            # 初始化 Beanie，注册所有文档模型
            await init_beanie(
                database=self.client[database_name],
                document_models=[
                    DocumentModel,
                    MessageModel,
                    UserInfoModel,
                    SessionModel,
                    ThoughtChainModel
                ]
            )
            print(f"✓ Beanie ODM 初始化成功！")
            print(f"✓ 数据库: {database_name}")
            print(f"✓ 集合: documents, message, user_info, session, thought_chains")
            
            # 标记为已初始化
            self._initialized = True
            
        except Exception as e:
            print(f"✗ MongoDB 连接失败: {e}")
            raise
    
    async def close_db(self):
        """关闭数据库连接"""
        if self.client:
            self.client.close()
            self._initialized = False
            print("MongoDB 连接已关闭")


# 全局数据库单例实例
db = MongoDB()


# 便捷函数（别名）
async def init_mongodb():
    """初始化MongoDB连接（便捷函数）"""
    await db.connect_db()


async def close_mongodb():
    """关闭MongoDB连接（便捷函数）"""
    await db.close_db()
