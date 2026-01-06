"""
网页搜索工具 - FastMCP 版本
"""
import sys
import os
# 添加项目根目录到路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from mcp.server import FastMCP
from typing import Dict, Any
import requests
import json

app = FastMCP("web_search")


@app.tool()
def web_search(
    query: str,
    max_results: int = 5,
    search_recency: str = "week"
) -> str:
    """
    网页搜索工具
    
    Args:
        query: 搜索关键词
        max_results: 最大返回结果数
        search_recency: 时间范围（day/week/month/year/all）
        
    Returns:
        Dict: 包含搜索结果的字典
    """
    try:
        from pkg.constants.constants import BAIDU_TOKEN
        
        if not BAIDU_TOKEN:
            return "网页搜索功能未配置（缺少 BAIDU_TOKEN）"
        
        url = "https://qianfan.baidubce.com/v2/ai_search/web_search"
        payload = {
            "messages": [{"role": "user", "content": query}],
            "edition": "standard",
            "search_source": "baidu_search_v2",
            "search_recency_filter": search_recency
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {BAIDU_TOKEN}'
        }
        
        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=10
        )
        data = response.json()
        
        if "references" not in data or not data["references"]:
            return "未找到相关搜索结果"
        
        references = data["references"][:max_results]
        
        summary_parts = []
        for i, ref in enumerate(references, 1):
            part = f"""[搜索结果 {i} - {ref.get('title', '无标题')}]
来源: {ref.get('website', '')}
URL: {ref.get('url', '')}
内容: {ref.get('content', '')[:300]}..."""
            summary_parts.append(part)
        return "\n\n".join(summary_parts)
        
    except Exception as e:
        return f"搜索失败: {str(e)}"


if __name__ == "__main__":
    app.run(transport="stdio")
