"""
IP 定位 MCP 工具
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from mcp.server import FastMCP
from typing import Dict, Any
from pkg.agent_tools.ip_location import ip_location as ip_location_func

app = FastMCP("ip_location")

@app.tool()
def ip_location(ip: str = None) -> Dict[str, Any]:
    """
    IP 定位工具，将 IP 地址转换为地理位置信息
    
    Args:
        ip: IP 地址（可选），如果不提供则自动获取客户端 IP
    """
    return ip_location_func(ip=ip)

if __name__ == "__main__":
    app.run(transport="stdio")
