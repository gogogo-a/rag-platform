"""
用户信息服务
"""
from typing import Tuple, Optional, List, Dict, Any
from internal.model.user_info import UserInfoModel
from internal.dto.request import (
    RegisterRequest,
    LoginRequest,
    EmailLoginRequest,
    UpdateUserInfoRequest
)
from internal.dto.respond import UserInfoResponse
from pkg.utils import hash_password, verify_password, create_token
from pkg.utils.email_service import email_service
from log import logger
import uuid


class UserInfoService:
    """用户信息服务类（单例）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def register(self, req: RegisterRequest) -> Tuple[str, Optional[UserInfoResponse], int]:
        """
        注册用户
        
        Returns:
            Tuple[str, Optional[UserInfoResponse], int]: (消息, 用户信息, 返回码)
        """
        try:
            # 1. 检查两次密码是否一致
            if req.password != req.confirm_password:
                logger.warning(f"注册失败: 两次密码不一致 - {req.nickname}")
                return "两次密码不一致", None, -2
            
            # 2. 验证邮箱验证码
            verify_result = email_service.verify_captcha(req.email, req.captcha)
            if not verify_result["success"]:
                logger.warning(f"注册失败: 验证码验证失败 - {req.email}, {verify_result['message']}")
                return verify_result["message"], None, -2
            
            # 3. 检查昵称是否存在
            existing_user = await UserInfoModel.find_one(UserInfoModel.nickname == req.nickname)
            if existing_user:
                logger.warning(f"注册失败: 昵称已存在 - {req.nickname}")
                return "昵称已存在", None, -2
            
            # 4. 检查邮箱是否存在
            existing_email = await UserInfoModel.find_one(UserInfoModel.email == req.email)
            if existing_email:
                logger.warning(f"注册失败: 邮箱已存在 - {req.email}")
                return "邮箱已存在", None, -2
            
            # 5. 创建用户
            user = UserInfoModel(
                uuid=str(uuid.uuid4()),
                nickname=req.nickname,
                password=hash_password(req.password),
                email=req.email
            )
            
            await user.insert()
            logger.info(f"用户注册成功: {user.nickname} ({user.uuid})")
            
            # 6. 生成 token（包含管理员标识）
            token_data = {
                "user_id": user.uuid,
                "nickname": user.nickname,
                "is_admin": user.is_admin
            }
            token = create_token(token_data)
            
            response = UserInfoResponse.from_orm(user)
            response.token = token
            
            return "注册成功", response, 0
            
        except Exception as e:
            logger.error(f"注册失败: {str(e)}", exc_info=True)
            return f"注册失败: {str(e)}", None, -1
    
    async def login(self, req: LoginRequest) -> Tuple[str, Optional[UserInfoResponse], int]:
        """
        用户登录（昵称+密码）
        
        Returns:
            Tuple[str, Optional[UserInfoResponse], int]: (消息, 用户信息, 返回码)
        """
        try:
            # 查找用户（通过昵称）
            user = await UserInfoModel.find_one(UserInfoModel.nickname == req.nickname)
            if not user:
                logger.warning(f"登录失败: 用户不存在 - {req.nickname}")
                return "昵称或密码错误", None, -2
            
            # 验证密码
            if not verify_password(req.password, user.password):
                logger.warning(f"登录失败: 密码错误 - {req.nickname}")
                return "昵称或密码错误", None, -2
            
            # 生成 token（包含管理员标识）
            token_data = {
                "user_id": user.uuid,
                "nickname": user.nickname,
                "is_admin": user.is_admin
            }
            token = create_token(token_data)
            
            logger.info(f"用户登录成功: {user.nickname} ({user.uuid})")
            
            response = UserInfoResponse.from_orm(user)
            response.token = token
            
            return "登录成功", response, 0
            
        except Exception as e:
            logger.error(f"登录失败: {str(e)}", exc_info=True)
            return f"登录失败: {str(e)}", None, -1
    
    async def email_login(self, req: EmailLoginRequest) -> Tuple[str, Optional[UserInfoResponse], int]:
        """
        邮箱验证码登录
        
        Returns:
            Tuple[str, Optional[UserInfoResponse], int]: (消息, 用户信息, 返回码)
        """
        try:
            # 验证邮箱验证码
            verify_result = email_service.verify_captcha(req.email, req.captcha)
            if not verify_result["success"]:
                logger.warning(f"邮箱登录失败: 验证码验证失败 - {req.email}, {verify_result['message']}")
                return verify_result["message"], None, -2
            
            # 查找用户（通过邮箱）
            user = await UserInfoModel.find_one(UserInfoModel.email == req.email)
            if not user:
                logger.warning(f"邮箱登录失败: 用户不存在 - {req.email}")
                return "该邮箱未注册", None, -2
            
            # 生成 token（包含管理员标识）
            token_data = {
                "user_id": user.uuid,
                "nickname": user.nickname,
                "is_admin": user.is_admin
            }
            token = create_token(token_data)
            
            logger.info(f"用户邮箱登录成功: {user.nickname} ({user.uuid})")
            
            response = UserInfoResponse.from_orm(user)
            response.token = token
            
            return "登录成功", response, 0
            
        except Exception as e:
            logger.error(f"邮箱登录失败: {str(e)}", exc_info=True)
            return f"登录失败: {str(e)}", None, -1
    
    async def get_user_info(self, user_uuid: str) -> Tuple[str, Optional[UserInfoResponse], int]:
        """
        获取用户信息
        
        Returns:
            Tuple[str, Optional[UserInfoResponse], int]: (消息, 用户信息, 返回码)
        """
        try:
            user = await UserInfoModel.find_one(UserInfoModel.uuid == user_uuid)
            if not user:
                logger.warning(f"获取用户信息失败: 用户不存在 - {user_uuid}")
                return "用户不存在", None, -2
            
            response = UserInfoResponse.from_orm(user)
            logger.info(f"获取用户信息成功: {user.nickname} ({user.uuid})")
            
            return "获取成功", response, 0
            
        except Exception as e:
            logger.error(f"获取用户信息失败: {str(e)}", exc_info=True)
            return f"获取失败: {str(e)}", None, -1
    
    async def update_user_info(self, req: UpdateUserInfoRequest) -> Tuple[str, int]:
        """
        更新用户信息
        
        Returns:
            Tuple[str, int]: (消息, 返回码)
        """
        try:
            user = await UserInfoModel.find_one(UserInfoModel.uuid == req.uuid)
            if not user:
                logger.warning(f"更新用户信息失败: 用户不存在 - {req.uuid}")
                return "用户不存在", -2
            
            # 更新字段
            if req.nickname:
                user.nickname = req.nickname
            if req.email:
                user.email = req.email
            if req.avatar:
                user.avatar = req.avatar
            if req.gender is not None:
                user.gender = req.gender
            if req.birthday:
                user.birthday = req.birthday
            
            await user.save()
            logger.info(f"用户信息更新成功: {user.nickname} ({user.uuid})")
            
            return "更新成功", 0
            
        except Exception as e:
            logger.error(f"更新用户信息失败: {str(e)}", exc_info=True)
            return f"更新失败: {str(e)}", -1
    
    async def get_user_info_list(self, owner_id: Optional[str], page: int = 1, page_size: int = 10) -> Tuple[str, List[Dict[str, Any]], int]:
        """
        获取用户列表
        
        Returns:
            Tuple[str, List[Dict], int]: (消息, 用户列表, 返回码)
        """
        try:
            skip = (page - 1) * page_size
            
            if owner_id:
                users = (
                    await UserInfoModel.find(UserInfoModel.uuid == owner_id)
                    .sort(-UserInfoModel.created_at)
                    .skip(skip)
                    .limit(page_size)
                    .to_list()
                )
            else:
                users = (
                    await UserInfoModel.find_all()
                    .sort(-UserInfoModel.created_at)
                    .skip(skip)
                    .limit(page_size)
                    .to_list()
                )
            
            user_list = []
            for user in users:
                row = UserInfoResponse.from_orm(user).model_dump(mode='json')
                row["create_at"] = row.get("created_at")
                user_list.append(row)
            logger.info(f"获取用户列表成功: 共 {len(user_list)} 条")
            
            return "获取成功", user_list, 0
            
        except Exception as e:
            logger.error(f"获取用户列表失败: {str(e)}", exc_info=True)
            return f"获取失败: {str(e)}", [], -1
    
    async def delete_users(self, uuid_list: List[str]) -> Tuple[str, int]:
        """
        批量删除用户
        
        Returns:
            Tuple[str, int]: (消息, 返回码)
        """
        try:
            for user_uuid in uuid_list:
                user = await UserInfoModel.find_one(UserInfoModel.uuid == user_uuid)
                if user:
                    await user.delete()
            
            logger.info(f"批量删除用户成功: {len(uuid_list)} 个")
            return f"删除成功: {len(uuid_list)} 个用户", 0
            
        except Exception as e:
            logger.error(f"批量删除用户失败: {str(e)}", exc_info=True)
            return f"删除失败: {str(e)}", -1
    
    async def set_admin(self, uuid_list: List[str], is_admin: bool) -> Tuple[str, int]:
        """
        批量设置管理员
        
        Returns:
            Tuple[str, int]: (消息, 返回码)
        """
        try:
            for user_uuid in uuid_list:
                user = await UserInfoModel.find_one(UserInfoModel.uuid == user_uuid)
                if user:
                    user.is_admin = is_admin
                    await user.save()
            
            action = "设置" if is_admin else "取消"
            logger.info(f"{action}管理员成功: {len(uuid_list)} 个")
            return f"{action}管理员成功: {len(uuid_list)} 个用户", 0
            
        except Exception as e:
            logger.error(f"设置管理员失败: {str(e)}", exc_info=True)
            return f"设置失败: {str(e)}", -1
    
    def send_email_code(self, email: str) -> Tuple[str, int]:
        """
        发送邮箱验证码
        
        Returns:
            Tuple[str, int]: (消息, 返回码)
        """
        try:
            # 调用邮件服务发送验证码
            result = email_service.send_captcha(
                email=email,
                expire_minutes=5,
                save_to_redis=True
            )
            
            if result["success"]:
                logger.info(f"邮箱验证码已发送: {email}")
                return "验证码发送成功", 0
            else:
                logger.warning(f"发送验证码失败: {email} - {result['message']}")
                return result["message"], -2
            
        except Exception as e:
            logger.error(f"发送验证码失败: {str(e)}", exc_info=True)
            return f"发送失败: {str(e)}", -1


# 创建单例实例
user_info_service = UserInfoService()
