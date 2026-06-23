"""知识库搜索工具。"""
import sys
import os
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("filelock").setLevel(logging.ERROR)

os.environ["TQDM_DISABLE"] = "1"

from mcp.server import FastMCP
from typing import Dict, Any

app = FastMCP("knowledge_search")


def _search_qdrant_direct(query: str, top_k: int, user_permission: int):
    from internal.embedding.embedding_service import embedding_service
    from internal.db.qdrant import qdrant_client

    query_embedding = embedding_service.encode_query(query, normalize=True)
    return qdrant_client.search_documents(query_embedding, top_k=top_k, user_permission=user_permission)


@app.tool()
def knowledge_search(
    query: str,
    top_k: int = 5,
    use_reranker: bool = True,
    user_permission: int = 0
) -> str:
    """
    知识库搜索工具
    从向量数据库中检索相关知识（RAG），根据用户权限过滤文档
    
    Args:
        query: 搜索查询
        top_k: 返回结果数量
        use_reranker: 保留兼容参数
        user_permission: 用户权限（0=普通用户，1=管理员）
        
    Returns:
        Dict: 包含搜索结果和上下文的字典
    """
    try:
        import json
        
        search_results = _search_qdrant_direct(query, top_k, user_permission)
        
        if not search_results:
            return json.dumps({
                "success": True,
                "context": "知识库中未找到相关信息",
                "documents": []
            }, ensure_ascii=False)
        
        # 构建上下文和文档列表
        context_parts = []
        documents = []
        seen_doc_names = set()  # 用于按文档名去重
        
        for i, result in enumerate(search_results, 1):
            text = result["text"]
            metadata = result.get("metadata", {})
            
            inner_metadata = metadata.get("metadata", metadata)
            
            # 使用正确的字段名：filename 和 document_uuid
            source = inner_metadata.get("filename", "未知来源")
            doc_uuid = inner_metadata.get("document_uuid", "")
            
            part = f"[文档{i} - {source}]\n{text}\n"
            context_parts.append(part)
            
            if doc_uuid and doc_uuid not in seen_doc_names and source not in seen_doc_names:
                documents.append({
                    "uuid": doc_uuid,
                    "name": source
                })
                seen_doc_names.add(doc_uuid)
                seen_doc_names.add(source)
        
        context = "\n".join(context_parts)
        
        # 返回 JSON 格式（包含文档信息）
        result = {
            "success": True,
            "context": f"成功检索到 {len(search_results)} 个相关文档片段：\n\n{context}",
            "documents": documents
        }
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        import json
        return json.dumps({
            "success": False,
            "context": f"搜索失败: {str(e)}",
            "documents": []
        }, ensure_ascii=False)


if __name__ == "__main__":
    app.run(transport="stdio")
