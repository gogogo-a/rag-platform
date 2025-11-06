"""
Agent 工具系统
提供统一的工具管理和权限控制
"""

# 导出基础类
from pkg.agent_tools.base_tool import AgentTool

# 导出所有工具函数
from pkg.agent_tools.knowledge_search import knowledge_search
from pkg.agent_tools.web_search import web_search
from pkg.agent_tools.weather_query import weather_query
from pkg.agent_tools.route_planning import route_planning
from pkg.agent_tools.ip_location import ip_location
from pkg.agent_tools.email_sender import email_sender
from pkg.agent_tools.poi_search import poi_search
from pkg.agent_tools.geocode import geocode

# 导出工具管理器函数
from pkg.agent_tools.tool_manager import (
    ALL_TOOLS,
    check_tool_permission,
    filter_tools_by_permission,
    get_tool_info,
    get_tools_info,
    list_all_tools,
    get_prompt_for_tools,
    get_available_tools,  # 主入口
)

__all__ = [
    # 基础类
    "AgentTool",
    
    # 工具函数
    "knowledge_search",
    "web_search",
    "weather_query",
    "route_planning",
    "ip_location",
    "email_sender",
    "poi_search",
    "geocode",
    
    # 工具管理
    "ALL_TOOLS",
    "check_tool_permission",
    "filter_tools_by_permission",
    "get_tool_info",
    "get_tools_info",
    "list_all_tools",
    "get_prompt_for_tools",
    "get_available_tools",  # 最重要的统一入口
]

