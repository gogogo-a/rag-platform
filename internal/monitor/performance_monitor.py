"""
性能监控模块

提供装饰器和工具来监控关键操作的执行时间
监控数据按天、按类型保存到 json_monitor/ 目录

监控类型：
- embedding: Embedding 向量化操作
- vector_search: 向量检索
- llm_think: LLM 思考过程
- llm_action: LLM 动作执行
- llm_answer: LLM 答案生成
- llm_total: LLM 完整对话
- agent_total: Agent 完整推理
"""

import time
import json
import asyncio
from pathlib import Path
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, Optional
from log import logger


class PerformanceMonitor:
    """性能监控管理器"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 监控数据保存目录
        project_root = Path(__file__).parent.parent.parent
        self.monitor_dir = project_root / "json_monitor"
        self.monitor_dir.mkdir(exist_ok=True)
        
        self._initialized = True
        logger.info(f"性能监控系统已初始化，监控目录: {self.monitor_dir}")
    
    def _get_file_path(self, monitor_type: str) -> Path:
        """
        获取监控数据文件路径
        
        格式: json_monitor/YY_MM_DD_monitor/{type}.json
        例如: json_monitor/25_10_26_monitor/embedding.json
        
        Args:
            monitor_type: 监控类型（embedding, vector_search, llm_think 等）
        
        Returns:
            Path: 文件路径
        """
        # 使用和 json_log 相同的日期格式：YY_MM_DD_monitor
        today_dir = datetime.now().strftime("%y_%m_%d_monitor")
        monitor_subdir = self.monitor_dir / today_dir
        
        # 确保目录存在
        monitor_subdir.mkdir(exist_ok=True)
        
        # 文件名：{type}.json
        filename = f"{monitor_type}.json"
        return monitor_subdir / filename
    
    def record(
        self, 
        monitor_type: str,
        operation: str,
        duration: float,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        记录性能数据到 JSON 文件
        
        Args:
            monitor_type: 监控类型
            operation: 操作名称
            duration: 执行时间（秒）
            metadata: 额外的元数据（如输入大小、输出大小等）
                     - token_count: token 数量（用于计算 tokens/s）
        """
        try:
            file_path = self._get_file_path(monitor_type)
            
            # 构建监控记录
            record = {
                "timestamp": datetime.now().isoformat(),
                "operation": operation,
                "duration_ms": round(duration * 1000, 2),  # 转换为毫秒
                "duration_s": round(duration, 4),  # 保留秒
            }
            
            # 添加元数据
            if metadata:
                # 🔥 如果metadata中有 'text' 字段，自动计算 token_count
                if "text" in metadata and "token_count" not in metadata:
                    text = metadata["text"]
                    token_count = _estimate_token_count(text)
                    if token_count > 0:
                        metadata["token_count"] = token_count
                
                record["metadata"] = metadata
                
                # 🔥 如果有 token_count，自动计算 token 处理速度
                if "token_count" in metadata and metadata["token_count"] > 0:
                    token_count = metadata["token_count"]
                    
                    # 计算 tokens/s
                    if duration > 0:
                        tokens_per_second = round(token_count / duration, 2)
                        record["tokens_per_second"] = tokens_per_second
                        
                        # 计算每 10000 tokens 的处理时间（毫秒）
                        ms_per_10k_tokens = round((duration * 1000 * 10000) / token_count, 2)
                        record["ms_per_10k_tokens"] = ms_per_10k_tokens
            
            # 追加写入文件（NDJSON 格式：每行一个 JSON）
            with open(file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record, ensure_ascii=False) + '\n')
            
            # 记录到日志（简化版，包含 token 速度信息）
            log_msg = f"⏱️  [{monitor_type}] {operation}: {record['duration_ms']}ms"
            if "tokens_per_second" in record:
                log_msg += f", {record['tokens_per_second']} tokens/s, {record['ms_per_10k_tokens']}ms/10k tokens"
            
            logger.debug(log_msg, **metadata if metadata else {})
        
        except Exception as e:
            logger.error(f"性能监控记录失败: {e}", exc_info=True)


# 全局单例
_monitor = PerformanceMonitor()


def _estimate_token_count(text: Any) -> int:
    """
    估算文本的 token 数量
    
    简化算法：
    - 中文：1 字符 ≈ 1 token
    - 英文：4 字符 ≈ 1 token
    - 标点符号：1 个 ≈ 1 token
    
    Args:
        text: 文本（字符串或字符串列表）
    
    Returns:
        int: 估算的 token 数量
    """
    try:
        # 处理列表
        if isinstance(text, (list, tuple)):
            return sum(_estimate_token_count(t) for t in text)
        
        # 处理字符串
        if isinstance(text, str):
            # 简化估算：总字符数 * 0.8（考虑中英文混合）
            return int(len(text) * 0.8)
        
        return 0
    except:
        return 0


def performance_monitor(
    monitor_type: str,
    operation_name: Optional[str] = None,
    include_args: bool = False,
    include_result: bool = False
):
    """
    同步函数性能监控装饰器
    
    Args:
        monitor_type: 监控类型（embedding, vector_search, llm_think 等）
        operation_name: 操作名称（默认使用函数名）
        include_args: 是否在元数据中包含函数参数
        include_result: 是否在元数据中包含返回值信息
    
    用法:
        @performance_monitor('embedding', operation_name='文档向量化')
        def encode_documents(documents):
            ...
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation_name or f"{func.__module__}.{func.__name__}"
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            metadata = {}
            
            # 记录参数信息
            if include_args:
                try:
                    # 只记录简单类型和数量
                    if args:
                        metadata['args_count'] = len(args)
                        # 如果第一个参数是列表，记录长度
                        if isinstance(args[0], (list, tuple)):
                            metadata['input_count'] = len(args[0])
                    if kwargs:
                        metadata['kwargs_keys'] = list(kwargs.keys())
                except:
                    pass
            
            # 🔥 对于 embedding 类型，自动计算 token 数量
            if monitor_type == 'embedding':
                try:
                    # 尝试从参数中提取文本
                    texts = None
                    
                    # 检查是否是类方法（第一个参数是 self）
                    start_index = 1 if args and hasattr(args[0], '__dict__') else 0
                    
                    # 从位置参数提取（跳过 self）
                    if args and len(args) > start_index:
                        texts = args[start_index]
                    # 从关键字参数提取
                    elif 'texts' in kwargs:
                        texts = kwargs['texts']
                    elif 'query' in kwargs:
                        texts = kwargs['query']
                    elif 'documents' in kwargs:
                        texts = kwargs['documents']
                    
                    if texts:
                        token_count = _estimate_token_count(texts)
                        if token_count > 0:
                            metadata['token_count'] = token_count
                except:
                    pass
            
            try:
                result = func(*args, **kwargs)
                
                # 记录返回值信息
                if include_result and result is not None:
                    try:
                        if isinstance(result, (list, tuple)):
                            metadata['output_count'] = len(result)
                        elif hasattr(result, '__len__'):
                            metadata['output_size'] = len(result)
                    except:
                        pass
                
                duration = time.time() - start_time
                metadata['status'] = 'success'
                _monitor.record(monitor_type, op_name, duration, metadata)
                
                return result
            
            except Exception as e:
                duration = time.time() - start_time
                metadata['status'] = 'error'
                metadata['error_type'] = type(e).__name__
                metadata['error_message'] = str(e)
                _monitor.record(monitor_type, op_name, duration, metadata)
                raise
        
        return wrapper
    return decorator


def async_performance_monitor(
    monitor_type: str,
    operation_name: Optional[str] = None,
    include_args: bool = False,
    include_result: bool = False
):
    """
    异步函数性能监控装饰器
    
    Args:
        monitor_type: 监控类型
        operation_name: 操作名称（默认使用函数名）
        include_args: 是否在元数据中包含函数参数
        include_result: 是否在元数据中包含返回值信息
    
    用法:
        @async_performance_monitor('vector_search', operation_name='向量检索')
        async def search_vectors(query_vector, top_k):
            ...
    """
    def decorator(func: Callable) -> Callable:
        op_name = operation_name or f"{func.__module__}.{func.__name__}"
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.time()
            metadata = {}
            
            # 记录参数信息
            if include_args:
                try:
                    if args:
                        metadata['args_count'] = len(args)
                        if isinstance(args[0], (list, tuple)):
                            metadata['input_count'] = len(args[0])
                    if kwargs:
                        metadata['kwargs_keys'] = list(kwargs.keys())
                except:
                    pass
            
            # 🔥 对于 embedding 类型，自动计算 token 数量
            if monitor_type == 'embedding':
                try:
                    # 尝试从参数中提取文本
                    texts = None
                    
                    # 检查是否是类方法（第一个参数是 self）
                    start_index = 1 if args and hasattr(args[0], '__dict__') else 0
                    
                    # 从位置参数提取（跳过 self）
                    if args and len(args) > start_index:
                        texts = args[start_index]
                    # 从关键字参数提取
                    elif 'texts' in kwargs:
                        texts = kwargs['texts']
                    elif 'query' in kwargs:
                        texts = kwargs['query']
                    elif 'documents' in kwargs:
                        texts = kwargs['documents']
                    
                    if texts:
                        token_count = _estimate_token_count(texts)
                        if token_count > 0:
                            metadata['token_count'] = token_count
                except:
                    pass
            
            try:
                result = await func(*args, **kwargs)
                
                # 记录返回值信息
                if include_result and result is not None:
                    try:
                        if isinstance(result, (list, tuple)):
                            metadata['output_count'] = len(result)
                        elif hasattr(result, '__len__'):
                            metadata['output_size'] = len(result)
                    except:
                        pass
                
                duration = time.time() - start_time
                metadata['status'] = 'success'
                _monitor.record(monitor_type, op_name, duration, metadata)
                
                return result
            
            except Exception as e:
                duration = time.time() - start_time
                metadata['status'] = 'error'
                metadata['error_type'] = type(e).__name__
                metadata['error_message'] = str(e)
                _monitor.record(monitor_type, op_name, duration, metadata)
                raise
        
        return wrapper
    return decorator


# ==================== 上下文管理器（用于手动计时）====================

class PerformanceTimer:
    """
    性能计时器上下文管理器
    
    用法:
        with PerformanceTimer('llm_think', '推理步骤1'):
            # 执行耗时操作
            result = llm.generate(prompt)
    """
    
    def __init__(self, monitor_type: str, operation: str, metadata: Optional[Dict] = None):
        self.monitor_type = monitor_type
        self.operation = operation
        self.metadata = metadata or {}
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type is not None:
            self.metadata['status'] = 'error'
            self.metadata['error_type'] = exc_type.__name__
            self.metadata['error_message'] = str(exc_val)
        else:
            self.metadata['status'] = 'success'
        
        _monitor.record(self.monitor_type, self.operation, duration, self.metadata)
        
        # 不抑制异常
        return False


class AsyncPerformanceTimer:
    """
    异步性能计时器上下文管理器
    
    用法:
        async with AsyncPerformanceTimer('vector_search', '检索文档'):
            results = await vector_store.search(...)
    """
    
    def __init__(self, monitor_type: str, operation: str, metadata: Optional[Dict] = None):
        self.monitor_type = monitor_type
        self.operation = operation
        self.metadata = metadata or {}
        self.start_time = None
    
    async def __aenter__(self):
        self.start_time = time.time()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type is not None:
            self.metadata['status'] = 'error'
            self.metadata['error_type'] = exc_type.__name__
            self.metadata['error_message'] = str(exc_val)
        else:
            self.metadata['status'] = 'success'
        
        _monitor.record(self.monitor_type, self.operation, duration, self.metadata)
        
        return False


# ==================== 便捷函数 ====================

def record_performance(
    monitor_type: str,
    operation: str,
    duration: float,
    **metadata
):
    """
    直接记录性能数据（不使用装饰器）
    
    用法:
        start = time.time()
        result = do_something()
        record_performance('embedding', '向量化', time.time() - start, count=100)
    """
    _monitor.record(monitor_type, operation, duration, metadata)
