"""
MCP 工具管理器
负责启动和管理所有 MCP 服务连接
"""
import asyncio
import os
import logging
from typing import List, Dict, Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .mcp_config import MCP_TOOLS, PYTHON_PATH

logger = logging.getLogger(__name__)


class MCPManager:
    """MCP 工具管理器"""
    
    def __init__(self):
        self.clients = []
        self.sessions = []
        self.tools = []  # LangChain Tool 对象列表
        self.tool_map = {}  # {tool_name: tool_function}
        self.mcp_tools = []  # 原始 MCP 工具列表
    
    async def start_all(self):
        """启动所有 MCP 服务"""
        for i, tool_config in enumerate(MCP_TOOLS):
            # 创建服务器参数
            server_params = StdioServerParameters(
                command=PYTHON_PATH,
                args=[tool_config["script"]],
                env=dict(os.environ),
                cwd=os.getcwd(),
            )
            
            # 启动客户端
            client = stdio_client(server_params)
            read, write = await client.__aenter__()
            
            # 创建会话
            session = ClientSession(read, write)
            await session.__aenter__()
            
            # 🔥 添加超时保护
            try:
                await asyncio.wait_for(session.initialize(), timeout=10.0)
                logger.info(f"✓ {tool_config['name']} 初始化成功")
            except asyncio.TimeoutError:
                logger.error(f"✗ {tool_config['name']} 初始化超时（10秒）")
                raise
            
            # 获取 MCP 工具列表
            tools_list = await session.list_tools()
            
            # 为每个工具创建包装函数
            for mcp_tool in tools_list.tools:
                tool_name = mcp_tool.name
                
                # 创建异步包装函数
                def make_async_wrapper(sess, tname):
                    async def async_tool(tool_input=None, **kwargs):
                        import json
                        
                        # LangChain 可能传递 tool_input 字符串或 kwargs
                        if isinstance(tool_input, str):
                            # 尝试解析 JSON 字符串
                            try:
                                parsed = json.loads(tool_input.strip())
                                if isinstance(parsed, dict):
                                    kwargs = parsed
                                else:
                                    kwargs = {"query": tool_input}
                            except json.JSONDecodeError:
                                # 不是 JSON，作为普通字符串
                                kwargs = {"query": tool_input}
                        elif isinstance(tool_input, dict):
                            # 字典输入，合并到 kwargs
                            kwargs.update(tool_input)
                        elif tool_input is None and not kwargs:
                            kwargs = {}
                        
                        try:
                            result = await sess.call_tool(tname, arguments=kwargs)
                            
                            if hasattr(result, 'content') and result.content:
                                # MCP 返回的是 CallToolResult，包含 content 列表
                                text = result.content[0].text if result.content else ""
                                # 🔥 直接返回原始文本（可能是 JSON），让 react_agent 处理
                                return text
                            return str(result)
                        except Exception as e:
                            logger.error(f"MCP 工具调用失败: {tname}: {e}", exc_info=True)
                            return f"工具调用失败: {str(e)}"
                    return async_tool
                
                async_func = make_async_wrapper(session, tool_name)
                
                # 转换为 LangChain Tool（使用 coroutine）
                from langchain_core.tools import Tool
                langchain_tool = Tool(
                    name=tool_name,
                    func=lambda *args, **kwargs: "请使用 coroutine 调用",  # 占位
                    coroutine=async_func,  # 异步函数
                    description=mcp_tool.description or f"MCP 工具: {tool_name}"
                )
                
                self.tools.append(langchain_tool)
                self.tool_map[tool_name] = langchain_tool
                self.mcp_tools.append(mcp_tool)
            
            # 保存连接
            self.clients.append(client)
            self.sessions.append(session)
            
        logger.info(f"MCP 工具服务已启动，共加载 {len(self.tools)} 个工具")
        
        return self.tools, self.tool_map
    
    async def stop_all(self):
        """停止所有 MCP 服务"""
        for i, (session, client) in enumerate(zip(self.sessions, self.clients)):
            if session:
                await session.__aexit__(None, None, None)
            if client:
                await client.__aexit__(None, None, None)
        logger.info("MCP 工具服务已关闭")
    
    def get_tools(self) -> List[Any]:
        """获取所有工具列表"""
        return self.tools
    
    def get_tool_map(self) -> Dict[str, Any]:
        """获取工具映射字典"""
        return self.tool_map


# 全局单例
mcp_manager = MCPManager()
