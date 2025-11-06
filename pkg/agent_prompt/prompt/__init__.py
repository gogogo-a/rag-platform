"""
AI Agent 提示词模块
提供统一的多工具 Agent 提示词
"""

# 导入基础提示词
from pkg.agent_prompt.prompt.default_prompt import DEFAULT_PROMPT
from pkg.agent_prompt.prompt.summary_prompt import SUMMARY_PROMPT
from pkg.agent_prompt.prompt.rag_prompt import RAG_PROMPT

# 导入多工具综合提示词
from pkg.agent_prompt.prompt.multi_tool_prompt import MULTI_TOOL_PROMPT

__all__ = [
    "DEFAULT_PROMPT",
    "SUMMARY_PROMPT",
    "RAG_PROMPT",
    "MULTI_TOOL_PROMPT",
]

