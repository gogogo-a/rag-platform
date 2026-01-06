"""
MCP 工具配置
定义所有 MCP 工具的路径和启动参数
"""
import os
from pathlib import Path

# 获取当前文件所在目录
CURRENT_DIR = Path(__file__).parent.absolute()

# Python 解释器路径（使用当前环境）
PYTHON_PATH = os.sys.executable

# MCP 工具配置列表
MCP_TOOLS = [
    {
        "name": "knowledge_search",
        "script": str(CURRENT_DIR / "knowledge_search_mcp.py"),
        "description": "知识库搜索工具"
    },
    {
        "name": "weather_query",
        "script": str(CURRENT_DIR / "weather_query_mcp.py"),
        "description": "天气查询工具"
    },
    {
        "name": "web_search",
        "script": str(CURRENT_DIR / "web_search_mcp.py"),
        "description": "网页搜索工具"
    },
    {
        "name": "email_sender",
        "script": str(CURRENT_DIR / "email_sender_mcp.py"),
        "description": "邮件发送工具"
    },
    {
        "name": "geocode",
        "script": str(CURRENT_DIR / "geocode_mcp.py"),
        "description": "地理编码/逆地理编码工具"
    },
    {
        "name": "ip_location",
        "script": str(CURRENT_DIR / "ip_location_mcp.py"),
        "description": "IP 定位工具"
    },
    {
        "name": "poi_search",
        "script": str(CURRENT_DIR / "poi_search_mcp.py"),
        "description": "POI 地点搜索工具"
    },
    {
        "name": "route_planning",
        "script": str(CURRENT_DIR / "route_planning_mcp.py"),
        "description": "路线规划工具"
    }
]
