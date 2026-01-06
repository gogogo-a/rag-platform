"""
邮件发送工具 - FastMCP 版本
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from mcp.server import FastMCP
from typing import Dict, Any, Optional

app = FastMCP("email_sender")


@app.tool()
def email_sender(
    to_email: str,
    subject: str = "来自 AI 助手的消息",
    content: Optional[str] = None,
    html_content: Optional[str] = None,
    send_captcha: bool = False
) -> Dict[str, Any]:
    """
    邮件发送工具（需要管理员权限）
    
    Args:
        to_email: 收件人邮箱
        subject: 邮件主题
        content: 纯文本内容
        html_content: HTML 内容
        send_captcha: 是否发送验证码
        
    Returns:
        Dict: 发送结果
    """
    try:
        from pkg.utils.email_service import email_service
        import re
        
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, to_email):
            return {
                "success": False,
                "summary": f"邮箱格式无效: {to_email}"
            }
        
        if send_captcha:
            result = email_service.send_captcha(
                email=to_email,
                expire_minutes=5,
                save_to_redis=True
            )
            if result["success"]:
                return {
                    "success": True,
                    "summary": f"验证码已发送到 {to_email}，有效期 5 分钟"
                }
            else:
                return {
                    "success": False,
                    "summary": result.get("message", "发送失败")
                }
        else:
            if not content and not html_content:
                return {
                    "success": False,
                    "summary": "必须提供邮件内容"
                }
            
            if not content and html_content:
                content = re.sub(r'<[^>]+>', '', html_content).strip()
            
            success = email_service.send_mail(
                recipient=to_email,
                subject=subject,
                message=content,
                html_message=html_content,
                debug=False
            )
            
            if success:
                return {
                    "success": True,
                    "summary": f"邮件已成功发送到 {to_email}"
                }
            else:
                return {
                    "success": False,
                    "summary": "邮件发送失败"
                }
        
    except Exception as e:
        return {
            "success": False,
            "summary": f"发送失败: {str(e)}"
        }


if __name__ == "__main__":
    app.run(transport="stdio")
