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
            return "知识库中未找到相关信息"
        
        # 构建上下文
        context_parts = []
        for i, result in enumerate(search_results, 1):
            text = result["text"]
            source = result["metadata"].get("filename", "未知来源")
            part = f"[文档{i} - {source}]\n{text}\n"
            context_parts.append(part)
        
        context = "\n".join(context_parts)
        return f"成功检索到 {len(search_results)} 个相关文档片段：\n\n{context}"
        
    except Exception as e:
        return f"搜索失败: {str(e)}"


if __name__ == "__main__":
    app.run(transport="stdio")
