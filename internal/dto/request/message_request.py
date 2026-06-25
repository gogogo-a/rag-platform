"""
消息相关请求模型 (RESTful 风格)
"""
from pydantic import BaseModel, Field
from typing import Optional


class SendMessageRequest(BaseModel):
    """发送消息请求 - POST /messages
    
    注意：user_id 从 JWT Token 中自动解析，不需要前端传递
    """
    session_id: Optional[str] = Field(None, description="会话ID（可选，不提供则创建新会话）")
    content: str = Field(..., min_length=1, description="消息内容")
    send_name: Optional[str] = Field(None, description="发送者昵称（可选，不提供则使用token中的昵称）")
    send_avatar: Optional[str] = Field(None, description="发送者头像URL（可选）")
    file_type: Optional[str] = Field(None, description="文件类型（text/image/file）")
    file_name: Optional[str] = Field(None, description="文件名")
    file_size: Optional[str] = Field(None, description="文件大小")
    show_thinking: bool = Field(default=False, description="是否显示思考过程（启用后流式返回）")
    agent_mode: str = Field(default="single", description="Agent 模式：single 或 expert")
