"""
文件处理器
负责文件的保存、读取、类型判断
"""
from typing import Optional, Dict, Any
from pathlib import Path as PathlibPath
import os
import uuid as uuid_module

from log import logger
from pkg.constants.constants import SUPPORTED_IMAGE_FORMATS

# 文件上传配置
MESSAGE_FILES_DIR = "uploads/message_files"
os.makedirs(MESSAGE_FILES_DIR, exist_ok=True)


class FileHandler:
    """文件处理器（单例模式）"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def save_file_to_server(self, file_bytes: bytes, original_filename: str) -> str:
        """
        保存文件到服务器，并返回访问 URL
        
        Args:
            file_bytes: 文件字节流
            original_filename: 原始文件名
        
        Returns:
            文件访问 URL（相对路径）
        """
        try:
            # 生成唯一文件名（保留原始扩展名）
            extension = PathlibPath(original_filename).suffix
            saved_filename = f"{uuid_module.uuid4()}{extension}"
            file_path = os.path.join(MESSAGE_FILES_DIR, saved_filename)
            
            # 保存文件
            with open(file_path, "wb") as f:
                f.write(file_bytes)
            
            # 构建访问 URL（相对路径）
            file_url = f"/uploads/message_files/{saved_filename}"
            
            logger.info(f"文件已保存: {file_path} ({len(file_bytes)} 字节) -> URL: {file_url}")
            
            return file_url
            
        except Exception as e:
            logger.error(f"保存文件失败: {original_filename}, error={e}", exc_info=True)
            raise
    
    def is_image_file(self, filename: str) -> bool:
        """
        判断是否为图片文件
        
        Args:
            filename: 文件名
            
        Returns:
            是否为图片文件
        """
        extension = PathlibPath(filename).suffix.lower()
        return extension in SUPPORTED_IMAGE_FORMATS
    
    def get_file_extension(self, filename: str) -> str:
        """
        获取文件扩展名（不含点号）
        
        Args:
            filename: 文件名
            
        Returns:
            扩展名（小写）
        """
        extension = PathlibPath(filename).suffix.lower()
        return extension[1:] if extension else 'file'
    
    def build_extra_data(
        self,
        file_bytes: Optional[bytes],
        file_name: Optional[str],
        file_type: Optional[str],
        file_size: Optional[str],
        file_content: Optional[str],
        location: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """
        构建消息的 extra_data 字段
        
        Args:
            file_bytes: 文件字节流
            file_name: 文件名
            file_type: 文件类型
            file_size: 文件大小
            file_content: 文件解析内容
            location: 位置信息（JSON字符串）
            
        Returns:
            extra_data 字典或 None
        """
        extra_data = None
        
        # 处理文件
        if file_bytes and file_name:
            # 保存文件到服务器
            file_url = self.save_file_to_server(file_bytes, file_name)
            
            extra_data = {
                "file_url": file_url,
                "file_type": file_type,
                "file_name": file_name,
                "file_size": file_size
            }
            
            # 如果有解析内容（文档），也保存到 extra_data
            if file_content:
                extra_data["parsed_content"] = file_content
            
            logger.info(f"用户上传了文件: {file_name}, URL: {file_url}, 有解析内容: {file_content is not None}")
            
        elif file_content:
            # 向后兼容：如果只有 file_content 没有 file_bytes
            extra_data = {
                "file_content": file_content,
                "file_type": file_type,
                "file_name": file_name
            }
            logger.info(f"用户上传了文件（仅内容）: {file_name}, 内容长度: {len(file_content)}")
        
        # 处理位置信息
        if location:
            if extra_data is None:
                extra_data = {}
            try:
                import json
                location_data = json.loads(location)
                extra_data["location"] = location_data
                logger.info(f"用户位置信息已保存: {location_data}")
            except Exception as e:
                logger.warning(f"解析位置信息失败: {e}")
                extra_data["location"] = location  # 保存原始字符串
        
        return extra_data


# 创建单例实例
file_handler = FileHandler()
