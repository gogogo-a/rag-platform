"""
Milvus 向量数据库连接
使用单例模式管理连接
"""
from pymilvus import connections, utility, Collection, CollectionSchema, FieldSchema, DataType
from typing import Optional, List, Dict, Any

from log import logger
from pkg.constants.constants import (
    MILVUS_HOST,
    MILVUS_PORT,
    MILVUS_USER,
    MILVUS_PASSWORD,
    MILVUS_DB_NAME,
    MILVUS_QA_COLLECTION_NAME
)


class Milvus:
    """Milvus 向量数据库单例类"""
    
    _instance: Optional['Milvus'] = None
    _initialized: bool = False
    _connection_alias: str = "default"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化（只执行一次）"""
        if not Milvus._initialized:
            self.host = MILVUS_HOST
            self.port = MILVUS_PORT
            self.user = MILVUS_USER
            self.password = MILVUS_PASSWORD
            self.db_name = MILVUS_DB_NAME
            self.collections: Dict[str, Collection] = {}
            Milvus._initialized = True
            logger.info("Milvus 实例已初始化")
    
    def connect(self):
        """
        连接到 Milvus 数据库
        
        Returns:
            bool: 连接是否成功
        """
        try:
            # 检查是否已连接
            if connections.has_connection(self._connection_alias):
                logger.info(f"Milvus 已连接到 {self.host}:{self.port}")
                return True
            
            # 直接连接（Milvus 2.x 会使用默认数据库）
            connections.connect(
                alias=self._connection_alias,
                host=self.host,
                port=str(self.port),
                user=self.user,
                password=self.password
            )
            
            logger.info(f"✓ 成功连接到 Milvus: {self.host}:{self.port}")
            
            # 验证连接
            version = utility.get_server_version()
            logger.info(f"✓ Milvus 版本: {version}")
            
            return True
            
        except Exception as e:
            logger.error(f"✗ 连接 Milvus 失败: {e}")
            raise Exception(f"Milvus 连接失败: {e}")
    
    def disconnect(self):
        """断开 Milvus 连接"""
        try:
            if connections.has_connection(self._connection_alias):
                connections.disconnect(self._connection_alias)
                logger.info("✓ Milvus 连接已断开")
        except Exception as e:
            logger.error(f"✗ 断开 Milvus 连接失败: {e}")
    
    def create_collection(
        self,
        collection_name: str,
        dimension: int = 1536,
        description: str = "",
        index_type: str = "IVF_FLAT",
        metric_type: str = "L2",
        auto_id: bool = True,
        index_params: Optional[Dict[str, Any]] = None
    ) -> Collection:
        """
        创建集合（Collection）
        
        Args:
            collection_name: 集合名称
            dimension: 向量维度（默认 1536，OpenAI embedding 维度）
            description: 集合描述
            index_type: 索引类型
            metric_type: 相似度度量类型（L2/IP/COSINE）
            auto_id: 是否自动生成 ID
            
        Returns:
            Collection: 创建的集合对象
        """
        try:
            # 检查集合是否已存在
            if utility.has_collection(collection_name):
                logger.info(f"集合 '{collection_name}' 已存在")
                collection = Collection(collection_name)
                self.collections[collection_name] = collection
                return collection
            
            # 定义字段
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=auto_id),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
                FieldSchema(name="metadata", dtype=DataType.JSON)
            ]
            
            # 创建 schema
            schema = CollectionSchema(
                fields=fields,
                description=description or f"Collection for {collection_name}"
            )
            
            # 创建集合
            collection = Collection(
                name=collection_name,
                schema=schema,
                using=self._connection_alias
            )
            
            # 创建索引
            if index_params is None:
                # 默认参数（根据索引类型选择）
                if index_type == "IVF_FLAT" or index_type == "IVF_SQ8":
                    params = {"nlist": 1024}
                elif index_type == "HNSW":
                    params = {"M": 16, "efConstruction": 256}
                elif index_type == "IVF_PQ":
                    params = {"nlist": 1024, "m": 8, "nbits": 8}
                else:
                    params = {"nlist": 1024}
            else:
                params = index_params
            
            final_index_params = {
                "metric_type": metric_type,
                "index_type": index_type,
                "params": params
            }
            
            collection.create_index(
                field_name="embedding",
                index_params=final_index_params
            )
            
            logger.info(f"✓ 集合 '{collection_name}' 创建成功")
            logger.info(f"  - 维度: {dimension}")
            logger.info(f"  - 索引类型: {index_type}")
            logger.info(f"  - 度量类型: {metric_type}")
            
            self.collections[collection_name] = collection
            return collection
            
        except Exception as e:
            logger.error(f"✗ 创建集合 '{collection_name}' 失败: {e}")
            raise
    
    def get_collection(self, collection_name: str) -> Optional[Collection]:
        """
        获取集合
        
        Args:
            collection_name: 集合名称
            
        Returns:
            Collection: 集合对象，不存在则返回 None
        """
        try:
            if collection_name in self.collections:
                return self.collections[collection_name]
            
            if utility.has_collection(collection_name):
                collection = Collection(collection_name)
                self.collections[collection_name] = collection
                return collection
            
            return None
            
        except Exception as e:
            logger.error(f"获取集合 '{collection_name}' 失败: {e}")
            return None
    
    def drop_collection(self, collection_name: str):
        """
        删除集合
        
        Args:
            collection_name: 集合名称
        """
        try:
            if utility.has_collection(collection_name):
                utility.drop_collection(collection_name)
                if collection_name in self.collections:
                    del self.collections[collection_name]
                logger.info(f"✓ 集合 '{collection_name}' 已删除")
            else:
                logger.warning(f"集合 '{collection_name}' 不存在")
        except Exception as e:
            logger.error(f"✗ 删除集合 '{collection_name}' 失败: {e}")
            raise
    
    def list_collections(self) -> List[str]:
        """
        列出所有集合
        
        Returns:
            List[str]: 集合名称列表
        """
        try:
            collections = utility.list_collections()
            return collections
        except Exception as e:
            logger.error(f"✗ 列出集合失败: {e}")
            return []
    
    def insert_vectors(
        self,
        collection_name: str,
        embeddings: List[List[float]],
        texts: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None
    ) -> List[int]:
        """
        插入向量数据
        
        Args:
            collection_name: 集合名称
            embeddings: 向量列表
            texts: 文本列表
            metadata: 元数据列表
            
        Returns:
            List[int]: 插入的 ID 列表
        """
        try:
            collection = self.get_collection(collection_name)
            if not collection:
                raise Exception(f"集合 '{collection_name}' 不存在")
            
            # 准备数据
            if metadata is None:
                metadata = [{}] * len(embeddings)
            
            data = [
                embeddings,
                texts,
                metadata
            ]
            
            # 插入数据
            mr = collection.insert(data)
            collection.flush()
            
            logger.info(f"✓ 成功插入 {len(embeddings)} 条向量到 '{collection_name}'")
            return mr.primary_keys
            
        except Exception as e:
            logger.error(f"✗ 插入向量失败: {e}")
            raise
    
    def search_vectors(
        self,
        collection_name: str,
        query_embeddings: List[List[float]],
        top_k: int = 10,
        metric_type: str = "COSINE",
        output_fields: Optional[List[str]] = None
    ) -> List[List[Dict[str, Any]]]:
        """
        搜索向量
        
        Args:
            collection_name: 集合名称
            query_embeddings: 查询向量列表
            top_k: 返回 top K 个结果
            metric_type: 度量类型（L2/IP/COSINE），应与创建索引时一致
            output_fields: 需要返回的字段
            
        Returns:
            List[List[Dict]]: 搜索结果
        """
        try:
            collection = self.get_collection(collection_name)
            if not collection:
                raise Exception(f"集合 '{collection_name}' 不存在")
            
            # 加载集合到内存
            collection.load()
            
            # 设置搜索参数
            search_params = {
                "metric_type": metric_type,
                "params": {"nprobe": 10}
            }
            
            if output_fields is None:
                output_fields = ["text", "metadata"]
            
            # 执行搜索
            results = collection.search(
                data=query_embeddings,
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=output_fields
            )
            
            # 格式化结果
            formatted_results = []
            for hits in results:
                hit_list = []
                for hit in hits:
                    hit_dict = {
                        "id": hit.id,
                        "distance": hit.distance,
                        "score": 1.0 / (1.0 + hit.distance)  # 转换为相似度分数
                    }
                    # 添加输出字段
                    for field in output_fields:
                        hit_dict[field] = hit.entity.get(field)
                    hit_list.append(hit_dict)
                formatted_results.append(hit_list)
            
            logger.info(f"✓ 在 '{collection_name}' 中搜索到 {len(formatted_results)} 组结果")
            return formatted_results
            
        except Exception as e:
            logger.error(f"✗ 搜索向量失败: {e}")
            raise
    
    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """
        获取集合统计信息
        
        Args:
            collection_name: 集合名称
            
        Returns:
            Dict: 统计信息
        """
        try:
            collection = self.get_collection(collection_name)
            if not collection:
                return {}
            
            collection.flush()
            stats = {
                "name": collection_name,
                "num_entities": collection.num_entities,
                "description": collection.description
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"✗ 获取集合统计信息失败: {e}")
            return {}
    
    # ==================== 分区管理（Partition）====================
    
    def create_partition(self, collection_name: str, partition_name: str) -> bool:
        """
        创建分区（用于数据分组，提升大规模数据检索性能）
        
        Args:
            collection_name: 集合名称
            partition_name: 分区名称（如 "2024_01", "通知类"）
            
        Returns:
            bool: 是否成功
        """
        try:
            collection = self.get_collection(collection_name)
            if collection is None:
                logger.error(f"✗ 集合 '{collection_name}' 不存在")
                return False
            
            collection.create_partition(partition_name)
            logger.info(f"✓ 分区 '{partition_name}' 创建成功")
            return True
            
        except Exception as e:
            logger.error(f"✗ 创建分区失败: {e}")
            return False
    
    def list_partitions(self, collection_name: str) -> List[str]:
        """
        列出所有分区
        
        Args:
            collection_name: 集合名称
            
        Returns:
            List[str]: 分区名称列表
        """
        try:
            collection = self.get_collection(collection_name)
            if collection is None:
                return []
            
            partitions = [p.name for p in collection.partitions]
            logger.info(f"✓ 集合 '{collection_name}' 的分区: {partitions}")
            return partitions
            
        except Exception as e:
            logger.error(f"✗ 获取分区列表失败: {e}")
            return []
    
    def search_in_partitions(
        self,
        collection_name: str,
        query_embeddings: List[List[float]],
        partition_names: List[str],
        top_k: int = 10,
        metric_type: str = "COSINE",
        output_fields: Optional[List[str]] = None
    ) -> List[List[Dict[str, Any]]]:
        """
        在指定分区中搜索（只搜索部分分区，大幅减少搜索范围和内存占用）
        
        示例：只搜索 "2024_01" 和 "2024_02" 月份的数据
        
        Args:
            collection_name: 集合名称
            query_embeddings: 查询向量列表
            partition_names: 要搜索的分区名称列表（只搜索这些分区）
            top_k: 返回 top K 个结果
            metric_type: 度量类型
            output_fields: 需要返回的字段
            
        Returns:
            List[List[Dict]]: 搜索结果
        """
        try:
            collection = self.get_collection(collection_name)
            if collection is None:
                logger.error(f"✗ 集合 '{collection_name}' 不存在")
                return []
            
            # 加载集合到内存
            collection.load()
            
            # 设置搜索参数
            search_params = {
                "metric_type": metric_type,
                "params": {"nprobe": 10}
            }
            
            if output_fields is None:
                output_fields = ["text", "metadata"]
            
            # 在指定分区中搜索（关键：只搜索 partition_names 分区）
            results = collection.search(
                data=query_embeddings,
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                partition_names=partition_names,  # 只搜索这些分区！
                output_fields=output_fields
            )
            
            # 格式化结果
            formatted_results = []
            for hits in results:
                query_results = []
                for hit in hits:
                    result = {
                        "id": hit.id,
                        "distance": hit.distance,
                        "score": hit.score if hasattr(hit, 'score') else hit.distance,
                    }
                    # 添加输出字段
                    for field in output_fields:
                        if hasattr(hit.entity, field):
                            result[field] = getattr(hit.entity, field)
                    query_results.append(result)
                formatted_results.append(query_results)
            
            logger.info(f"✓ 在分区 {partition_names} 中搜索完成（只搜索了 {len(partition_names)} 个分区）")
            return formatted_results
            
        except Exception as e:
            logger.error(f"✗ 搜索失败: {e}")
            return []
    
    # ==================== 问答缓存集合管理 ====================
    
    def create_qa_cache_collection(
        self,
        dimension: int = 1024,
        metric_type: str = "COSINE"
    ) -> Optional[Collection]:
        """
        创建问答缓存集合（用于相似问题检索）
        
        Args:
            dimension: 向量维度（默认 1024，BGE-large-zh-v1.5）
            metric_type: 相似度度量类型（默认 COSINE）
            
        Returns:
            Collection: 创建的集合对象
        """
        collection_name = MILVUS_QA_COLLECTION_NAME
        
        try:
            # 检查集合是否已存在
            if utility.has_collection(collection_name):
                logger.info(f"问答缓存集合 '{collection_name}' 已存在")
                collection = Collection(collection_name)
                self.collections[collection_name] = collection
                return collection
            
            # 定义字段
            fields = [
                FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
                FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),  # 问题原文
                FieldSchema(name="metadata", dtype=DataType.JSON)  # {thought_chain_id, session_id, answer_preview, user_id}
            ]
            
            # 创建 schema
            schema = CollectionSchema(
                fields=fields,
                description="问答缓存集合 - 用于相似问题检索"
            )
            
            # 创建集合
            collection = Collection(
                name=collection_name,
                schema=schema,
                using=self._connection_alias
            )
            
            # 创建索引（使用 HNSW 索引，适合高精度检索）
            index_params = {
                "metric_type": metric_type,
                "index_type": "HNSW",
                "params": {"M": 16, "efConstruction": 256}
            }
            
            collection.create_index(
                field_name="embedding",
                index_params=index_params
            )
            
            logger.info(f"✓ 问答缓存集合 '{collection_name}' 创建成功")
            logger.info(f"  - 维度: {dimension}")
            logger.info(f"  - 索引类型: HNSW")
            logger.info(f"  - 度量类型: {metric_type}")
            
            self.collections[collection_name] = collection
            return collection
            
        except Exception as e:
            logger.error(f"✗ 创建问答缓存集合失败: {e}")
            return None
    
    def insert_qa_cache(
        self,
        question_embedding: List[float],
        question_text: str,
        metadata: Dict[str, Any]
    ) -> Optional[int]:
        """
        插入问答缓存
        
        Args:
            question_embedding: 问题的向量表示
            question_text: 问题原文
            metadata: 元数据 {thought_chain_id, session_id, answer_preview, user_id, created_at}
            
        Returns:
            插入的 ID，失败返回 None
        """
        collection_name = MILVUS_QA_COLLECTION_NAME
        
        try:
            collection = self.get_collection(collection_name)
            if not collection:
                # 自动创建集合
                collection = self.create_qa_cache_collection(dimension=len(question_embedding))
                if not collection:
                    raise Exception("无法创建问答缓存集合")
            
            # 准备数据
            data = [
                [question_embedding],
                [question_text],
                [metadata]
            ]
            
            # 插入数据
            mr = collection.insert(data)
            collection.flush()
            
            inserted_id = mr.primary_keys[0] if mr.primary_keys else None
            return inserted_id
            
        except Exception as e:
            logger.error(f"插入问答缓存失败: {e}", exc_info=True)
            return None
    
    def search_similar_questions(
        self,
        query_embedding: List[float],
        top_k: int = 1,
        score_threshold: float = 0.95
    ) -> List[Dict[str, Any]]:
        """
        搜索相似问题
        
        Args:
            query_embedding: 查询问题的向量表示
            top_k: 返回 top K 个结果
            score_threshold: 相似度阈值（0-1，COSINE 相似度）
            
        Returns:
            List[Dict]: 相似问题列表 [{id, score, text, metadata}]
        """
        collection_name = MILVUS_QA_COLLECTION_NAME
        
        try:
            collection = self.get_collection(collection_name)
            if not collection:
                return []
            
            # 获取集合统计信息
            collection.flush()
            num_entities = collection.num_entities
            
            if num_entities == 0:
                return []
            
            # 加载集合到内存
            collection.load()
            
            # 设置搜索参数
            search_params = {
                "metric_type": "COSINE",
                "params": {"ef": 64}  # HNSW 搜索参数
            }
            
            # 执行搜索
            results = collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["text", "metadata"]
            )
            
            # 格式化结果并过滤
            similar_questions = []
            for hits in results:
                for hit in hits:
                    # Milvus COSINE 度量：distance 直接就是 cosine similarity
                    similarity = hit.distance
                    
                    if similarity >= score_threshold:
                        similar_questions.append({
                            "id": hit.id,
                            "score": similarity,
                            "text": hit.entity.get("text"),
                            "metadata": hit.entity.get("metadata")
                        })
            
            return similar_questions
            
        except Exception as e:
            logger.error(f"搜索相似问题失败: {e}", exc_info=True)
            return []
    
    def delete_qa_cache(self, milvus_id: int) -> bool:
        """
        删除 QA 缓存
        
        Args:
            milvus_id: Milvus 中的记录 ID
            
        Returns:
            是否删除成功
        """
        collection_name = MILVUS_QA_COLLECTION_NAME
        
        try:
            collection = self.get_collection(collection_name)
            if not collection:
                return False
            
            # 使用表达式删除
            expr = f"id == {milvus_id}"
            collection.delete(expr)
            collection.flush()
            
            logger.info(f"✓ 已删除 QA 缓存: id={milvus_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除 QA 缓存失败: {e}", exc_info=True)
            return False
    
    def delete_qa_cache_by_thought_chain_id(self, thought_chain_id: str) -> bool:
        """
        根据思维链 ID 删除 QA 缓存
        
        Args:
            thought_chain_id: 思维链 UUID
            
        Returns:
            是否删除成功
        """
        collection_name = MILVUS_QA_COLLECTION_NAME
        
        try:
            collection = self.get_collection(collection_name)
            if not collection:
                return False
            
            # 加载集合
            collection.load()
            
            # 先查询找到对应的 ID
            # 注意：Milvus 不支持直接按 JSON 字段删除，需要先查询
            # 这里使用一个变通方法：查询所有记录然后过滤
            # 对于大规模数据，建议在 metadata 中添加索引字段
            
            # 查询所有记录（限制数量避免内存问题）
            results = collection.query(
                expr="id >= 0",
                output_fields=["id", "metadata"],
                limit=10000
            )
            
            # 找到匹配的记录
            ids_to_delete = []
            for record in results:
                metadata = record.get("metadata", {})
                if metadata.get("thought_chain_id") == thought_chain_id:
                    ids_to_delete.append(record["id"])
            
            if not ids_to_delete:
                logger.debug(f"未找到对应的 QA 缓存: thought_chain_id={thought_chain_id}")
                return True  # 没有找到也算成功
            
            # 删除找到的记录
            for mid in ids_to_delete:
                expr = f"id == {mid}"
                collection.delete(expr)
            
            collection.flush()
            logger.info(f"✓ 已删除 QA 缓存: thought_chain_id={thought_chain_id}, count={len(ids_to_delete)}")
            return True
            
        except Exception as e:
            logger.error(f"删除 QA 缓存失败: {e}", exc_info=True)
            return False


# 创建全局单例实例
milvus_client = Milvus()

