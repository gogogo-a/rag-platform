"""
MCP 工具包
提供 FastMCP 封装的所有工具
"""
from .mcp_manager import mcp_manager, MCPManager
from .mcp_config import MCP_TOOLS

__all__ = [
    "mcp_manager",
    "MCPManager",
    "MCP_TOOLS"
]
