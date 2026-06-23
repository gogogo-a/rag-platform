"""
文档处理服务
统一的文档处理器，整合文档加载、分割、Embedding、存储等功能
支持同步和异步处理（Channel/Kafka）
"""
from typing import Dict, Any, List, Optional
from pathlib import Path
from log import logger
from internal.document_client.message_client import message_client
from internal.document_client.config_loader import config
from internal.embedding.embedding_service import embedding_service
from internal.db.qdrant import qdrant_client
from pkg.constants.constants import QDRANT_COLLECTION_NAME, VECTOR_DIMENSION
from internal.document_client.document_extract import extractor_manager
from internal.monitor import record_performance  # 🔥 导入性能监控


class DocumentProcessor:
    """
    统一文档处理器（单例模式）
    
    功能：
    1. 文档加载（PDF, DOCX, TXT）
    2. 文本分割
    3. Embedding 生成
    4. 存储到 Qdrant
    5. 异步任务处理（Channel/Kafka）
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self.embedding_config = config.embedding_config
        self.vector_dimension = VECTOR_DIMENSION
        self.message_client = message_client
        
        # 从配置读取分块参数
        self.chunk_size = self.embedding_config.get('chunk_size', 500)
        self.chunk_overlap = self.embedding_config.get('chunk_overlap', 50)
        
        self._initialized = True
        logger.info(
            f"文档处理器已初始化 "
            f"(分块大小: {self.chunk_size}, 重叠: {self.chunk_overlap})"
        )
    
    # ==================== 同步处理方法 ====================
    
    def process_file(
        self,
        file_path: str,
        document_uuid: str,
        collection_name: Optional[str] = None,
        extra_metadata: Optional[Dict[str, Any]] = None,
        permission: int = 0
    ) -> Dict[str, Any]:
        """
        同步处理单个文件（加载 -> 分割 -> Embedding -> 存储）
        
        Args:
            file_path: 文件路径
            document_uuid: 文档 UUID
            collection_name: 向量集合名称（可选）
            extra_metadata: 额外元数据（可选）
            permission: 文档权限（0=普通用户可见，1=仅管理员可见）
        
        Returns:
            Dict: 处理结果 {success, message, chunks_count, vectors_count, embedding_time, processing_time}
        """
        try:
            import time
            from datetime import datetime
            
            # 记录处理开始时间
            process_start_time = time.time()
            start_datetime = datetime.now()
            # 1. 验证文件
            if not extractor_manager.is_supported(file_path):
                return {
                    "success": False,
                    "message": f"不支持的文件类型: {Path(file_path).suffix}"
                }
            
            file_info = extractor_manager.get_file_info(file_path)
            logger.info(f"开始处理文档: {file_info['name']}, UUID: {document_uuid}")
            
            # 2. 加载文档
            loaded_docs = extractor_manager.load_document(file_path)
            full_content = "\n\n".join([doc["content"] for doc in loaded_docs])
            
            # 3. 分割文本
            chunks = extractor_manager.split_text(
                text=full_content,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                metadata={
                    "document_uuid": document_uuid,
                    "filename": file_info['name'],
                    "source": file_path,
                    "permission": permission,  # 🔥 添加权限到元数据
                    **(extra_metadata or {})
                }
            )
            
            if not chunks:
                return {
                    "success": False,
                    "message": "文档分割后没有生成文本块"
                }
            
            logger.info(f"文档分割完成: {len(chunks)} 个块")
            
            # 4. 批量 Embedding（记录时间）
            embedding_start_time = time.time()
            texts = [chunk["content"] for chunk in chunks]
            embeddings = embedding_service.encode_documents(
                documents=texts,
                batch_size=self.embedding_config.get('batch_size', 32),
                normalize=True
            )
            embedding_duration = time.time() - embedding_start_time
            
            logger.info(f"Embedding 生成完成: {len(embeddings)} 个向量, 耗时: {embedding_duration:.2f}秒")
            
            # 🔥 记录 Embedding 性能监控
            total_text = "\n".join(texts)
            text_length = len(total_text)
            # 估算 token 数量（中英文混合：字符数 * 0.8）
            token_count = int(text_length * 0.8)
            
            record_performance(
                monitor_type="embedding",
                operation=f"文档向量化_{file_info['name']}",
                duration=embedding_duration,
                token_count=token_count,  # 🔥 传入 token_count，系统会自动计算 tokens/s 和 ms/10k tokens
                document_uuid=document_uuid,
                filename=file_info['name'],
                chunks_count=len(chunks),
                vectors_count=len(embeddings),
                text_length=text_length
            )
            
            # 5. 准备向量数据
            texts = []
            metadata_list = []
            
            for i, chunk in enumerate(chunks):
                texts.append(chunk["content"])
                metadata_list.append({
                    "document_uuid": document_uuid,
                    "chunk_index": i,
                    "chunk_count": len(chunks),
                    "filename": file_info['name'],
                    "source": file_path,
                    "permission": permission,  # 🔥 确保每个chunk都有permission
                    **chunk["metadata"]
                })
            
            # 6. 存储到 Qdrant
            if collection_name is None:
                collection_name = QDRANT_COLLECTION_NAME
            
            ids = qdrant_client.upsert_documents(
                collection_name=collection_name,
                embeddings=embeddings,
                texts=texts,
                metadata=metadata_list
            )
            success = ids is not None and len(ids) > 0
            
            # 计算总处理时间
            process_duration = time.time() - process_start_time
            complete_datetime = datetime.now()
            
            if success:
                logger.info(
                    f"✅ 文档处理完成: {file_info['name']}, "
                    f"UUID: {document_uuid}, "
                    f"块数: {len(chunks)}, "
                    f"向量数: {len(embeddings)}, "
                    f"Embedding耗时: {embedding_duration:.2f}秒, "
                    f"总耗时: {process_duration:.2f}秒"
                )
                return {
                    "success": True,
                    "message": "处理成功",
                    "chunks_count": len(chunks),
                    "vectors_count": len(embeddings),
                    "document_uuid": document_uuid,
                    "embedding_time": round(embedding_duration, 2),  # 🔥 embedding时间（秒）
                    "processing_time": round(process_duration, 2),  # 🔥 总处理时间（秒）
                    "start_datetime": start_datetime.isoformat(),  # 🔥 开始时间
                    "complete_datetime": complete_datetime.isoformat()  # 🔥 完成时间
                }
            else:
                return {
                    "success": False,
                    "message": "向量存储失败"
                }
                
        except Exception as e:
            logger.error(f"处理文件失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"处理异常: {str(e)}"
            }
    
    def process_text(
        self,
        text: str,
        document_uuid: str,
        collection_name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        同步处理纯文本（分割 -> Embedding -> 存储）
        
        Args:
            text: 文本内容
            document_uuid: 文档 UUID
            collection_name: 向量集合名称（可选）
            metadata: 元数据（可选）
        
        Returns:
            Dict: 处理结果
        """
        try:
            import time  # 🔥 导入time模块
            
            logger.info(f"开始处理文本，UUID: {document_uuid}")
            
            # 1. 分割文本
            chunks = extractor_manager.split_text(
                text=text,
                chunk_size=self.chunk_size,
                chunk_overlap=self.chunk_overlap,
                metadata={
                    "document_uuid": document_uuid,
                    **(metadata or {})
                }
            )
            
            if not chunks:
                return {
                    "success": False,
                    "message": "文本分割后没有生成文本块"
                }
            
            # 2. 批量 Embedding（记录时间）
            embedding_start_time = time.time()
            texts = [chunk["content"] for chunk in chunks]
            embeddings = embedding_service.encode_documents(
                documents=texts,
                batch_size=self.embedding_config.get('batch_size', 32),
                normalize=True
            )
            embedding_duration = time.time() - embedding_start_time
            
            logger.info(f"Embedding 生成完成: {len(embeddings)} 个向量, 耗时: {embedding_duration:.2f}秒")
            
            # 🔥 记录 Embedding 性能监控
            total_text = "\n".join(texts)
            text_length = len(total_text)
            # 估算 token 数量（中英文混合：字符数 * 0.8）
            token_count = int(text_length * 0.8)
            
            record_performance(
                monitor_type="embedding",
                operation=f"文本向量化_{document_uuid[:8]}",
                duration=embedding_duration,
                token_count=token_count,  # 🔥 传入 token_count，系统会自动计算 tokens/s 和 ms/10k tokens
                document_uuid=document_uuid,
                chunks_count=len(chunks),
                vectors_count=len(embeddings),
                text_length=text_length,
                source="text_upload"  # 标记为文本上传
            )
            
            # 3. 准备向量元数据
            metadata_list = []
            for i, chunk in enumerate(chunks):
                metadata_list.append({
                    "document_uuid": document_uuid,
                    "chunk_index": i,
                    "chunk_count": len(chunks),
                    **chunk["metadata"]
                })
            
            # 4. 存储到 Qdrant
            if collection_name is None:
                collection_name = QDRANT_COLLECTION_NAME
            
            ids = qdrant_client.upsert_documents(
                collection_name=collection_name,
                embeddings=embeddings,
                texts=texts,
                metadata=metadata_list
            )
            success = ids is not None and len(ids) > 0
            
            if success:
                logger.info(f"✅ 文本处理完成, UUID: {document_uuid}, 块数: {len(chunks)}")
                return {
                    "success": True,
                    "message": "处理成功",
                    "chunks_count": len(chunks),
                    "vectors_count": len(embeddings)
                }
            else:
                return {
                    "success": False,
                    "message": "向量存储失败"
                }
                
        except Exception as e:
            logger.error(f"处理文本失败: {e}", exc_info=True)
            return {
                "success": False,
                "message": f"处理异常: {str(e)}"
            }
    
    # ==================== 异步任务方法 ====================
    
    def submit_task(self, task: Dict[str, Any]) -> bool:
        """
        提交文档处理任务到消息队列（异步）
        
        Args:
            task: 任务字典，包含:
                - task_type: 任务类型 (file, text, delete, batch)
                - document_uuid: 文档 UUID
                - file_path/content: 文件路径或文本内容
                - metadata: 元数据（可选）
        
        Returns:
            bool: 是否提交成功
        """
        try:
            # 验证任务
            if 'task_type' not in task:
                logger.error("任务缺少 task_type 字段")
                return False
            
            task_type = task['task_type']
            
            # 根据任务类型选择主题（仅 Kafka 模式需要）
            topic = None
            if message_client.mode == 'kafka':
                topics = config.get('kafka.topics', {})
                topic_map = {
                    'file': topics.get('document_embedding', 'document_embedding'),
                    'text': topics.get('document_embedding', 'document_embedding'),
                    'delete': topics.get('document_delete', 'document_delete'),
                    'batch': topics.get('batch_processing', 'batch_processing')
                }
                topic = topic_map.get(task_type)
            
            # 发送消息
            success = self.message_client.send_message(
                message=task,
                topic=topic
            )
            
            if success:
                logger.info(f"文档任务已提交: {task_type}, UUID={task.get('document_uuid')}")
            else:
                logger.error(f"文档任务提交失败: {task_type}")
            
            return success
            
        except Exception as e:
            logger.error(f"提交任务异常: {e}", exc_info=True)
            return False
    
    def start_processing(self):
        """启动文档处理消费者"""
        logger.info("启动文档处理服务...")
        
        # 启动不同类型的消费者
        if message_client.mode == 'channel':
            # Channel 模式：单个消费者处理所有任务
            self.message_client.start_consumer(
                handler=self._process_task
            )
        else:
            # Kafka 模式：为每个主题启动消费者
            topics = config.get('kafka.topics', {})
            
            # Embedding 任务消费者
            embedding_topic = topics.get('document_embedding', 'document_embedding')
            self.message_client.start_consumer(
                handler=self._process_task,
                topic=embedding_topic
            )
            
            # 删除任务消费者（可选）
            # delete_topic = topics.get('document_delete', 'document_delete')
            # self.message_client.start_consumer(
            #     handler=self._process_delete_task,
            #     topic=delete_topic
            # )
        
        logger.info("文档处理服务已启动")
    
    def _update_document_status_sync(
        self, 
        document_uuid: str, 
        status: int,
        page: Optional[int] = None,
        content: Optional[str] = None,
        extra_data_update: Optional[Dict[str, Any]] = None
    ):
        """
        在同步上下文中更新文档状态（供 Kafka 消费者使用）
        直接调用同步版本，避免事件循环冲突
        
        Args:
            document_uuid: 文档UUID
            status: 状态码
            page: 文档页数（可选）
            content: 文档内容（可选）
            extra_data_update: 额外数据更新（可选）
        """
        from internal.service.orm.document_sever import document_service
        
        # 直接调用同步版本，使用 pymongo 而不是 beanie
        return document_service.update_document_status_sync(
            document_uuid, 
            status, 
            page, 
            content,
            extra_data_update  # 🔥 传递 extra_data_update 参数
        )
    
    def _process_task(self, task: Dict[str, Any]):
        """
        处理文档任务（分发器）
        
        Args:
            task: 任务字典
        """
        task_type = task.get('task_type')
        
        try:
            if task_type == 'file':
                self._process_file_task(task)
            elif task_type == 'text':
                self._process_text_task(task)
            elif task_type == 'delete':
                self._process_delete_task(task)
            elif task_type == 'batch':
                self._process_batch_task(task)
            else:
                logger.warning(f"未知任务类型: {task_type}")
                
        except Exception as e:
            logger.error(f"处理任务失败: {task_type}, 错误: {e}", exc_info=True)
    
    def _process_file_task(self, task: Dict[str, Any]):
        """处理文件任务"""
        file_path = task.get('file_path')
        document_uuid = task.get('document_uuid')
        collection_name = task.get('collection_name')
        metadata = task.get('metadata', {})
        permission = task.get('permission', 0)  # 🔥 获取权限信息
        
        if not file_path or not document_uuid:
            logger.error("文件任务缺少必要字段: file_path, document_uuid")
            # 更新状态为处理失败
            try:
                self._update_document_status_sync(document_uuid, 3)
            except Exception as e:
                logger.error(f"更新文档状态失败: {e}")
            return
        
        result = self.process_file(
            file_path=file_path,
            document_uuid=document_uuid,
            collection_name=collection_name,
            extra_metadata=metadata,
            permission=permission  # 🔥 传递权限信息
        )
        
        # 根据处理结果更新文档状态
        try:
            if result['success']:
                # 处理成功：status=2（处理完成）
                chunks_count = result.get('chunks_count', 0)
                
                # 🔥 准备extra_data更新（记录处理时间）
                extra_data_update = {
                    "embedding_time_seconds": result.get('embedding_time'),
                    "processing_time_seconds": result.get('processing_time'),
                    "processing_start_time": result.get('start_datetime'),
                    "processing_complete_time": result.get('complete_datetime'),
                    "vectors_count": result.get('vectors_count'),
                    "chunks_count": chunks_count
                }
                
                self._update_document_status_sync(
                    document_uuid, 
                    status=2,
                    page=chunks_count,  # 将 chunks_count 存储到 page 字段
                    extra_data_update=extra_data_update  # 🔥 更新extra_data
                )
                logger.info(f"✅ 文档处理完成，状态已更新: {document_uuid}")
            else:
                # 处理失败：status=3（处理失败）
                self._update_document_status_sync(document_uuid, 3)
                logger.error(f"❌ 文档处理失败: {result['message']}, 状态已更新: {document_uuid}")
        except Exception as e:
            logger.error(f"更新文档状态时发生异常: {e}", exc_info=True)
    
    def _process_text_task(self, task: Dict[str, Any]):
        """处理文本任务"""
        content = task.get('content')
        document_uuid = task.get('document_uuid')
        collection_name = task.get('collection_name')
        metadata = task.get('metadata', {})
        
        if not content or not document_uuid:
            logger.error("文本任务缺少必要字段: content, document_uuid")
            return
        
        result = self.process_text(
            text=content,
            document_uuid=document_uuid,
            collection_name=collection_name,
            metadata=metadata
        )
        
        if not result['success']:
            logger.error(f"文本处理失败: {result['message']}")
    
    def _process_delete_task(self, task: Dict[str, Any]):
        """
        处理删除任务
        
        Args:
            task: 任务字典，包含 document_id
        """
        document_id = task.get('document_id')
        
        if not document_id:
            logger.error("删除任务缺少 document_id")
            return
        
        logger.info(f"删除文档: {document_id}")
        
        try:
            qdrant_client.delete_by_document_uuid(document_id, collection_name=QDRANT_COLLECTION_NAME)
            logger.info(f"文档向量已删除: {document_id}")
                
        except Exception as e:
            logger.error(f"删除任务异常: {document_id}, 错误: {e}", exc_info=True)
    
    def _process_batch_task(self, task: Dict[str, Any]):
        """
        处理批量任务
        
        Args:
            task: 任务字典，包含 tasks 列表
        """
        tasks = task.get('tasks', [])
        
        if not tasks:
            logger.error("批量任务缺少 tasks")
            return
        
        logger.info(f"处理批量任务，任务数: {len(tasks)}")
        
        # 批量处理
        for sub_task in tasks:
            self._process_task(sub_task)
    
    def stop(self):
        """停止文档处理服务"""
        logger.info("正在停止文档处理服务...")
        self.message_client.stop()
        logger.info("文档处理服务已停止")


# 创建全局实例
document_processor = DocumentProcessor()


if __name__ == "__main__":
    # 测试代码
    print("=" * 80)
    print("文档处理服务测试")
    print("=" * 80)
    
    # 提交测试任务
    test_task = {
        "task_type": "embedding",
        "document_id": "test_doc_001",
        "content": "这是一个测试文档，用于验证 Embedding 和向量存储功能",
        "metadata": {
            "title": "测试文档",
            "author": "白总"
        }
    }
    
    success = document_processor.submit_task(test_task)
    print(f"\n任务提交结果: {success}")
    
    # 获取统计信息
    stats = message_client.get_stats()
    print(f"\n统计信息: {stats}")

