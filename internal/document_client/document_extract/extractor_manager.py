"""
文档提取器管理器
统一管理所有文档提取器，并提供文档处理工具函数
"""
from typing import Dict, List, Optional, Any
from pathlib import Path
import re
from langchain_text_splitters import RecursiveCharacterTextSplitter
from .base_extractor import BaseExtractor
from .extractors import (
    TextExtractor,
    PDFExtractor,
    WordExtractor,
    PowerPointExtractor,
    ExcelExtractor,
    CSVExtractor,
    HTMLExtractor,
    RTFExtractor,
    EPUBExtractor,
    JSONExtractor,
    XMLExtractor
)
from log import logger


class DocumentExtractorManager:
    """文档提取器管理器（单例）"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        """初始化管理器"""
        if self._initialized:
            return
        
        self.extractors: List[BaseExtractor] = []
        self.extension_map: Dict[str, BaseExtractor] = {}
        
        # 注册所有提取器
        self._register_default_extractors()
        
        self._initialized = True
        logger.info(f"✓ 文档提取器管理器初始化完成，支持 {len(self.extension_map)} 种文件格式")
    
    def _register_default_extractors(self):
        """注册默认提取器"""
        default_extractors = [
            TextExtractor(),
            PDFExtractor(),
            WordExtractor(),
            PowerPointExtractor(),
            ExcelExtractor(),
            CSVExtractor(),
            HTMLExtractor(),
            RTFExtractor(),
            EPUBExtractor(),
            JSONExtractor(),
            XMLExtractor()
        ]
        
        for extractor in default_extractors:
            self.register_extractor(extractor)
    
    def register_extractor(self, extractor: BaseExtractor):
        """
        注册提取器
        
        Args:
            extractor: 提取器实例
        """
        self.extractors.append(extractor)
        
        for ext in extractor.supported_extensions:
            self.extension_map[ext] = extractor
        
        logger.debug(f"注册提取器: {extractor.get_name()}, 支持: {extractor.supported_extensions}")
    
    def get_extractor(self, file_path_or_name: str) -> Optional[BaseExtractor]:
        """
        根据文件路径或文件名获取对应的提取器
        
        Args:
            file_path_or_name: 文件路径或文件名
            
        Returns:
            BaseExtractor: 提取器实例，如果不支持则返回 None
        """
        extension = Path(file_path_or_name).suffix.lower()
        return self.extension_map.get(extension)
    
    def is_supported(self, file_path_or_name: str) -> bool:
        """
        检查文件格式是否支持
        
        Args:
            file_path_or_name: 文件路径或文件名
            
        Returns:
            bool: 是否支持
        """
        extension = Path(file_path_or_name).suffix.lower()
        return extension in self.extension_map
    
    def extract_from_file(self, file_path: str) -> str:
        """
        从文件提取内容
        
        Args:
            file_path: 文件路径
            
        Returns:
            str: 提取的文本内容
            
        Raises:
            ValueError: 不支持的文件格式
            FileNotFoundError: 文件不存在
        """
        extractor = self.get_extractor(file_path)
        
        if extractor is None:
            extension = Path(file_path).suffix.lower()
            supported = list(self.extension_map.keys())
            raise ValueError(
                f"不支持的文件格式: {extension}\n"
                f"支持的格式: {', '.join(supported)}"
            )
        
        return extractor.extract_from_file(file_path)
    
    def extract_from_bytes(self, file_bytes: bytes, filename: str) -> str:
        """
        从字节流提取内容
        
        Args:
            file_bytes: 文件字节流
            filename: 文件名（用于确定格式）
            
        Returns:
            str: 提取的文本内容
            
        Raises:
            ValueError: 不支持的文件格式
        """
        extractor = self.get_extractor(filename)
        
        if extractor is None:
            extension = Path(filename).suffix.lower()
            supported = list(self.extension_map.keys())
            raise ValueError(
                f"不支持的文件格式: {extension}\n"
                f"支持的格式: {', '.join(supported)}"
            )
        
        return extractor.extract_from_bytes(file_bytes, filename)
    
    def get_supported_extensions(self) -> List[str]:
        """
        获取所有支持的文件扩展名
        
        Returns:
            List[str]: 扩展名列表
        """
        return sorted(self.extension_map.keys())
    
    def get_extractors_info(self) -> List[Dict[str, any]]:
        """
        获取所有提取器的信息
        
        Returns:
            List[Dict]: 提取器信息列表
        """
        info_list = []
        for extractor in self.extractors:
            info_list.append({
                "name": extractor.get_name(),
                "supported_extensions": extractor.supported_extensions
            })
        return info_list
    
    # ==================== 文档处理工具方法 ====================
    
    def load_document(self, file_path: str) -> List[Dict[str, Any]]:
        """
        加载文档
        
        Args:
            file_path: 文档路径
            
        Returns:
            List[Dict]: 文档内容列表，每个包含 content 和 metadata
        """
        try:
            path = Path(file_path)
            
            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            # 使用提取器提取内容
            content = self.extract_from_file(file_path)
            
            # 转换为标准格式
            result = [{
                "content": content,
                "metadata": {
                    "source": str(path),
                    "filename": path.name,
                    "extension": path.suffix.lower()
                }
            }]
            
            logger.info(f"✓ 文档加载成功: {path.name}, 内容长度: {len(content)}")
            
            return result
            
        except Exception as e:
            logger.error(f"✗ 文档加载失败: {e}", exc_info=True)
            raise
    
    def clean_text(self, text: str) -> str:
        """
        清理文本
        
        Args:
            text: 原始文本
            
        Returns:
            str: 清理后的文本
        """
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text)
        
        # 去除首尾空格
        text = text.strip()
        
        return text
    
    def split_text(
        self,
        text: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        separators: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        分割文本为块
        
        Args:
            text: 文本内容
            chunk_size: 分块大小（字符数）
            chunk_overlap: 分块重叠（字符数）
            separators: 分割符列表（可选）
            metadata: 元数据（可选）
            
        Returns:
            List[Dict]: 文本块列表，每个包含 content 和 metadata
        """
        try:
            # 清理文本
            text = self.clean_text(text)
            
            # 默认分割符（针对中文优化）
            if separators is None:
                separators = [
                    "\n\n",  # 段落
                    "\n",    # 换行
                    "。",    # 句号
                    "！",    # 感叹号
                    "？",    # 问号
                    "；",    # 分号
                    "，",    # 逗号
                    " ",     # 空格
                    ""       # 字符
                ]
            
            # 创建文本分割器
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=separators,
                length_function=len,
            )
            
            # 分割文本
            chunks = text_splitter.split_text(text)
            
            # 构建结果
            result = []
            for i, chunk in enumerate(chunks):
                chunk_data = {
                    "content": chunk,
                    "metadata": {
                        **(metadata or {}),
                        "chunk_index": i,
                        "chunk_count": len(chunks),
                        "chunk_size": len(chunk)
                    }
                }
                result.append(chunk_data)
            
            logger.info(f"✓ 文本分割完成: {len(chunks)} 个块")
            
            return result
            
        except Exception as e:
            logger.error(f"✗ 文本分割失败: {e}", exc_info=True)
            raise
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        获取文件基本信息
        
        Args:
            file_path: 文件路径
            
        Returns:
            Dict: 文件信息（name, size, extension 等）
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        
        return {
            "name": path.name,
            "path": str(path),
            "extension": path.suffix.lower(),
            "size": path.stat().st_size,
            "exists": True
        }


# 便捷函数
def extract_document_content(file_bytes: bytes, filename: str) -> str:
    """
    便捷函数：从字节流提取文档内容
    
    Args:
        file_bytes: 文件字节流
        filename: 文件名
        
    Returns:
        str: 提取的文本内容
    """
    manager = DocumentExtractorManager()
    return manager.extract_from_bytes(file_bytes, filename)


def extract_document_from_file(file_path: str) -> str:
    """
    便捷函数：从文件路径提取文档内容
    
    Args:
        file_path: 文件路径
        
    Returns:
        str: 提取的文本内容
    """
    manager = DocumentExtractorManager()
    return manager.extract_from_file(file_path)


def is_supported_file(file_path_or_name: str) -> bool:
    """
    便捷函数：检查文件格式是否支持
    
    Args:
        file_path_or_name: 文件路径或文件名
        
    Returns:
        bool: 是否支持
    """
    manager = DocumentExtractorManager()
    return manager.is_supported(file_path_or_name)

