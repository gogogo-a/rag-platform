"""
提示词模板系统
提供可直接导入和点击跳转的提示词

新架构：
- 每个工具都有独立的 prompt 文件
- 所有 prompt 文件位于 pkg/agent_prompt/prompt/ 目录
- 通过此文件保持向后兼容
"""

# 从新的 prompt 模块导入所有提示词
from pkg.agent_prompt.prompt import (
    DEFAULT_PROMPT,
    SUMMARY_PROMPT,
    RAG_PROMPT,
    MULTI_TOOL_PROMPT,
)

# ==================== 向后兼容的别名 ====================
# 保持旧的变量名，方便已有代码使用
AGENT_RAG_PROMPT = RAG_PROMPT


# ==================== 提示词字典（按功能分类）====================

# 基础提示词
BASIC_PROMPTS = {
    "default": DEFAULT_PROMPT,
    "summary": SUMMARY_PROMPT,
}

# Agent 提示词
AGENT_PROMPTS = {
    "rag": RAG_PROMPT,          # 单一工具：知识库搜索
    "multi_tool": MULTI_TOOL_PROMPT,  # 多工具综合 Agent
}

# 完整提示词字典（向后兼容）
PROMPT_TEMPLATES = {
    # 基础提示词
    "default": DEFAULT_PROMPT,
    "summary": SUMMARY_PROMPT,
    
    # Agent 提示词
    "rag": RAG_PROMPT,
    "agent_rag": RAG_PROMPT,  # 向后兼容
    "multi_tool": MULTI_TOOL_PROMPT,
    "agent": MULTI_TOOL_PROMPT,  # 别名
    "multi": MULTI_TOOL_PROMPT,  # 别名
}


# ==================== 工具函数 ====================

def get_prompt(template_name: str = "default") -> str:
    """
    获取提示词模板（向后兼容函数）
    
    Args:
        template_name: 模板名称
            基础: default, summary
            Agent: rag (单工具), multi_tool (多工具)
        
    Returns:
        提示词内容
        
    示例:
        >>> prompt = get_prompt("rag")
        >>> prompt = get_prompt("multi_tool")
    """
    return PROMPT_TEMPLATES.get(template_name, DEFAULT_PROMPT)


def get_agent_prompt(use_multi_tool: bool = True) -> str:
    """
    获取 Agent 提示词
    
    Args:
        use_multi_tool: 是否使用多工具模式
            - True: 返回多工具综合 Agent prompt（推荐）
            - False: 返回单一知识库搜索 prompt
        
    Returns:
        对应的 Agent 提示词
        
    示例:
        >>> prompt = get_agent_prompt(True)   # 多工具模式
        >>> prompt = get_agent_prompt(False)  # 仅知识库搜索
    """
    return MULTI_TOOL_PROMPT if use_multi_tool else RAG_PROMPT


def list_available_prompts() -> dict:
    """
    列出所有可用的提示词
    
    Returns:
        按类别分组的提示词字典
        
    示例:
        >>> prompts = list_available_prompts()
        >>> print(prompts["basic"])  # 基础提示词
        >>> print(prompts["agent"])  # Agent 提示词
    """
    return {
        "basic": list(BASIC_PROMPTS.keys()),
        "agent": list(AGENT_PROMPTS.keys()),
        "all": list(PROMPT_TEMPLATES.keys()),
    }
