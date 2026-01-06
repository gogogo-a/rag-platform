"""
POI 地点搜索 MCP 工具
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from mcp.server import FastMCP
from typing import Dict, Any
from pkg.agent_tools.poi_search import poi_search as poi_search_func

app = FastMCP("poi_search")

@app.tool()
def poi_search(
    search_type: str = "text",
    keywords: str = None,
    location: str = None,
    radius: int = 5000,
    polygon: str = None,
    poi_id: str = None,
    types: str = None,
    region: str = None,
    city_limit: bool = False,
    page_size: int = 10,
    page_num: int = 1
) -> Dict[str, Any]:
    """
    POI 地点搜索工具，支持关键字搜索、周边搜索、多边形区域搜索、ID 搜索
    
    Args:
        search_type: 搜索类型（text/around/polygon/detail）
        keywords: 搜索关键字
        location: 中心点坐标（周边搜索时必填）
        radius: 搜索半径（米）
        polygon: 多边形区域坐标
        poi_id: POI ID
        types: POI 类型
        region: 搜索区域
        city_limit: 是否严格限制在区域内
        page_size: 每页数量
        page_num: 页码
    """
    return poi_search_func(
        search_type=search_type,
        keywords=keywords,
        location=location,
        radius=radius,
        polygon=polygon,
        poi_id=poi_id,
        types=types,
        region=region,
        city_limit=city_limit,
        page_size=page_size,
        page_num=page_num
    )

if __name__ == "__main__":
    app.run(transport="stdio")
