"""
监控数据读取服务

读取 json_monitor 目录下的性能监控和资源监控数据
"""
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from log import logger


class MonitorService:
    """监控数据读取服务（单例模式）"""
    
    _instance = None
    _initialized = False
    
    # 监控类型列表
    MONITOR_TYPES = {
        "performance": [
            "embedding",
            "vector_search",
            "llm_think",
            "llm_action",
            "llm_answer",
            "llm_total",
            "agent_total"
        ],
        "resource": [
            "resource"
        ]
    }
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 监控目录
        project_root = Path(__file__).parent.parent.parent.parent
        self.monitor_dir = project_root / "json_monitor"
        
        self._initialized = True
        logger.info(f"监控服务已初始化，监控目录: {self.monitor_dir}")
    
    def _get_monitor_dir(self, date: Optional[str] = None) -> Path:
        """
        获取指定日期的监控目录
        
        Args:
            date: 日期字符串，格式 YYYY-MM-DD（可选，默认今天）
        
        Returns:
            Path: 监控目录路径，格式：json_monitor/YY_MM_DD_monitor/
        """
        if date:
            try:
                dt = datetime.strptime(date, "%Y-%m-%d")
                dir_name = dt.strftime("%y_%m_%d_monitor")
            except ValueError:
                logger.error(f"日期格式错误: {date}，应为 YYYY-MM-DD")
                return None
        else:
            # 默认今天
            dir_name = datetime.now().strftime("%y_%m_%d_monitor")
        
        return self.monitor_dir / dir_name
    
    def get_performance_monitor(
        self,
        monitor_type: str,
        date: Optional[str] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        获取性能监控数据
        
        Args:
            monitor_type: 监控类型（embedding, vector_search, llm_think 等）
            date: 日期字符串，格式 YYYY-MM-DD（可选，默认今天）
            limit: 返回的最大记录数（可选，默认100）
            offset: 偏移量，用于分页（默认0）
        
        Returns:
            Dict: {
                "date": "2025-10-26",
                "type": "embedding",
                "total": 150,
                "count": 100,
                "offset": 0,
                "data": [...]
            }
        """
        try:
            monitor_dir = self._get_monitor_dir(date)
            
            if not monitor_dir or not monitor_dir.exists():
                return {
                    "date": date or datetime.now().strftime("%Y-%m-%d"),
                    "type": monitor_type,
                    "total": 0,
                    "count": 0,
                    "offset": 0,
                    "data": [],
                    "message": f"监控目录不存在: {monitor_dir}"
                }
            
            monitor_file = monitor_dir / f"{monitor_type}.json"
            
            if not monitor_file.exists():
                return {
                    "date": date or datetime.now().strftime("%Y-%m-%d"),
                    "type": monitor_type,
                    "total": 0,
                    "count": 0,
                    "offset": 0,
                    "data": [],
                    "message": f"监控文件不存在: {monitor_file.name}"
                }
            
            # 读取 NDJSON 文件
            records = []
            with open(monitor_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            record = json.loads(line)
                            records.append(record)
                        except json.JSONDecodeError as e:
                            logger.warning(f"解析监控记录失败: {e}")
            
            total = len(records)
            
            # 反转列表，最新的在前面
            records.reverse()
            
            # 分页
            if limit:
                paginated_records = records[offset:offset + limit]
            else:
                paginated_records = records[offset:]
            
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "type": monitor_type,
                "total": total,
                "count": len(paginated_records),
                "offset": offset,
                "data": paginated_records
            }
        
        except Exception as e:
            logger.error(f"读取性能监控数据失败: {e}", exc_info=True)
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "type": monitor_type,
                "total": 0,
                "count": 0,
                "offset": 0,
                "data": [],
                "error": str(e)
            }
    
    def get_resource_monitor(
        self,
        date: Optional[str] = None,
        limit: Optional[int] = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        获取资源监控数据
        
        Args:
            date: 日期字符串，格式 YYYY-MM-DD（可选，默认今天）
            limit: 返回的最大记录数（可选，默认100）
            offset: 偏移量，用于分页（默认0）
        
        Returns:
            Dict: {
                "date": "2025-10-26",
                "type": "resource",
                "total": 150,
                "count": 100,
                "offset": 0,
                "data": [...]
            }
        """
        return self.get_performance_monitor("resource", date, limit, offset)
    
    def get_all_monitors(
        self,
        date: Optional[str] = None,
        limit: Optional[int] = 10
    ) -> Dict[str, Any]:
        """
        获取所有监控数据（每种类型返回最新的几条）
        
        Args:
            date: 日期字符串，格式 YYYY-MM-DD（可选，默认今天）
            limit: 每种类型返回的记录数（默认10）
        
        Returns:
            Dict: {
                "date": "2025-10-26",
                "performance": {...},
                "resource": {...}
            }
        """
        try:
            result = {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "performance": {},
                "resource": {}
            }
            
            # 获取性能监控
            for monitor_type in self.MONITOR_TYPES["performance"]:
                data = self.get_performance_monitor(monitor_type, date, limit, 0)
                result["performance"][monitor_type] = {
                    "total": data["total"],
                    "data": data["data"]
                }
            
            # 获取资源监控
            data = self.get_resource_monitor(date, limit, 0)
            result["resource"] = {
                "total": data["total"],
                "data": data["data"]
            }
            
            return result
        
        except Exception as e:
            logger.error(f"获取所有监控数据失败: {e}")
            return {
                "date": date or datetime.now().strftime("%Y-%m-%d"),
                "performance": {},
                "resource": {},
                "error": str(e)
            }
    
    def get_available_dates(self) -> List[str]:
        """
        获取所有可用的监控日期
        
        Returns:
            List[str]: 日期列表，格式 YYYY-MM-DD
        """
        try:
            if not self.monitor_dir.exists():
                return []
            
            dates = []
            for dir_path in self.monitor_dir.iterdir():
                if dir_path.is_dir() and dir_path.name.endswith("_monitor"):
                    # 解析目录名：YY_MM_DD_monitor -> YYYY-MM-DD
                    try:
                        date_str = dir_path.name.replace("_monitor", "")
                        dt = datetime.strptime(date_str, "%y_%m_%d")
                        dates.append(dt.strftime("%Y-%m-%d"))
                    except ValueError:
                        continue
            
            # 按日期倒序排列
            dates.sort(reverse=True)
            return dates
        
        except Exception as e:
            logger.error(f"获取可用日期失败: {e}")
            return []
    
    def get_monitor_types(self) -> Dict[str, List[str]]:
        """
        获取所有监控类型
        
        Returns:
            Dict: {"performance": [...], "resource": [...]}
        """
        return self.MONITOR_TYPES
    
    def get_monitor_statistics(self) -> Dict[str, Any]:
        """
        获取监控数据统计信息
        
        Returns:
            Dict: {
                "today_date": "2025-10-26",
                "total_records": 总记录数（今日所有类型）,
                "performance_stats": {
                    "embedding": {
                        "count": 记录数,
                        "avg_duration_ms": 平均耗时,
                        "min_duration_ms": 最小耗时,
                        "max_duration_ms": 最大耗时,
                        "recent": 最近3条记录
                    },
                    ...
                },
                "resource_stats": {
                    "count": 记录数,
                    "avg_cpu": 平均CPU使用率,
                    "max_cpu": CPU峰值,
                    "avg_memory": 平均内存使用率,
                    "max_memory": 内存峰值,
                    "recent": 最近3条记录
                },
                "available_dates": 可用日期列表
            }
        """
        try:
            today_date = datetime.now().strftime("%Y-%m-%d")
            available_dates = self.get_available_dates()
            
            total_records = 0
            performance_stats = {}
            resource_stats = {}
            
            # 统计性能监控数据
            for monitor_type in self.MONITOR_TYPES["performance"]:
                data = self.get_performance_monitor(monitor_type, date=None, limit=3, offset=0)
                count = data.get("total", 0)
                total_records += count
                
                # 计算性能指标（从所有记录中计算，不只是最近3条）
                all_data = self.get_performance_monitor(monitor_type, date=None, limit=None, offset=0)
                records = all_data.get("data", [])
                
                durations = []
                for record in records:
                    duration = record.get("duration_ms")
                    if duration is not None:
                        durations.append(duration)
                
                avg_duration = round(sum(durations) / len(durations), 2) if durations else 0
                min_duration = round(min(durations), 2) if durations else 0
                max_duration = round(max(durations), 2) if durations else 0
                
                performance_stats[monitor_type] = {
                    "count": count,
                    "avg_duration_ms": avg_duration,
                    "min_duration_ms": min_duration,
                    "max_duration_ms": max_duration,
                    "recent": data.get("data", [])[:3]  # 最近3条
                }
            
            # 统计资源监控数据
            resource_data = self.get_resource_monitor(date=None, limit=3, offset=0)
            resource_count = resource_data.get("total", 0)
            total_records += resource_count
            
            # 计算资源使用统计
            all_resource = self.get_resource_monitor(date=None, limit=None, offset=0)
            resource_records = all_resource.get("data", [])
            
            cpu_values = []
            memory_values = []
            gpu_values = []
            
            for record in resource_records:
                system = record.get("system", {})
                
                cpu = system.get("cpu_percent")
                if cpu is not None:
                    cpu_values.append(cpu)
                
                memory = system.get("memory_percent")
                if memory is not None:
                    memory_values.append(memory)
                
                # GPU 数据可能在不同位置
                gpu_info = system.get("gpu", {})
                if isinstance(gpu_info, dict):
                    gpu = gpu_info.get("utilization")
                    if gpu is not None:
                        gpu_values.append(gpu)
            
            resource_stats = {
                "count": resource_count,
                "cpu": {
                    "avg": round(sum(cpu_values) / len(cpu_values), 2) if cpu_values else 0,
                    "max": round(max(cpu_values), 2) if cpu_values else 0,
                    "min": round(min(cpu_values), 2) if cpu_values else 0
                },
                "memory": {
                    "avg": round(sum(memory_values) / len(memory_values), 2) if memory_values else 0,
                    "max": round(max(memory_values), 2) if memory_values else 0,
                    "min": round(min(memory_values), 2) if memory_values else 0
                },
                "gpu": {
                    "avg": round(sum(gpu_values) / len(gpu_values), 2) if gpu_values else 0,
                    "max": round(max(gpu_values), 2) if gpu_values else 0,
                    "min": round(min(gpu_values), 2) if gpu_values else 0
                } if gpu_values else None,
                "recent": resource_data.get("data", [])[:3]  # 最近3条
            }
            
            # 移除空的 GPU 统计
            if resource_stats["gpu"] is None:
                del resource_stats["gpu"]
            
            return {
                "today_date": today_date,
                "total_records": total_records,
                "performance_stats": performance_stats,
                "resource_stats": resource_stats,
                "available_dates": available_dates
            }
        
        except Exception as e:
            logger.error(f"获取监控统计信息失败: {e}", exc_info=True)
            return {
                "today_date": datetime.now().strftime("%Y-%m-%d"),
                "total_records": 0,
                "performance_stats": {},
                "resource_stats": {},
                "available_dates": [],
                "error": str(e)
            }


# 全局单例
monitor_service = MonitorService()

