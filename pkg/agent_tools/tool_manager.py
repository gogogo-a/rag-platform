"""
Agent 工具管理器
统一管理所有 AI 工具，提供权限过滤和参数绑定
"""
from typing import Dict, List, Callable, Any

# 导入所有工具
from pkg.agent_tools.knowledge_search import knowledge_search
from pkg.agent_tools.web_search import web_search
from pkg.agent_tools.weather_query import weather_query
from pkg.agent_tools.route_planning import route_planning
from pkg.agent_tools.ip_location import ip_location
from pkg.agent_tools.email_sender import email_sender
from pkg.agent_tools.poi_search import poi_search
from pkg.agent_tools.geocode import geocode


# ==================== 所有可用工具列表 ====================

ALL_TOOLS = [
    knowledge_search,
    web_search,
    weather_query,
    route_planning,
    ip_location,
    email_sender,
    poi_search,
    geocode,
]


# ==================== 工具权限管理 ====================

def check_tool_permission(tool_func: Callable, is_admin: bool = False) -> bool:
    """
    检查工具使用权限
    
    Args:
        tool_func: 工具函数
        is_admin: 用户是否为管理员
        
    Returns:
        是否有权限使用该工具
    """
    # 获取工具的权限要求（默认所有用户可用）
    requires_admin = getattr(tool_func, "is_admin", False)
    
    # 如果工具不需要管理员权限，所有用户都可用
    if not requires_admin:
        return True
    
    # 如果工具需要管理员权限，检查用户是否为管理员
    return is_admin


def filter_tools_by_permission(tools: Dict[str, Callable], is_admin: bool = False) -> Dict[str, Callable]:
    """
    根据用户权限过滤可用工具
    
    Args:
        tools: 所有工具字典
        is_admin: 用户是否为管理员
        
    Returns:
        用户可用的工具字典
    """
    filtered_tools = {}
    
    for name, tool_func in tools.items():
        if check_tool_permission(tool_func, is_admin):
            filtered_tools[name] = tool_func
        else:
            print(f"[权限] 工具 '{name}' 需要管理员权限，已过滤")
    
    return filtered_tools


# ==================== 工具信息获取 ====================

def get_tool_info(tool_func: Callable) -> Dict:
    """
    获取工具信息
    
    Args:
        tool_func: 工具函数
        
    Returns:
        工具信息字典
    """
    return {
        "name": tool_func.__name__,
        "description": getattr(tool_func, "description", tool_func.__doc__ or "无描述"),
        "prompt_template": getattr(tool_func, "prompt_template", "default"),
        "is_admin": getattr(tool_func, "is_admin", False)
    }


def get_tools_info(tools: List[Callable]) -> List[Dict]:
    """
    批量获取工具信息
    
    Args:
        tools: 工具函数列表
        
    Returns:
        工具信息列表
    """
    return [get_tool_info(tool) for tool in tools]


def list_all_tools() -> List[Dict]:
    """列出所有可用工具的信息"""
    return get_tools_info(ALL_TOOLS)


def get_prompt_for_tools(tools: List[Callable]) -> str:
    """
    根据工具列表获取合适的提示词模板
    
    Args:
        tools: 工具函数列表
        
    Returns:
        提示词模板名称
    """
    if not tools:
        return "default"
    
    # 返回第一个工具的提示词模板
    first_tool = tools[0]
    return getattr(first_tool, "prompt_template", "default")


# ==================== 工具获取（主入口）====================

def get_available_tools(is_admin: bool = False, user_permission: int = 0) -> Dict[str, Callable]:
    """
    获取用户可用的工具字典（自动处理权限过滤和参数绑定）
    
    这是工具层的统一入口，Service 层只需要调用这个函数即可获得：
    1. 根据用户权限过滤后的工具列表
    2. 自动绑定了必要参数的工具函数（如 user_permission）
    
    Args:
        is_admin: 用户是否为管理员
        user_permission: 用户权限值（0=普通用户，1=管理员）
        
    Returns:
        工具名称到函数的映射字典，可直接传递给 Agent
        
    示例:
        ```python
        # Service 层代码
        tools = get_available_tools(is_admin=user.is_admin, user_permission=user.is_admin)
        agent = ReActAgent(llm_service, tools=tools)
        ```
    """
    # 1. 根据权限过滤工具
    all_tools_dict = {tool.__name__: tool for tool in ALL_TOOLS}
    filtered_tools = filter_tools_by_permission(all_tools_dict, is_admin)
    
    # 2. 为需要权限参数的工具创建包装函数
    wrapped_tools = {}
    
    for tool_name, tool_func in filtered_tools.items():
        if tool_name == "knowledge_search":
            # knowledge_search 需要绑定 user_permission 参数
            def knowledge_search_wrapper(query: str, top_k: int = 5, use_reranker: bool = True):
                """知识库搜索工具（已绑定用户权限）"""
                return knowledge_search(query=query, top_k=top_k, use_reranker=use_reranker, user_permission=user_permission)
            
            # 保留原始函数的元信息
            knowledge_search_wrapper.__name__ = "knowledge_search"
            knowledge_search_wrapper.__doc__ = knowledge_search.__doc__
            knowledge_search_wrapper.description = getattr(knowledge_search, "description", "")
            knowledge_search_wrapper.prompt_template = getattr(knowledge_search, "prompt_template", "default")
            knowledge_search_wrapper.is_admin = getattr(knowledge_search, "is_admin", False)
            
            wrapped_tools[tool_name] = knowledge_search_wrapper
            
        else:
            # 其他工具直接使用（如 web_search 不需要额外参数）
            wrapped_tools[tool_name] = tool_func
    
    print(f"[工具层] 为用户准备了 {len(wrapped_tools)} 个可用工具: {list(wrapped_tools.keys())}")
    
    return wrapped_tools

