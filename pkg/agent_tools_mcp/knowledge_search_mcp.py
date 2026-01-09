"""
知识库搜索工具 - FastMCP 版本
从向量数据库中检索相关知识（RAG）
"""
import sys
import os
import logging

# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# 🔥 配置日志输出到 stderr（不要重定向 stdout，MCP 需要用它通信）
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)

# 🔥 禁用第三方库的日志输出
logging.getLogger("sentence_transformers").setLevel(logging.ERROR)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("filelock").setLevel(logging.ERROR)

# 🔥 禁用 tqdm 进度条
os.environ["TQDM_DISABLE"] = "1"

from mcp.server import FastMCP
from typing import Dict, Any

app = FastMCP("knowledge_search")


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
        use_reranker: 是否使用重排序
        user_permission: 用户权限（0=普通用户，1=管理员）
        
    Returns:
        Dict: 包含搜索结果和上下文的字典
    """
    try:
        import json
        
        # 🔥 延迟导入并获取 rag_service（避免启动时加载模型）
        from internal.rag import rag_service as rag_module
        rag_service = rag_module.rag_service
        
        # 添加调试日志
        import sys
        print(f"[DEBUG] 开始搜索: query={query}, top_k={top_k}", file=sys.stderr)
        
        # 执行 RAG 检索
        search_results = rag_service.search(
            query=query,
            top_k=top_k,
            use_reranker=use_reranker,
            user_permission=user_permission
        )
        
        print(f"[DEBUG] 搜索结果数量: {len(search_results) if search_results else 0}", file=sys.stderr)
        
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
            
            # 🔥 处理嵌套的 metadata 结构
            # LangChain Milvus 返回的格式是 {'id': ..., 'metadata': {...}}
            inner_metadata = metadata.get("metadata", metadata)
            
            # 使用正确的字段名：filename 和 document_uuid
            source = inner_metadata.get("filename", "未知来源")
            doc_uuid = inner_metadata.get("document_uuid", "")
            
            part = f"[文档{i} - {source}]\n{text}\n"
            context_parts.append(part)
            
            # 收集文档信息（按 UUID 和文件名双重去重）
            # 同一个文档的不同 chunk 有相同的 document_uuid 和 filename
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
