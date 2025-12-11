from mcp.server import FastMCP  
import requests
from typing import Dict, Any
import json
app = FastMCP('web-search')
BAIDU_TOKEN=""
@app.tool()
def web_search(query: str, max_results: int = 5, search_recency: str = "week") -> Dict[str, Any]:
    """
    网页搜索工具
    从互联网搜索实时信息（使用百度千帆 AI Search API）
    
    Args:
        query: 搜索关键词
        max_results: 最大返回结果数（默认 5）
        search_recency: 时间范围过滤
            - "day": 最近一天
            - "week": 最近一周（默认）
            - "month": 最近一个月
            - "year": 最近一年
            - "all": 全部时间
        
    Returns:
        Dict: 包含搜索结果的字典
            - success: 是否成功
            - results: 搜索结果列表
            - summary: 格式化的摘要文本
            - count: 结果数量
            - sources: 来源信息列表（title, url）
    """
    try:
        
        if not BAIDU_TOKEN:
            print("[工具] ⚠️ 百度千帆 API Token 未配置")
            return {
                "success": False,
                "results": [],
                "summary": "",
                "count": 0,
                "sources": [],
                "message": "网页搜索功能未配置（缺少 BAIDU_TOKEN）"
            }
        
        print(f"[工具] 网页搜索: {query} (时间范围: {search_recency}, 最多 {max_results} 条)")
        
        # 构建请求
        url = "https://qianfan.baidubce.com/v2/ai_search/web_search"
        
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": query
                }
            ],
            "edition": "standard",
            "search_source": "baidu_search_v2",
            "search_recency_filter": search_recency
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {BAIDU_TOKEN}'
        }
        
        # 发送请求
        response = requests.post(
            url,
            headers=headers,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            timeout=10
        )
        response.raise_for_status()
        
        # 解析响应
        data = response.json()
        
        if "references" not in data or not data["references"]:
            print("[工具] 未找到相关搜索结果")
            return {
                "success": False,
                "results": [],
                "summary": "",
                "count": 0,
                "sources": [],
                "message": "未找到相关搜索结果"
            }
        
        # 提取搜索结果（限制数量）
        references = data["references"][:max_results]
        
        # 格式化结果
        formatted_results = []
        sources = []
        
        for i, ref in enumerate(references, 1):
            result = {
                "id": i,
                "title": ref.get("title", "无标题"),
                "url": ref.get("url", ""),
                "content": ref.get("content", ref.get("snippet", "")),
                "date": ref.get("date", ""),
                "website": ref.get("website", ""),
                "rerank_score": ref.get("rerank_score", 0),
                "authority_score": ref.get("authority_score", 0)
            }
            formatted_results.append(result)
            
            # 提取来源信息
            sources.append({
                "title": result["title"],
                "url": result["url"],
                "website": result["website"]
            })
        
        # 构建摘要文本
        summary_parts = []
        for i, result in enumerate(formatted_results, 1):
            part = f"""
[搜索结果 {i} - {result['title']}]
来源: {result['website']} ({result['date']})
URL: {result['url']}
内容: {result['content'][:500]}{"..." if len(result['content']) > 500 else ""}
"""
            summary_parts.append(part.strip())
        
        summary = "\n\n".join(summary_parts)
        
        print(f"[工具] 找到 {len(formatted_results)} 个搜索结果")
        print(f"[工具] 摘要长度: {len(summary)} 字符")
        
        return {
            "success": True,
            "results": formatted_results,
            "summary": summary,
            "count": len(formatted_results),
            "sources": sources,
            "message": f"成功搜索到 {len(formatted_results)} 条相关结果",
            "request_id": data.get("request_id", "")
        }
        
    except requests.exceptions.Timeout:
        print("[工具] 网页搜索超时")
        return {
            "success": False,
            "results": [],
            "summary": "",
            "count": 0,
            "sources": [],
            "message": "搜索请求超时，请稍后重试"
        }
    except requests.exceptions.RequestException as e:
        print(f"[工具] 网页搜索请求失败: {e}")
        return {
            "success": False,
            "results": [],
            "summary": "",
            "count": 0,
            "sources": [],
            "message": f"搜索请求失败: {str(e)}"
        }
    except Exception as e:
        print(f"[工具] 网页搜索失败: {e}")
        return {
            "success": False,
            "results": [],
            "summary": "",
            "count": 0,
            "sources": [],
            "message": f"搜索失败: {str(e)}"
        }


web_search.name = "网络搜素"
web_search.description="""
    网页搜索工具
    从互联网搜索实时信息（使用百度千帆 AI Search API）
    
    Args:
        query: 搜索关键词
        max_results: 最大返回结果数（默认 5）
        search_recency: 时间范围过滤
            - "day": 最近一天
            - "week": 最近一周（默认）
            - "month": 最近一个月
            - "year": 最近一年
            - "all": 全部时间
        
    Returns:
        Dict: 包含搜索结果的字典
            - success: 是否成功
            - results: 搜索结果列表
            - summary: 格式化的摘要文本
            - count: 结果数量
            - sources: 来源信息列表（title, url）
    """
if __name__ == "__main__":
    app.run(transport='stdio')