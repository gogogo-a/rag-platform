"""
3D 文档可视化服务
使用 UMAP 对文档向量进行降维，生成 3D 坐标
"""
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import numpy as np

from pymilvus import Collection

from log import logger
from internal.db.milvus import milvus_client
from pkg.constants.constants import MILVUS_COLLECTION_NAME, MILVUS_QA_COLLECTION_NAME


class Document3DService:
    """3D 文档可视化服务"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.collection_name = MILVUS_COLLECTION_NAME
        # 缓存降维结果 {cache_key: {coordinates, timestamp, doc_count}}
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = 86400  # 缓存 24 小时
        self._last_doc_count = 0  # 上次文档数量，用于检测变化
    
    def _get_cache_key(self, doc_uuids: List[str]) -> str:
        """生成缓存 key"""
        sorted_uuids = sorted(doc_uuids)
        content = json.dumps(sorted_uuids)
        return hashlib.md5(content.encode()).hexdigest()
    
    def _is_cache_valid(self, cache_key: str, current_doc_count: int) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self._cache:
            return False
        cached = self._cache[cache_key]
        
        # 检查时间
        elapsed = (datetime.now() - cached['timestamp']).total_seconds()
        if elapsed >= self._cache_ttl:
            logger.info(f"3D 缓存已过期 ({elapsed/3600:.1f}h)")
            return False
        
        # 检查文档数量是否变化
        if cached.get('doc_count', 0) != current_doc_count:
            logger.info(f"文档数量变化 ({cached.get('doc_count', 0)} -> {current_doc_count})，缓存失效")
            return False
        
        return True
    
    async def get_document_vectors(
        self,
        page: int = 1,
        page_size: int = 500,
        keyword: Optional[str] = None
    ) -> Tuple[str, int, Optional[Dict[str, Any]]]:
        """
        获取文档向量数据（按文档 UUID 去重，每个文档取第一个 chunk 的向量）
        
        Args:
            page: 页码
            page_size: 每页数量（最大 500）
            keyword: 搜索关键词
            
        Returns:
            (message, ret, data)
        """
        try:
            # 检查集合是否存在
            existing_collections = milvus_client.list_collections()
            if self.collection_name not in existing_collections:
                return "集合不存在", -2, None
            
            collection = Collection(self.collection_name)
            collection.load()
            
            # 查询所有向量（带元数据）
            # 注意：Milvus 不支持 GROUP BY，需要在应用层去重
            results = collection.query(
                expr="id >= 0",
                output_fields=["id", "embedding", "text", "metadata"],
                limit=16384  # Milvus 单次查询上限
            )
            
            if not results:
                return "暂无文档数据", 0, {"total": 0, "documents": [], "coordinates": []}
            
            # 按 document_uuid 去重，每个文档只保留第一个 chunk
            doc_map: Dict[str, Dict] = {}
            for item in results:
                metadata = item.get("metadata", {})
                doc_uuid = metadata.get("document_uuid")
                
                if not doc_uuid:
                    continue
                
                # 关键词过滤
                if keyword:
                    filename = metadata.get("filename", "")
                    text = item.get("text", "")
                    if keyword.lower() not in filename.lower() and keyword.lower() not in text.lower():
                        continue
                
                # 只保留每个文档的第一个 chunk
                if doc_uuid not in doc_map:
                    doc_map[doc_uuid] = {
                        "uuid": doc_uuid,
                        "milvus_id": item["id"],
                        "embedding": item["embedding"],
                        "text": item.get("text", "")[:100],  # 前 100 字符
                        "metadata": metadata
                    }
            
            # 转换为列表
            all_docs = list(doc_map.values())
            total = len(all_docs)
            
            # 分页
            start = (page - 1) * page_size
            end = start + page_size
            paged_docs = all_docs[start:end]
            
            if not paged_docs:
                return "查询成功", 0, {"total": total, "documents": [], "coordinates": []}
            
            # 提取向量进行 UMAP 降维
            embeddings = [doc["embedding"] for doc in paged_docs]
            doc_uuids = [doc["uuid"] for doc in paged_docs]
            
            # 检查缓存
            cache_key = self._get_cache_key(doc_uuids)
            if self._is_cache_valid(cache_key, len(paged_docs)):
                coordinates = self._cache[cache_key]['coordinates']
                logger.info(f"使用缓存的 3D 坐标: {len(coordinates)} 个点")
            else:
                # UMAP 降维到 3D
                coordinates = self._umap_reduce(embeddings)
                # 缓存结果
                self._cache[cache_key] = {
                    'coordinates': coordinates,
                    'timestamp': datetime.now(),
                    'doc_count': len(paged_docs)
                }
                logger.info(f"UMAP 降维完成并缓存: {len(coordinates)} 个点，有效期 24h")
            
            # 构建返回数据
            documents = []
            for i, doc in enumerate(paged_docs):
                metadata = doc["metadata"]
                # 获取文件类型
                filename = metadata.get("filename", "unknown")
                file_ext = filename.split(".")[-1].lower() if "." in filename else "unknown"
                
                documents.append({
                    "uuid": doc["uuid"],
                    "filename": filename,
                    "file_type": file_ext,
                    "text_preview": doc["text"],
                    "chunk_index": metadata.get("chunk_index", 0),
                    "created_at": metadata.get("upload_time") or metadata.get("created_at"),
                    "permission": metadata.get("permission", 0),
                    "x": coordinates[i][0],
                    "y": coordinates[i][1],
                    "z": coordinates[i][2]
                })
            
            data = {
                "total": total,
                "page": page,
                "page_size": page_size,
                "documents": documents
            }
            
            return "查询成功", 0, data
            
        except Exception as e:
            logger.error(f"获取文档向量失败: {e}", exc_info=True)
            return f"查询失败: {str(e)}", -1, None
    
    def _umap_reduce(self, embeddings: List[List[float]], n_components: int = 3) -> List[List[float]]:
        """
        使用 UMAP 将高维向量降维到 3D
        
        Args:
            embeddings: 高维向量列表
            n_components: 目标维度（默认 3）
            
        Returns:
            降维后的坐标列表 [[x, y, z], ...]
        """
        try:
            import umap
            
            embeddings_array = np.array(embeddings)
            n_samples = len(embeddings)
            
            if n_samples < 4:
                logger.warning(f"样本数量太少 ({n_samples})，使用球面分布")
                return self._sphere_distribute(n_samples)
            
            # 使用默认 UMAP 参数，让相似文档自然聚类
            n_neighbors = min(15, max(5, n_samples // 10))
            min_dist = 0.1  # 较小的值允许形成紧密的簇
            
            reducer = umap.UMAP(
                n_components=n_components,
                n_neighbors=n_neighbors,
                min_dist=min_dist,
                metric='cosine',
                random_state=42
            )
            
            reduced = reducer.fit_transform(embeddings_array)
            
            # 应用斥力分散算法，避免点重叠但保持簇结构
            reduced = self._apply_repulsion(reduced, iterations=20, min_distance=5.0)
            
            # 归一化到合适范围
            reduced = self._normalize_coordinates(reduced, scale=50)
            
            return reduced.tolist()
            
        except ImportError:
            logger.warning("UMAP 未安装，使用 PCA 降维")
            return self._pca_reduce(embeddings, n_components)
        except Exception as e:
            logger.error(f"UMAP 降维失败: {e}")
            return self._pca_reduce(embeddings, n_components)
    
    def _pca_reduce(self, embeddings: List[List[float]], n_components: int = 3) -> List[List[float]]:
        """使用 PCA 降维（备选方案）"""
        try:
            from sklearn.decomposition import PCA
            
            embeddings_array = np.array(embeddings)
            n_samples = len(embeddings)
            
            if n_samples < n_components:
                return self._sphere_distribute(n_samples)
            
            pca = PCA(n_components=n_components)
            reduced = pca.fit_transform(embeddings_array)
            
            # 应用斥力分散
            reduced = self._apply_repulsion(reduced, iterations=20, min_distance=5.0)
            reduced = self._normalize_coordinates(reduced, scale=50)
            
            return reduced.tolist()
            
        except Exception as e:
            logger.error(f"PCA 降维失败: {e}")
            return self._sphere_distribute(len(embeddings))
    
    def _apply_repulsion(self, coords: np.ndarray, iterations: int = 50, min_distance: float = 8.0) -> np.ndarray:
        """
        应用斥力算法，让过近的点互相排斥
        
        Args:
            coords: 坐标数组
            iterations: 迭代次数
            min_distance: 最小距离阈值
        """
        coords = coords.copy()
        n = len(coords)
        
        if n < 2:
            return coords
        
        for _ in range(iterations):
            for i in range(n):
                for j in range(i + 1, n):
                    diff = coords[i] - coords[j]
                    dist = np.linalg.norm(diff)
                    
                    if dist < min_distance and dist > 0.01:
                        # 计算斥力方向和大小
                        force = (min_distance - dist) / min_distance * 0.5
                        direction = diff / dist
                        
                        # 双向推开
                        coords[i] += direction * force
                        coords[j] -= direction * force
        
        return coords
    
    def _sphere_distribute(self, n_samples: int, radius: float = 50) -> List[List[float]]:
        """在球面上均匀分布点（斐波那契球面）"""
        coords = []
        phi = np.pi * (3.0 - np.sqrt(5.0))  # 黄金角
        
        for i in range(n_samples):
            y = 1 - (i / float(n_samples - 1)) * 2 if n_samples > 1 else 0
            r = np.sqrt(1 - y * y)
            theta = phi * i
            
            x = np.cos(theta) * r * radius
            z = np.sin(theta) * r * radius
            y = y * radius
            
            coords.append([x, y, z])
        
        return coords
    
    def _random_distribute(self, n_samples: int, scale: float = 50) -> List[List[float]]:
        """随机分布（最后的备选方案）"""
        np.random.seed(42)
        coords = np.random.uniform(-scale, scale, (n_samples, 3))
        return coords.tolist()
    
    def _normalize_coordinates(self, coords: np.ndarray, scale: float = 50) -> np.ndarray:
        """归一化坐标到指定范围"""
        # 中心化
        coords = coords - coords.mean(axis=0)
        # 缩放到 [-scale, scale]
        max_abs = np.abs(coords).max()
        if max_abs > 0:
            coords = coords / max_abs * scale
        return coords
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("3D 可视化缓存已清空")


# 单例实例
document_3d_service = Document3DService()


class QACache3DService:
    """QA 缓存 3D 可视化服务"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        self.collection_name = MILVUS_QA_COLLECTION_NAME
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = 86400  # 24 小时
    
    def _get_cache_key(self, ids: List[str]) -> str:
        """生成缓存 key"""
        sorted_ids = sorted(ids)
        content = json.dumps(sorted_ids)
        return hashlib.md5(content.encode()).hexdigest()
    
    def _is_cache_valid(self, cache_key: str, current_count: int) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self._cache:
            return False
        cached = self._cache[cache_key]
        elapsed = (datetime.now() - cached['timestamp']).total_seconds()
        if elapsed >= self._cache_ttl:
            return False
        if cached.get('count', 0) != current_count:
            return False
        return True
    
    async def get_qa_vectors(
        self,
        page: int = 1,
        page_size: int = 500,
        keyword: Optional[str] = None
    ) -> Tuple[str, int, Optional[Dict[str, Any]]]:
        """
        获取 QA 缓存向量数据用于 3D 可视化
        """
        try:
            from pymilvus import Collection, utility
            
            # 检查集合是否存在
            if not utility.has_collection(self.collection_name):
                return "QA 缓存集合不存在", -2, None
            
            collection = Collection(self.collection_name)
            collection.load()
            
            # 查询所有 QA 缓存
            results = collection.query(
                expr="id >= 0",
                output_fields=["id", "embedding", "text", "metadata"],
                limit=16384
            )
            
            if not results:
                return "暂无 QA 缓存数据", 0, {"total": 0, "items": []}
            
            # 关键词过滤
            filtered = []
            for item in results:
                text = item.get("text", "")
                metadata = item.get("metadata", {})
                answer_preview = metadata.get("answer_preview", "")
                
                if keyword:
                    if keyword.lower() not in text.lower() and keyword.lower() not in answer_preview.lower():
                        continue
                
                filtered.append(item)
            
            total = len(filtered)
            
            # 分页
            start = (page - 1) * page_size
            end = start + page_size
            paged = filtered[start:end]
            
            if not paged:
                return "查询成功", 0, {"total": total, "items": []}
            
            # 提取向量进行降维
            embeddings = [item["embedding"] for item in paged]
            ids = [str(item["id"]) for item in paged]
            
            # 检查缓存
            cache_key = self._get_cache_key(ids)
            if self._is_cache_valid(cache_key, len(paged)):
                coordinates = self._cache[cache_key]['coordinates']
            else:
                # UMAP 降维
                coordinates = document_3d_service._umap_reduce(embeddings)
                self._cache[cache_key] = {
                    'coordinates': coordinates,
                    'timestamp': datetime.now(),
                    'count': len(paged)
                }
            
            # 构建返回数据
            items = []
            for i, item in enumerate(paged):
                metadata = item.get("metadata", {})
                items.append({
                    "id": item["id"],
                    "question": item.get("text", "")[:100],
                    "answer_preview": metadata.get("answer_preview", "")[:100],
                    "thought_chain_id": metadata.get("thought_chain_id"),
                    "created_at": metadata.get("created_at"),
                    "x": coordinates[i][0],
                    "y": coordinates[i][1],
                    "z": coordinates[i][2]
                })
            
            data = {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": items
            }
            
            return "查询成功", 0, data
            
        except Exception as e:
            logger.error(f"获取 QA 缓存向量失败: {e}", exc_info=True)
            return f"查询失败: {str(e)}", -1, None
    
    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()
        logger.info("QA 3D 可视化缓存已清空")


# 单例实例
qa_cache_3d_service = QACache3DService()
