"""
邮件服务工具
用于发送验证码邮件
"""
import re
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from pkg.constants.constants import (
    EMAIL_HOST,
    EMAIL_PORT,
    EMAIL_USE_TLS,
    EMAIL_HOST_USER,
    EMAIL_HOST_PASSWORD,
    EMAIL_FROM,
    EMAIL_TIMEOUT,
    EMAIL_VERIFY_SSL,
)
from internal.db.redis import redis_client  # 直接导入全局单例实例


class EmailService:
    """邮件服务类（单例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化邮件服务配置"""
        self.host = EMAIL_HOST
        self.port = EMAIL_PORT
        self.use_tls = EMAIL_USE_TLS
        self.username = EMAIL_HOST_USER
        self.password = EMAIL_HOST_PASSWORD
        self.from_email = EMAIL_FROM
        self.timeout = EMAIL_TIMEOUT
        self.verify_ssl = EMAIL_VERIFY_SSL
        
        # 验证配置
        if not self.username or not self.password:
            raise ValueError("邮件服务配置不完整，请检查 EMAIL_HOST_USER 和 EMAIL_HOST_PASSWORD")
    
    @staticmethod
    def validate_email(email: str) -> bool:
        """
        验证邮箱格式是否合规
        
        Args:
            email: 待验证的邮箱地址
            
        Returns:
            bool: 是否合规
        """
        email_regex = r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$'
        return bool(re.match(email_regex, email))
    
    @staticmethod
    def generate_captcha(length: int = 6) -> str:
        """
        生成数字验证码
        
        Args:
            length: 验证码长度，默认 6 位
            
        Returns:
            str: 生成的验证码
        """
        return "".join(random.sample(string.digits, length))
    
    def send_mail(
        self,
        recipient: str,
        subject: str,
        message: str,
        html_message: Optional[str] = None,
        debug: bool = False
    ) -> bool:
        """
        发送邮件
        
        Args:
            recipient: 收件人邮箱
            subject: 邮件主题
            message: 纯文本邮件内容
            html_message: HTML 格式邮件内容（可选）
            debug: 是否开启调试模式
            
        Returns:
            bool: 发送是否成功
        """
        server = None
        try:
            # 创建邮件对象
            msg = MIMEMultipart('alternative')
            msg['From'] = self.from_email
            msg['To'] = recipient
            msg['Subject'] = subject
            
            # 确保 message 不为空
            if not message or len(message.strip()) == 0:
                if html_message:
                    # 如果有 HTML 但没有纯文本，生成一个简单的备份
                    import re
                    message = re.sub(r'<[^>]+>', '', html_message)
                    message = re.sub(r'\s+', ' ', message).strip()
                    message = message if message else "请在支持 HTML 的邮件客户端中查看此邮件。"
                else:
                    message = "邮件内容为空"
            
            # 添加纯文本内容
            part1 = MIMEText(message, 'plain', 'utf-8')
            msg.attach(part1)
            
            # 如果提供了 HTML 内容，也添加进去
            if html_message and len(html_message.strip()) > 0:
                part2 = MIMEText(html_message, 'html', 'utf-8')
                msg.attach(part2)
            
            if debug:
                print(f"🔍 [邮件调试]")
                print(f"   收件人: {recipient}")
                print(f"   主题: {subject}")
                print(f"   纯文本: {len(message)} 字符")
                print(f"   HTML: {len(html_message) if html_message else 0} 字符")
            
            # 方案 1: 使用 SMTP_SSL (适用于 465 端口)
            if self.port == 465:
                if debug:
                    print(f"   连接方式: SMTP_SSL (端口 465)")
                    print(f"   SSL 证书验证: {'开启' if self.verify_ssl else '关闭'}")
                import ssl
                context = ssl.create_default_context()
                # 根据配置决定是否验证证书
                if not self.verify_ssl:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
                if debug:
                    server.set_debuglevel(1)
                server.login(self.username, self.password)
                server.send_message(msg)
            
            # 方案 2: 使用 SMTP + STARTTLS (适用于 587 或 25 端口)
            else:
                if debug:
                    print(f"   连接方式: SMTP + STARTTLS (端口 {self.port})")
                    print(f"   SSL 证书验证: {'开启' if self.verify_ssl else '关闭'}")
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
                if debug:
                    server.set_debuglevel(1)
                
                # 发送 EHLO
                server.ehlo()
                
                if self.use_tls:
                    # 启用 TLS 加密
                    import ssl
                    context = ssl.create_default_context()
                    
                    # 根据配置决定是否验证证书
                    if not self.verify_ssl:
                        if debug:
                            print(f"   ⚠️  已关闭 SSL 证书验证（适用于开发环境）")
                        context.check_hostname = False
                        context.verify_mode = ssl.CERT_NONE
                    
                    server.starttls(context=context)
                    server.ehlo()  # TLS 后需要再次 EHLO
                
                server.login(self.username, self.password)
                server.send_message(msg)
            
            if server:
                server.quit()
            
            return True
            
        except smtplib.SMTPAuthenticationError as e:
            print(f"❌ SMTP 认证失败: {e}")
            print(f"   提示: 请检查 EMAIL_HOST_USER 和 EMAIL_HOST_PASSWORD 是否正确")
            print(f"   注意: QQ 邮箱需要使用授权码，而不是登录密码")
            return False
        except smtplib.SMTPException as e:
            print(f"❌ SMTP 错误: {e}")
            print(f"   提示: 可能的原因:")
            print(f"   1. SMTP 服务器地址或端口错误")
            print(f"   2. TLS/SSL 配置不正确")
            print(f"   3. 网络连接问题")
            return False
        except Exception as e:
            print(f"❌ 发送邮件失败: {e}")
            print(f"   错误类型: {type(e).__name__}")
            return False
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass
    
    def send_captcha(
        self,
        email: str,
        captcha: Optional[str] = None,
        expire_minutes: int = 5,
        save_to_redis: bool = True,
        debug: bool = False
    ) -> dict:
        """
        发送验证码邮件
        
        Args:
            email: 收件人邮箱
            captcha: 验证码（如果不提供则自动生成）
            expire_minutes: 验证码有效期（分钟）
            save_to_redis: 是否保存到 Redis
            debug: 是否开启调试模式
            
        Returns:
            dict: 包含 success, message, captcha(仅用于测试)
        """
        # 1. 验证邮箱格式
        if not self.validate_email(email):
            return {
                "success": False,
                "message": "邮箱格式不合规，请重新输入",
                "captcha": None
            }
        
        # 2. 生成验证码
        if captcha is None:
            captcha = self.generate_captcha()
        
        # 3. 构建邮件内容
        subject = "验证码通知"
        message = f"您的验证码是: {captcha}\n\n验证码将在 {expire_minutes} 分钟内有效，请尽快使用。\n\n如非本人操作，请忽略此邮件。"
        
        html_message = f"""
        <html>
          <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #333;">验证码通知</h2>
            <p>您的验证码是:</p>
            <h1 style="color: #4CAF50; letter-spacing: 5px; font-size: 36px;">{captcha}</h1>
            <p style="color: #666;">验证码将在 <strong>{expire_minutes}</strong> 分钟内有效，请尽快使用。</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="color: #999; font-size: 12px;">如非本人操作，请忽略此邮件。</p>
          </body>
        </html>
        """
        
        # 4. 发送邮件
        success = self.send_mail(
            recipient=email,
            subject=subject,
            message=message,
            html_message=html_message,
            debug=debug
        )
        
        if not success:
            return {
                "success": False,
                "message": "验证码发送失败，请重新发送",
                "captcha": None
            }
        
        # 5. 保存到 Redis（可选，直接使用全局单例实例）
        if save_to_redis:
            try:
                # 保存验证码，key 为邮箱，value 为验证码，过期时间为指定分钟数
                redis_client.set(
                    key=f"email_captcha:{email}",
                    value=captcha,
                    ex=expire_minutes * 60
                )
                print(f"✓ 验证码已保存到 Redis，key: email_captcha:{email}, 过期时间: {expire_minutes} 分钟")
                
            except Exception as e:
                print(f"⚠️  保存验证码到 Redis 失败: {e}")
                # 不影响邮件发送成功的结果
        
        return {
            "success": True,
            "message": "验证码发送成功",
            "captcha": captcha  # 仅用于测试，生产环境不应返回
        }
    
    def verify_captcha(self, email: str, captcha: str) -> dict:
        """
        验证验证码
        
        Args:
            email: 邮箱地址
            captcha: 用户输入的验证码
            
        Returns:
            dict: 包含 success, message
        """
        try:
            # 从 Redis 获取验证码（直接使用全局单例实例）
            key = f"email_captcha:{email}"
            stored_captcha = redis_client.get(key)
            
            if stored_captcha is None:
                return {
                    "success": False,
                    "message": "验证码已过期或不存在"
                }
            
            # 确保类型一致（Redis 可能返回 bytes 或 str）
            if isinstance(stored_captcha, bytes):
                stored_captcha = stored_captcha.decode('utf-8')
            stored_captcha = str(stored_captcha)
            captcha = str(captcha)
            
            # 验证码匹配
            if stored_captcha == captcha:
                # 验证成功后删除验证码
                redis_client.delete(key)
                return {
                    "success": True,
                    "message": "验证成功"
                }
            else:
                return {
                    "success": False,
                    "message": "验证码错误，请重新输入"
                }
                
        except Exception as e:
            print(f"❌ 验证失败: {e}")
            return {
                "success": False,
                "message": f"验证失败: {str(e)}, 请重新输入"
            }
    
    def get_config_info(self) -> dict:
        """
        获取邮件服务配置信息（隐藏敏感信息）
        
        Returns:
            dict: 配置信息
        """
        return {
            "host": self.host,
            "port": self.port,
            "use_tls": self.use_tls,
            "verify_ssl": self.verify_ssl,
            "username": self.username,
            "password": "***" + self.password[-4:] if len(self.password) > 4 else "***",
            "from_email": self.from_email,
            "timeout": self.timeout
        }


# 创建单例实例
email_service = EmailService()

