"""
路线规划 MCP 工具
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from mcp.server import FastMCP
from typing import Dict, Any
from pkg.agent_tools.route_planning import route_planning as route_planning_func

app = FastMCP("route_planning")

@app.tool()
def route_planning(
    origin: str,
    destination: str,
    mode: str = "driving",
    strategy: int = None,
    waypoints: str = None,
    city1: str = None,
    city2: str = None
) -> Dict[str, Any]:
    """
    路线规划工具，支持驾车、步行、骑行、电动车、公交等多种出行方式
    
    Args:
        origin: 起点坐标，格式：'经度,纬度'
        destination: 终点坐标，格式：'经度,纬度'
        mode: 出行方式（driving/walking/bicycling/electrobike/transit）
        strategy: 路线策略
        waypoints: 途经点（仅驾车有效）
        city1: 起点城市代码（仅公交必填）
        city2: 终点城市代码（仅公交必填）
    """
    return route_planning_func(
        origin=origin,
        destination=destination,
        mode=mode,
        strategy=strategy,
        waypoints=waypoints,
        city1=city1,
        city2=city2
    )

if __name__ == "__main__":
    app.run(transport="stdio")
