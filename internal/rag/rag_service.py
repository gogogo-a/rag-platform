"""
RAG 服务
专注于向量检索和上下文生成

特性：
1. 向量检索
2. Reranker 重排序（可选）
3. 智能去重：自动过滤分数差异 <= 0.02 (相似度 >= 98%) 的重复文档
4. 返回指定数量的最相关不重复文档

注意：文档的加载、分割、向量化和存储请使用 document_processor.add_documents()
"""
from typing import List, Dict, Any, Optional
import logging
import time

from internal.embedding.embedding_service import embedding_service
from internal.db.milvus import milvus_client
from internal.reranker.reranker_service import reranker_service
from pkg.model_list import BGE_LARGE_ZH_V1_5, BGE_RERANKER_V2_M3  # 默认模型配置
from pkg.constants.constants import MILVUS_COLLECTION_NAME
from internal.monitor import performance_monitor, record_performance

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 服务类 - 专注于检索功能"""
    
    def __init__(
        self,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        reranker_model: Optional[str] = None,
        top_k: int = 5,
        use_reranker: bool = True
    ):
        """
        初始化 RAG 服务（仅检索功能）
        
        Args:
            collection_name: Milvus 集合名称
            embedding_model: Embedding 模型名称，如果为 None 则使用 BGE_LARGE_ZH_V1_5
            reranker_model: Reranker 模型名称，如果为 None 则使用 BGE_RERANKER_V2_M3
            top_k: 检索返回结果数量
            use_reranker: 是否使用 Reranker
        """
        # 如果没有指定模型，使用默认配置
        if embedding_model is None:
            embedding_model = BGE_LARGE_ZH_V1_5.name
        if reranker_model is None:
            reranker_model = BGE_RERANKER_V2_M3.name
        
        # 如果没有指定 collection_name，使用全局配置
        if collection_name is None:
            collection_name = MILVUS_COLLECTION_NAME
        
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
        self.top_k = top_k
        self.use_reranker = use_reranker
        
        # 初始化检索相关组件
        self.embedder = embedding_service
        self.vector_db = milvus_client
        self.reranker = reranker_service if use_reranker else None
        
        logger.info(f"RAG 检索服务已初始化")
        logger.info(f"  集合名称: {collection_name}")
        logger.info(f"  Embedding 模型: {embedding_model}")
        logger.info(f"  Reranker 模型: {reranker_model if use_reranker else '未启用'}")
    
    def _deduplicate_results(
        self,
        results: List[Dict[str, Any]],
        score_diff_threshold: float = 0.02,
        target_count: int = 5
    ) -> List[Dict[str, Any]]:
        """
        去重检索结果：过滤掉分数极其接近的重复文档
        
        判定标准：
        - 分数完全相同
        - 或者分数差异 <= 0.02（意味着相似度 >= 98%）
        
        Args:
            results: 检索结果列表（必须包含分数字段）
            score_diff_threshold: 分数差异阈值，默认0.02（2%）
            target_count: 目标返回数量
            
        Returns:
            List[Dict]: 去重后的结果列表
        """
        if not results:
            return []
        
        # 确定使用哪个分数字段（优先使用 rerank_score）
        score_field = "rerank_score" if "rerank_score" in results[0] else "vector_score"
        
        # 按分数降序排序（确保高分在前）
        sorted_results = sorted(results, key=lambda x: x.get(score_field, 0), reverse=True)
        
        deduplicated = []
        
        for current in sorted_results:
            current_score = current.get(score_field, 0)
            is_duplicate = False
            
            # 检查是否与已选中的文档重复
            for selected in deduplicated:
                selected_score = selected.get(score_field, 0)
                
                # 计算分数差异（绝对值）
                score_diff = abs(current_score - selected_score)
                
                # 如果分数差异小于等于阈值，认为是重复
                # 例如：0.95 和 0.94 差异为 0.01 < 0.02，判定为重复
                if score_diff <= score_diff_threshold:
                    is_duplicate = True
                    similarity_pct = (1 - score_diff) * 100
                    logger.debug(
                        f"去重：文档 {current.get('id')} (分数: {current_score:.4f}) "
                        f"与 {selected.get('id')} (分数: {selected_score:.4f}) "
                        f"差异: {score_diff:.4f} (相似度: {similarity_pct:.1f}%)，判定为重复"
                    )
                    break
            
            # 如果不是重复，添加到结果中
            if not is_duplicate:
                deduplicated.append(current)
                
                # 如果已达到目标数量，停止
                if len(deduplicated) >= target_count:
                    break
        
        logger.info(f"✓ 去重完成：{len(results)} -> {len(deduplicated)} 个文档")
        
        return deduplicated
    
    def initialize(self):
        """初始化所有组件"""
        try:
            # 连接 Milvus
            self.vector_db.connect()
            
            # 加载 Embedding 模型
            self.embedder.load_model()
            
            # 加载 Reranker 模型（如果启用）
            if self.use_reranker and self.reranker:
                self.reranker.load_model()
            
            # 获取模型信息
            model_info = self.embedder.get_model_info()
            dimension = model_info["dimension"]
            
            # 创建或获取集合
            collection = self.vector_db.get_collection(self.collection_name)
            if not collection:
                logger.info(f"创建新集合: {self.collection_name}")
                self.vector_db.create_collection(
                    collection_name=self.collection_name,
                    dimension=dimension,
                    description=f"RAG 文档集合 - {self.embedding_model}",
                    metric_type="COSINE"
                )
            else:
                logger.info(f"使用现有集合: {self.collection_name}")
            
            logger.info("✓ RAG 检索服务初始化完成")
            
        except Exception as e:
            logger.error(f"✗ RAG 检索服务初始化失败: {e}")
            raise
    
    @performance_monitor('milvus_search', operation_name='向量检索+Rerank', include_args=True, include_result=True)
    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
        use_reranker: Optional[bool] = None,
        rerank_top_k: Optional[int] = None,
        rerank_score_threshold: float = -100.0,  # BGE reranker 输出 logits，可以是负数
        user_permission: int = 0  # 🔥 用户权限（0=普通用户，1=管理员）
    ) -> List[Dict[str, Any]]:
        """
        搜索相关文档（包含 Rerank 和去重）
        
        流程：
        1. 向量检索
        2. 根据用户权限过滤文档（普通用户只能看permission=0的文档，管理员可以看所有文档）
        3. Rerank 重排序（可选）
        4. 去重：过滤分数差异 <= 0.02 (相似度 >= 98%) 的重复文档
        5. 返回最多 top_k 个最相关的不重复文档
        
        Args:
            query: 查询文本
            top_k: 初始向量检索返回结果数量（会被 Reranker 处理）
            filter_metadata: 元数据过滤条件
            use_reranker: 是否使用 Reranker（None 表示使用默认设置）
            rerank_top_k: 去重后返回的结果数量（默认5个，None 表示与 top_k 相同）
            rerank_score_threshold: Rerank 分数阈值
            user_permission: 用户权限（0=普通用户，只能查询permission=0的文档；1=管理员，可查询所有文档）
            
        Returns:
            List[Dict]: 去重后的搜索结果列表（最多 rerank_top_k 个不重复文档）
        """
        try:
            if top_k is None:
                top_k = self.top_k
            else:
                # 确保 top_k 是整数类型（可能从工具调用传入字符串）
                top_k = int(top_k)
            
            if use_reranker is None:
                use_reranker = self.use_reranker
            
            if rerank_top_k is None:
                rerank_top_k = top_k
            else:
                rerank_top_k = int(rerank_top_k)
            
            logger.info(f"搜索查询: {query[:50]}...")
            
            # 1. 向量化查询（手动记录 embedding 性能）
            embedding_start = time.time()
            query_embedding = self.embedder.encode_query(
                query=query,
                normalize=True
            )
            embedding_duration = time.time() - embedding_start
            
            # 记录 embedding 性能（自动计算 token 数量和 ms/10k tokens）
            record_performance(
                monitor_type='embedding',
                operation='查询向量化',
                duration=embedding_duration,
                query_length=len(query),
                text=query  # 用于自动计算 token 数量
            )
            
            # 2. 向量检索（如果使用 Reranker，检索更多候选）
            retrieval_top_k = top_k * 3 if use_reranker else top_k
            # 限制最大值，避免超过 Milvus 的 limit 限制
            retrieval_top_k = min(retrieval_top_k, 512)
            
            results = self.vector_db.search_vectors(
                collection_name=self.collection_name,
                query_embeddings=[query_embedding.tolist()],
                top_k=retrieval_top_k,
                metric_type="COSINE",
                output_fields=["text", "metadata"]
            )
            
            # 3. 格式化结果
            formatted_results = []
            if results and len(results) > 0:
                for hit in results[0]:  # 只有一个查询
                    result = {
                        "id": hit["id"],
                        "text": hit["text"],
                        "metadata": hit["metadata"],
                        "vector_score": hit["score"],
                        "distance": hit["distance"]
                    }
                    
                    # 应用元数据过滤
                    if filter_metadata:
                        match = all(
                            hit["metadata"].get(k) == v
                            for k, v in filter_metadata.items()
                        )
                        if not match:
                            continue
                    
                    # 🔥 权限过滤：普通用户（user_permission=0）只能看 permission=0 的文档
                    # 📌 兼容性处理：旧文档没有 permission 字段，默认视为 0（普通用户可见）
                    doc_permission = hit["metadata"].get("permission", 0)  # 默认为 0
                    if user_permission == 0 and doc_permission == 1:
                        # 普通用户不能看管理员专属文档
                        logger.debug(f"权限过滤：跳过管理员文档 {hit['id']}")
                        continue
                    
                    formatted_results.append(result)
            
            logger.info(f"✓ 向量检索完成，返回 {len(formatted_results)} 条候选（已应用权限过滤，user_permission={user_permission}）")
            
            # 4. Rerank 步骤（如果启用）
            if use_reranker and self.reranker and formatted_results:
                logger.info(f"开始 Rerank...")
                
                reranked_results = self.reranker.rerank(
                    query=query,
                    documents=formatted_results,
                    top_k=rerank_top_k * 2,  # 先获取更多结果，去重后再截取
                    score_threshold=rerank_score_threshold
                )
                
                logger.info(f"✓ Rerank 完成，返回 {len(reranked_results)} 条结果")
                
                # 5. 去重：过滤分数差异 <= 0.02 的重复文档
                deduplicated_results = self._deduplicate_results(
                    results=reranked_results,
                    score_diff_threshold=0.02,
                    target_count=rerank_top_k
                )
                
                return deduplicated_results
            
            # 6. 不使用 Reranker，直接返回向量检索结果（也需要去重）
            deduplicated_results = self._deduplicate_results(
                results=formatted_results,
                score_diff_threshold=0.02,
                target_count=rerank_top_k
            )
            
            return deduplicated_results
            
        except Exception as e:
            logger.error(f"✗ 搜索失败: {e}")
            raise
    
    def get_context_for_query(
        self,
        query: str,
        top_k: Optional[int] = None,
        max_context_length: int = 2000,
        use_reranker: Optional[bool] = None,
        rerank_score_threshold: float = 0.0
    ) -> str:
        """
        获取查询的上下文文本（用于 LLM，自动应用 Reranker）
        
        Args:
            query: 查询文本
            top_k: 返回结果数量
            max_context_length: 最大上下文长度
            use_reranker: 是否使用 Reranker
            rerank_score_threshold: Rerank 分数阈值
            
        Returns:
            str: 拼接的上下文文本
        """
        try:
            # 搜索相关文档（包含 Rerank）
            results = self.search(
                query,
                top_k=top_k,
                use_reranker=use_reranker,
                rerank_score_threshold=rerank_score_threshold
            )
            
            if not results:
                return ""
            
            # 拼接上下文
            context_parts = []
            current_length = 0
            
            for i, result in enumerate(results, 1):
                text = result["text"]
                source = result["metadata"].get("filename", "未知来源")
                
                # 添加分数信息（如果有 rerank_score）
                score_info = ""
                if "rerank_score" in result:
                    score_info = f" (Rerank分数: {result['rerank_score']:.4f})"
                
                # 格式化引用
                part = f"[文档{i} - {source}{score_info}]\n{text}\n"
                part_length = len(part)
                
                # 检查长度限制
                if current_length + part_length > max_context_length:
                    break
                
                context_parts.append(part)
                current_length += part_length
            
            context = "\n".join(context_parts)
            
            logger.info(f"✓ 生成上下文，长度: {len(context)} 字符")
            
            return context
            
        except Exception as e:
            logger.error(f"✗ 获取上下文失败: {e}")
            return ""
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """获取集合统计信息"""
        try:
            stats = self.vector_db.get_collection_stats(self.collection_name)
            model_info = self.embedder.get_model_info()
            
            return {
                **stats,
                "embedding_model": model_info["model_name"],
                "dimension": model_info["dimension"]
            }
        except Exception as e:
            logger.error(f"✗ 获取统计信息失败: {e}")
            return {}


# 创建默认 RAG 检索服务实例（使用全局配置和默认模型 BGE_LARGE_ZH_V1_5、BGE_RERANKER_V2_M3）
rag_service = RAGService(
    collection_name=None,  # 使用全局配置 MILVUS_COLLECTION_NAME
    top_k=5,
    use_reranker=True
)

