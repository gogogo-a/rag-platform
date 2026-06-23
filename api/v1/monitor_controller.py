"""
监控数据查询 API 控制器
"""
from fastapi import APIRouter, Query, Path, Request
from typing import Optional
from internal.service.json_load.monitor_sever import monitor_service
from api.v1.response_controller import json_response
from log import logger

router = APIRouter(prefix="/monitors", tags=["性能监控"])


@router.get("/performance/{monitor_type}", summary="获取性能监控数据")
async def get_performance_monitor(
    request: Request,
    monitor_type: str = Path(..., description="监控类型（embedding, vector_search, llm_think, llm_action, llm_answer, llm_total, agent_total）"),
    date: Optional[str] = Query(None, description="日期（格式：YYYY-MM-DD），不提供则返回今天的数据"),
    limit: Optional[int] = Query(100, ge=1, le=1000, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量（用于分页）")
):
    """
    获取指定类型的性能监控数据
    
    **监控类型：**
    - `embedding`: Embedding 向量化性能
    - `vector_search`: 向量检索性能
    - `llm_think`: LLM 思考过程性能
    - `llm_action`: LLM 动作执行性能
    - `llm_answer`: LLM 答案生成性能
    - `llm_total`: LLM 完整对话性能
    - `agent_total`: Agent 完整推理性能
    
    **参数：**
    - **monitor_type**: 监控类型
    - **date**: 日期（格式：YYYY-MM-DD），可选，默认今天
    - **limit**: 返回的最大记录数，默认 100
    - **offset**: 偏移量，用于分页，默认 0
    
    **返回：**
    ```json
    {
        "code": 200,
        "message": "成功",
        "data": {
            "date": "2025-10-26",
            "type": "embedding",
            "total": 150,
            "count": 100,
            "offset": 0,
            "data": [
                {
                    "timestamp": "2025-10-26T10:30:45.123456",
                    "operation": "文本向量化",
                    "duration_ms": 125.45,
                    "duration_s": 0.1255,
                    "metadata": {...}
                }
            ]
        }
    }
    ```
    
    **示例：**
    ```bash
    # 获取今天的 Embedding 性能数据
    curl "http://localhost:8000/monitors/performance/embedding"
    
    # 获取指定日期的 LLM 性能数据
    curl "http://localhost:8000/monitors/performance/llm_total?date=2025-10-25"
    
    # 分页查询
    curl "http://localhost:8000/monitors/performance/vector_search?limit=50&offset=100"
    ```
    """
    try:
        logger.info(f"查询性能监控: type={monitor_type}, date={date}, limit={limit}, offset={offset}")
        
        # 调用服务层
        result = monitor_service.get_performance_monitor(monitor_type, date, limit, offset)
        
        return json_response("成功", 0, result)
    
    except Exception as e:
        logger.error(f"获取性能监控数据失败: {e}", exc_info=True)
        return json_response(f"获取性能监控数据失败: {str(e)}", -1)


@router.get("/resource", summary="获取资源监控数据")
async def get_resource_monitor(
    request: Request,
    date: Optional[str] = Query(None, description="日期（格式：YYYY-MM-DD），不提供则返回今天的数据"),
    limit: Optional[int] = Query(100, ge=1, le=1000, description="每页数量"),
    offset: int = Query(0, ge=0, description="偏移量（用于分页）")
):
    """
    获取系统资源监控数据（CPU、内存、GPU、MongoDB、Qdrant）
    
    **参数：**
    - **date**: 日期（格式：YYYY-MM-DD），可选，默认今天
    - **limit**: 返回的最大记录数，默认 100
    - **offset**: 偏移量，用于分页，默认 0
    
    **返回：**
    ```json
    {
        "code": 200,
        "message": "成功",
        "data": {
            "date": "2025-10-26",
            "type": "resource",
            "total": 24,
            "count": 24,
            "offset": 0,
            "data": [
                {
                    "timestamp": "2025-10-26T10:30:00.000000",
                    "system": {
                        "cpu_percent": 45.2,
                        "memory_percent": 62.3,
                        "disk_percent": 55.1
                    },
                    "mongodb": {...},
                    "qdrant": {...},
                    "app_stats": {...}
                }
            ]
        }
    }
    ```
    
    **示例：**
    ```bash
    # 获取今天的资源监控数据
    curl "http://localhost:8000/monitors/resource"
    
    # 获取指定日期的资源监控数据
    curl "http://localhost:8000/monitors/resource?date=2025-10-25"
    ```
    """
    try:
        logger.info(f"查询资源监控: date={date}, limit={limit}, offset={offset}")
        
        # 调用服务层
        result = monitor_service.get_resource_monitor(date, limit, offset)
        
        return json_response("成功", 0, result)
    
    except Exception as e:
        logger.error(f"获取资源监控数据失败: {e}", exc_info=True)
        return json_response(f"获取资源监控数据失败: {str(e)}", -1)


@router.get("/all", summary="获取所有监控数据（概览）")
async def get_all_monitors(
    request: Request,
    date: Optional[str] = Query(None, description="日期（格式：YYYY-MM-DD），不提供则返回今天的数据"),
    limit: Optional[int] = Query(10, ge=1, le=100, description="每种类型返回的记录数")
):
    """
    获取所有监控数据（每种类型返回最新的几条记录）
    
    **参数：**
    - **date**: 日期（格式：YYYY-MM-DD），可选，默认今天
    - **limit**: 每种类型返回的记录数，默认 10
    
    **返回：**
    ```json
    {
        "code": 200,
        "message": "成功",
        "data": {
            "date": "2025-10-26",
            "performance": {
                "embedding": {"total": 150, "data": [...]},
                "vector_search": {"total": 80, "data": [...]},
                "llm_total": {"total": 50, "data": [...]}
            },
            "resource": {
                "total": 24,
                "data": [...]
            }
        }
    }
    ```
    
    **示例：**
    ```bash
    # 获取今天所有监控数据的概览
    curl "http://localhost:8000/monitors/all"
    
    # 获取指定日期的监控概览
    curl "http://localhost:8000/monitors/all?date=2025-10-25&limit=20"
    ```
    """
    try:
        logger.info(f"查询所有监控数据: date={date}, limit={limit}")
        
        # 调用服务层
        result = monitor_service.get_all_monitors(date, limit)
        
        return json_response("成功", 0, result)
    
    except Exception as e:
        logger.error(f"获取所有监控数据失败: {e}", exc_info=True)
        return json_response(f"获取所有监控数据失败: {str(e)}", -1)


@router.get("/dates", summary="获取可用的监控日期")
async def get_available_monitor_dates(request: Request):
    """
    获取所有可用的监控日期
    
    **返回：**
    ```json
    {
        "code": 200,
        "message": "成功",
        "data": {
            "dates": [
                "2025-10-26",
                "2025-10-25",
                "2025-10-24"
            ]
        }
    }
    ```
    
    **示例：**
    ```bash
    curl "http://localhost:8000/monitors/dates"
    ```
    """
    try:
        logger.info("查询可用的监控日期")
        
        dates = monitor_service.get_available_dates()
        
        return json_response("成功", 0, {"dates": dates})
    
    except Exception as e:
        logger.error(f"获取可用日期失败: {e}", exc_info=True)
        return json_response(f"获取可用日期失败: {str(e)}", -1)


@router.get("/types", summary="获取所有监控类型")
async def get_monitor_types(request: Request):
    """
    获取所有可用的监控类型
    
    **返回：**
    ```json
    {
        "code": 200,
        "message": "成功",
        "data": {
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
    }
    ```
    
    **示例：**
    ```bash
    curl "http://localhost:8000/monitors/types"
    ```
    """
    try:
        logger.info("查询监控类型列表")
        
        types = monitor_service.get_monitor_types()
        
        return json_response("成功", 0, types)
    
    except Exception as e:
        logger.error(f"获取监控类型失败: {e}", exc_info=True)
        return json_response(f"获取监控类型失败: {str(e)}", -1)


@router.get("/statistics", summary="获取监控统计信息")
async def get_monitor_statistics(request: Request):
    """
    获取监控统计信息（性能统计、资源使用统计）
    
    **返回：**
    ```json
    {
        "code": 200,
        "message": "成功",
        "data": {
            "today_date": "2025-10-26",
            "total_records": 520,
            "performance_stats": {
                "embedding": {
                    "count": 150,
                    "avg_duration_ms": 125.45,
                    "min_duration_ms": 80.12,
                    "max_duration_ms": 230.67,
                    "recent": [...]
                },
                "vector_search": {
                    "count": 80,
                    "avg_duration_ms": 45.23,
                    "min_duration_ms": 20.15,
                    "max_duration_ms": 95.41,
                    "recent": [...]
                },
                "llm_think": {...},
                "llm_action": {...},
                "llm_answer": {...},
                "llm_total": {...},
                "agent_total": {...}
            },
            "resource_stats": {
                "count": 24,
                "cpu": {
                    "avg": 45.2,
                    "max": 78.5,
                    "min": 12.3
                },
                "memory": {
                    "avg": 62.3,
                    "max": 85.1,
                    "min": 45.2
                },
                "gpu": {
                    "avg": 35.5,
                    "max": 65.2,
                    "min": 10.1
                },
                "recent": [...]
            },
            "available_dates": ["2025-10-26", "2025-10-25", "2025-10-24"]
        }
    }
    ```
    
    **字段说明：**
    - **today_date**: 今天的日期
    - **total_records**: 今日所有类型监控的总记录数
    - **performance_stats**: 各类性能监控统计
      - **count**: 记录数
      - **avg_duration_ms**: 平均耗时（毫秒）
      - **min_duration_ms**: 最小耗时（毫秒）
      - **max_duration_ms**: 最大耗时（毫秒）
      - **recent**: 最近3条记录
    - **resource_stats**: 资源使用统计
      - **count**: 记录数
      - **cpu/memory/gpu**: 各项资源的平均值、峰值、最小值
      - **recent**: 最近3条记录
    - **available_dates**: 所有可用的监控日期
    
    **示例：**
    ```bash
    # 获取监控统计信息
    curl "http://localhost:8000/monitors/statistics"
    ```
    """
    try:
        logger.info("查询监控统计信息")
        
        stats = monitor_service.get_monitor_statistics()
        
        return json_response("成功", 0, stats)
    
    except Exception as e:
        logger.error(f"获取监控统计信息失败: {e}", exc_info=True)
        return json_response(f"获取监控统计信息失败: {str(e)}", -1)

