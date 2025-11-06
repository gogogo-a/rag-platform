"""
邮件发送工具
发送各种格式的邮件通知、验证码等（需要管理员权限）
"""
from typing import Dict, Any, Optional
import re


def email_sender(
    to_email: str,
    subject: str = "来自 AI 助手的消息",
    content: Optional[str] = None,
    html_content: Optional[str] = None,
    send_captcha: bool = False
) -> Dict[str, Any]:
    """
    邮件发送工具
    发送各种格式的邮件，支持纯文本、HTML 富文本或验证码（需要管理员权限）
    
    Args:
        to_email: 收件人邮箱地址
        subject: 邮件主题（默认："来自 AI 助手的消息"）
        content: 邮件纯文本内容
            - 支持多行文本，可以包含换行符
            - 如果同时提供 html_content，则作为备用纯文本版本
            - 如果 send_captcha=True，则忽略此参数
        html_content: 邮件 HTML 内容（可选）
            - 支持完整的 HTML 格式，包括样式、链接、图片等
            - 可以创建美观的富文本邮件
            - 如果提供，邮件客户端会优先显示 HTML 版本
        send_captcha: 是否发送验证码邮件（默认：False）
            - True: 发送系统验证码邮件（自动生成验证码，忽略 content 和 html_content）
            - False: 发送自定义内容邮件
        
    Returns:
        Dict: 发送结果
            - success: 是否成功
            - message: 结果消息
            - captcha: 验证码（仅当 send_captcha=True 时返回）
            
    示例:
        # 发送纯文本邮件
        result = email_sender(
            to_email="user@example.com",
            subject="系统通知",
            content="您好！您的账户余额不足，请及时充值。"
        )
        
        # 发送 HTML 富文本邮件
        result = email_sender(
            to_email="user@example.com",
            subject="活动通知",
            content="活动详情...",
            html_content="<h1>限时优惠</h1><p>全场<strong>8折</strong>！</p>"
        )
        
        # 发送验证码邮件（系统专用）
        result = email_sender(
            to_email="user@example.com",
            send_captcha=True
        )
    
    注意:
        - 此工具需要管理员权限
        - 请勿频繁发送邮件，避免被标记为垃圾邮件
        - 验证码有效期为 5 分钟
        - HTML 内容请确保格式正确，避免被邮件客户端过滤
    """
    try:
        # 延迟导入，避免循环依赖
        from pkg.utils.email_service import email_service
        
        # 验证邮箱格式
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, to_email):
            print(f"[工具] ⚠️ 邮箱格式无效: {to_email}")
            return {
                "success": False,
                "message": f"邮箱格式无效: {to_email}",
                "captcha": None
            }
        
        if send_captcha:
            # 发送验证码邮件
            print(f"[工具] 发送验证码邮件: {to_email}")
            
            result = email_service.send_captcha(
                email=to_email,
                expire_minutes=5,
                save_to_redis=True
            )
            
            if result["success"]:
                print(f"[工具] 验证码邮件发送成功: {to_email}")
                return {
                    "success": True,
                    "message": f"验证码已发送到 {to_email}，有效期 5 分钟",
                    "captcha": result.get("captcha", "")  # 返回验证码（仅用于日志）
                }
            else:
                print(f"[工具] 验证码邮件发送失败: {result.get('message', '未知错误')}")
                return {
                    "success": False,
                    "message": result.get("message", "发送失败"),
                    "captcha": None
                }
        
        else:
            # 发送自定义内容邮件
            if not content and not html_content:
                return {
                    "success": False,
                    "message": "发送邮件时必须提供邮件内容（content 或 html_content 参数）",
                    "captcha": None
                }
            
            # 如果没有提供纯文本内容，但提供了 HTML，则生成简单的纯文本版本
            if not content and html_content:
                # 简单地去除 HTML 标签作为纯文本备份
                content = re.sub(r'<[^>]+>', '', html_content)
                content = content.strip()
            
            # 调用邮件服务发送自定义邮件
            success = email_service.send_mail(
                recipient=to_email,
                subject=subject,
                message=content,
                html_message=html_content,
                debug=False  # 关闭调试模式（避免日志过多）
            )
            
            if success:
                return {
                    "success": True,
                    "message": f"邮件已成功发送到 {to_email}",
                    "captcha": None
                }
            else:
                print(f"[工具] 邮件发送失败")
                return {
                    "success": False,
                    "message": "邮件发送失败，请检查邮件服务配置或网络连接",
                    "captcha": None
                }
        
    except ImportError as e:
        print(f"[工具] 导入邮件服务失败: {e}")
        return {
            "success": False,
            "message": "邮件服务未配置或导入失败",
            "captcha": None
        }
    except Exception as e:
        print(f"[工具] 发送邮件失败: {e}")
        return {
            "success": False,
            "message": f"发送失败: {str(e)}",
            "captcha": None
        }


# 工具元信息
email_sender.prompt_template = "default"
email_sender.description = """邮件发送工具，支持发送纯文本邮件、HTML 富文本邮件和验证码邮件。
可用于发送各种内容：通知、提醒、报告、活动信息、验证码等。
支持 HTML 格式，可以发送带有样式、表格、链接等的美观邮件。
注意：此工具需要管理员权限，请谨慎使用，避免频繁发送造成垃圾邮件"""
email_sender.is_admin = True  # 需要管理员权限

