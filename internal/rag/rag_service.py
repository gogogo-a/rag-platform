"""
RAG 服务 - LangChain 版本
使用 LangChain 的 VectorStoreRetriever 和 Milvus 集成

特性：
1. LangChain Milvus 向量存储
2. VectorStoreRetriever 检索器
3. Reranker 重排序（可选）
4. 智能去重
"""
from typing import List, Dict, Any, Optional
import logging
import time

from langchain_milvus import Milvus
from langchain_core.retrievers import BaseRetriever
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from internal.embedding.embedding_service import embedding_service
from internal.reranker.reranker_service import reranker_service
from pkg.model_list import BGE_LARGE_ZH_V1_5, BGE_RERANKER_V2_M3
from pkg.constants.constants import MILVUS_COLLECTION_NAME, MILVUS_HOST, MILVUS_PORT
from internal.monitor import performance_monitor, record_performance

logger = logging.getLogger(__name__)


class LangChainEmbeddingWrapper(Embeddings):
    """包装现有的 embedding_service 为 LangChain Embeddings"""
    
    def __init__(self, embedding_service):
        self.embedding_service = embedding_service
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文档列表"""
        return self.embedding_service.encode_documents(texts)
    
    def embed_query(self, text: str) -> List[float]:
        """嵌入查询"""
        return self.embedding_service.encode_query(text)


class RAGService:
    """RAG 服务类 - LangChain 版本"""
    
    def __init__(
        self,
        collection_name: Optional[str] = None,
        embedding_model: Optional[str] = None,
        reranker_model: Optional[str] = None,
        top_k: int = 5,
        use_reranker: bool = True
    ):
        """
        初始化 RAG 服务 - LangChain 版本
        
        Args:
            collection_name: Milvus 集合名称
            embedding_model: Embedding 模型名称
            reranker_model: Reranker 模型名称
            top_k: 检索返回结果数量
            use_reranker: 是否使用 Reranker
        """
        # 默认配置
        if embedding_model is None:
            embedding_model = BGE_LARGE_ZH_V1_5.name
        if reranker_model is None:
            reranker_model = BGE_RERANKER_V2_M3.name
        if collection_name is None:
            collection_name = MILVUS_COLLECTION_NAME
        
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
        self.top_k = top_k
        self.use_reranker = use_reranker
        
        # 🔥 包装 embedding_service 为 LangChain Embeddings
        self.embeddings = LangChainEmbeddingWrapper(embedding_service)
        
        # 🔥 初始化 LangChain Milvus 向量存储
        # 注意：使用现有 collection 的字段名 "embedding"，而不是默认的 "vector"
        self.vector_store = Milvus(
            embedding_function=self.embeddings,
            collection_name=collection_name,
            connection_args={
                "host": MILVUS_HOST,
                "port": MILVUS_PORT
            },
            vector_field="embedding",  # 🔥 指定向量字段名
            text_field="text",          # 🔥 指定文本字段名
            auto_id=True                # 🔥 使用自动 ID
        )
        
        # 🔥 创建 Retriever
        self.retriever: BaseRetriever = self.vector_store.as_retriever(
            search_kwargs={"k": top_k * 2}  # 多检索一些，用于去重和 rerank
        )
        
        # Reranker（保持不变）
        self.reranker = reranker_service if use_reranker else None
        
        logger.info(f"RAG 检索服务已初始化（LangChain 版本）")
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
        """初始化所有组件 - LangChain 版本（已在 __init__ 中完成）"""
        # 🔥 LangChain 版本不需要手动初始化，在 __init__ 中已经完成
        logger.info("RAG 服务已初始化（LangChain 版本）")
        return
    
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
            
            # 1. 使用 LangChain Retriever 检索（内部会自动进行向量化）
            embedding_start = time.time()
            
            # 🔥 使用 LangChain 的 retriever.get_relevant_documents
            # 注意：这会自动调用 embeddings.embed_query 进行向量化
            docs: List[Document] = self.retriever.get_relevant_documents(query)
            
            embedding_duration = time.time() - embedding_start
            
            # 记录检索性能
            record_performance(
                monitor_type='embedding',
                operation='向量检索',
                duration=embedding_duration,
                query_length=len(query),
                text=query
            )
            
            # 2. 格式化 LangChain Document 为统一格式
            formatted_results = []
            for i, doc in enumerate(docs):
                result = {
                    "id": doc.metadata.get("id", f"doc_{i}"),
                    "text": doc.page_content,
                    "metadata": doc.metadata,
                    "vector_score": doc.metadata.get("score", 0.0),  # LangChain 可能在 metadata 中存储分数
                    "distance": doc.metadata.get("distance", 0.0)
                }
                
                # 应用元数据过滤
                if filter_metadata:
                    match = all(
                        doc.metadata.get(k) == v
                        for k, v in filter_metadata.items()
                    )
                    if not match:
                        continue
                
                # 🔥 权限过滤：普通用户（user_permission=0）只能看 permission=0 的文档
                # 📌 兼容性处理：旧文档没有 permission 字段，默认视为 0（普通用户可见）
                doc_permission = doc.metadata.get("permission", 0)  # 默认为 0
                if user_permission == 0 and doc_permission == 1:
                    # 普通用户不能看管理员专属文档
                    logger.debug(f"权限过滤：跳过管理员文档 {result['id']}")
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
        """获取集合统计信息 - LangChain 版本"""
        try:
            # 🔥 LangChain 版本：直接从配置返回信息
            return {
                "collection_name": self.collection_name,
                "embedding_model": self.embedding_model,
                "reranker_model": self.reranker_model if self.use_reranker else None,
                "top_k": self.top_k
            }
        except Exception as e:
            logger.error(f"✗ 获取统计信息失败: {e}")
            return {}


# 🔥 懒加载：延迟创建实例，避免导入时就初始化模型
_rag_service_instance = None

def get_rag_service():
    """获取 RAG 服务实例（懒加载）"""
    global _rag_service_instance
    if _rag_service_instance is None:
        _rag_service_instance = RAGService(
            collection_name=None,  # 使用全局配置 MILVUS_COLLECTION_NAME
            top_k=5,
            use_reranker=True
        )
    return _rag_service_instance

# 为了向后兼容，保留 rag_service 变量（但使用属性访问）
class _RAGServiceProxy:
    """RAG 服务代理，实现懒加载"""
    def __getattr__(self, name):
        return getattr(get_rag_service(), name)

rag_service = _RAGServiceProxy()

