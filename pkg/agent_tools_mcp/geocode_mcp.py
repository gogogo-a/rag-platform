"""
地理编码/逆地理编码 MCP 工具
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from mcp.server import FastMCP
from typing import Dict, Any
from pkg.agent_tools.geocode import geocode as geocode_func

app = FastMCP("geocode")

@app.tool()
def geocode(
    address: str = None,
    location: str = None,
    city: str = None,
    extensions: str = "base"
) -> Dict[str, Any]:
    """
    地理编码/逆地理编码工具，支持地址与经纬度之间的相互转换
    
    Args:
        address: 结构化地址信息（地理编码时使用）
        location: 经纬度坐标（逆地理编码时使用）
        city: 指定查询的城市（地理编码时可选）
        extensions: 返回结果控制（base/all）
    """
    return geocode_func(
        address=address,
        location=location,
        city=city,
        extensions=extensions
    )

if __name__ == "__main__":
    app.run(transport="stdio")
