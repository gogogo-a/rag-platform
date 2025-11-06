"""
高德路线规划工具
支持驾车、步行、骑行、电动车、公交等多种出行方式的路线规划
"""
from typing import Dict, Any, Optional
import requests


def _format_route_summary(route_type: str, data: Dict, origin: str, destination: str) -> str:
    """格式化路线摘要信息"""
    try:
        route = data.get("route", {})
        
        if route_type in ["driving", "walking", "bicycling", "electrobike"]:
            # 驾车、步行、骑行、电动车的返回格式相似
            paths = route.get("paths", [])
            if not paths:
                return "未找到路线信息"
            
            # 可能有多条路线方案
            summary_parts = [
                f"📍 起点: {origin}",
                f"📍 终点: {destination}",
                f"🚗 共找到 {len(paths)} 条路线方案\n"
            ]
            
            for i, path in enumerate(paths, 1):
                distance = float(path.get("distance", 0))
                distance_km = distance / 1000
                
                # 提取耗时信息（如果有）
                duration_info = ""
                cost = path.get("cost", {})
                if cost:
                    duration = cost.get("duration", "")
                    if duration:
                        duration_min = int(float(duration)) // 60
                        duration_info = f" | ⏱️ 约 {duration_min} 分钟"
                    
                    # 驾车特有信息
                    if route_type == "driving":
                        tolls = cost.get("tolls", "0")
                        traffic_lights = cost.get("traffic_lights", "0")
                        extra_info = f" | 💰 过路费: {tolls}元 | 🚦 红绿灯: {traffic_lights}个"
                        duration_info += extra_info
                
                summary_parts.append(f"【方案{i}】📏 距离: {distance_km:.2f}公里{duration_info}")
                
                # 添加分段说明（前3段）
                steps = path.get("steps", [])[:3]
                if steps:
                    summary_parts.append("  路线说明:")
                    for step in steps:
                        instruction = step.get("instruction", "")
                        road_name = step.get("road_name", "")
                        step_distance = float(step.get("step_distance", 0))
                        summary_parts.append(f"    - {instruction} ({road_name}, {step_distance}米)")
                    if len(path.get("steps", [])) > 3:
                        summary_parts.append(f"    ... 还有 {len(path.get('steps', [])) - 3} 个路段")
                
                summary_parts.append("")  # 空行分隔
            
            return "\n".join(summary_parts).strip()
            
        elif route_type == "transit":
            # 公交路线
            transits = route.get("transits", [])
            if not transits:
                return "未找到公交路线"
            
            summary_parts = [
                f"📍 起点: {origin}",
                f"📍 终点: {destination}",
                f"🚌 共找到 {len(transits)} 条公交换乘方案\n"
            ]
            
            for i, transit in enumerate(transits[:3], 1):  # 最多显示前3条方案
                distance = float(transit.get("distance", 0))
                distance_km = distance / 1000
                
                # 提取耗时和费用
                cost = transit.get("cost", {})
                duration = cost.get("duration", "0")
                duration_min = int(float(duration)) // 60
                transit_fee = cost.get("transit_fee", "未知")
                
                summary_parts.append(
                    f"【方案{i}】📏 {distance_km:.2f}公里 | ⏱️ 约{duration_min}分钟 | 💰 {transit_fee}元"
                )
                
                # 添加换乘说明
                segments = transit.get("segments", [])
                if segments:
                    summary_parts.append("  换乘说明:")
                    for seg in segments:
                        # 步行段
                        if "walking" in seg:
                            walking = seg["walking"]
                            walk_distance = float(walking.get("distance", 0))
                            summary_parts.append(f"    🚶 步行 {walk_distance}米")
                        
                        # 公交/地铁段
                        if "bus" in seg:
                            bus = seg["bus"]
                            buslines = bus.get("buslines", [])
                            for busline in buslines:
                                bus_name = busline.get("name", "")
                                departure_stop = busline.get("departure_stop", {}).get("name", "")
                                arrival_stop = busline.get("arrival_stop", {}).get("name", "")
                                via_num = busline.get("via_num", 0)
                                summary_parts.append(
                                    f"    🚌 {bus_name}: {departure_stop} → {arrival_stop} ({via_num}站)"
                                )
                
                summary_parts.append("")  # 空行
            
            if len(transits) > 3:
                summary_parts.append(f"... 还有 {len(transits) - 3} 条备选方案")
            
            return "\n".join(summary_parts).strip()
        
        return "未知路线类型"
        
    except Exception as e:
        return f"格式化路线信息失败: {str(e)}"


def route_planning(
    origin: str,
    destination: str,
    mode: str = "driving",
    strategy: Optional[int] = None,
    waypoints: Optional[str] = None,
    city1: Optional[str] = None,
    city2: Optional[str] = None
) -> Dict[str, Any]:
    """
    高德路线规划工具（通用）
    根据起终点坐标规划出行路线
    
    Args:
        origin: 起点坐标，格式："经度,纬度"（如："116.481028,39.989643"）
        destination: 终点坐标，格式："经度,纬度"（如："116.434446,39.90816"）
        mode: 出行方式
            - "driving": 驾车（默认）
            - "walking": 步行
            - "bicycling": 骑行
            - "electrobike": 电动车
            - "transit": 公交
        strategy: 路线策略（仅驾车和公交有效）
            驾车策略：
                0: 速度优先，32: 推荐（默认），33: 躲避拥堵，34: 高速优先
                35: 不走高速，36: 少收费，38: 速度最快
            公交策略：
                0: 推荐（默认），1: 最经济，2: 最少换乘，3: 最少步行
                5: 不乘地铁，7: 地铁优先，8: 时间短
        waypoints: 途经点（仅驾车有效），多个途经点用";"分隔
        city1: 起点城市代码（仅公交必填，如："010"表示北京）
        city2: 终点城市代码（仅公交必填）
        
    Returns:
        Dict: 路线规划结果
            - success: 是否成功
            - data: 路线数据
            - summary: 格式化的路线摘要
            - route_count: 方案数量
            
    示例:
        # 驾车路线（北京天安门到故宫）
        result = route_planning(
            origin="116.397428,39.90923",
            destination="116.403963,39.924091",
            mode="driving"
        )
        
        # 公交换乘
        result = route_planning(
            origin="116.481028,39.989643",
            destination="116.434446,39.90816",
            mode="transit",
            city1="010",
            city2="010"
        )
    """
    try:
        from pkg.constants.constants import GAODE_API_KEY
        
        if not GAODE_API_KEY:
            return {
                "success": False,
                "data": None,
                "summary": "",
                "route_count": 0,
                "message": "路线规划功能未配置（缺少 GAODE_API_KEY）"
            }
        
        # 根据出行方式选择API端点
        mode_urls = {
            "driving": "https://restapi.amap.com/v5/direction/driving",
            "walking": "https://restapi.amap.com/v5/direction/walking",
            "bicycling": "https://restapi.amap.com/v5/direction/bicycling",
            "electrobike": "https://restapi.amap.com/v5/direction/electrobike",
            "transit": "https://restapi.amap.com/v5/direction/transit/integrated"
        }
        
        mode_names = {
            "driving": "驾车",
            "walking": "步行",
            "bicycling": "骑行",
            "electrobike": "电动车",
            "transit": "公交"
        }
        
        if mode not in mode_urls:
            return {
                "success": False,
                "data": None,
                "summary": "",
                "route_count": 0,
                "message": f"不支持的出行方式: {mode}"
            }
        
        url = mode_urls[mode]
        mode_name = mode_names[mode]
        
        print(f"[工具] 路线规划: {origin} → {destination} (方式: {mode_name})")
        
        # 构建请求参数
        params = {
            "key": GAODE_API_KEY,
            "origin": origin,
            "destination": destination,
            "output": "json",
            "show_fields": "cost,navi,polyline"  # 请求详细信息
        }
        
        # 添加特定参数
        if mode == "driving":
            params["strategy"] = strategy if strategy is not None else 32
            if waypoints:
                params["waypoints"] = waypoints
        elif mode == "transit":
            # 公交必须提供城市代码
            if not city1 or not city2:
                return {
                    "success": False,
                    "data": None,
                    "summary": "",
                    "route_count": 0,
                    "message": "公交路线规划需要提供起点和终点的城市代码（city1, city2）"
                }
            params["city1"] = city1
            params["city2"] = city2
            params["strategy"] = strategy if strategy is not None else 0
        elif mode in ["walking", "bicycling", "electrobike"]:
            params["alternative_route"] = 3  # 返回多条备选路线
        
        # 发送请求
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        
        # 解析响应
        data = response.json()
        
        # 检查返回状态
        if data.get("status") != "1":
            error_msg = data.get("info", "未知错误")
            print(f"[工具] 路线规划失败: {error_msg}")
            return {
                "success": False,
                "data": None,
                "summary": "",
                "route_count": 0,
                "message": f"规划失败: {error_msg}"
            }
        
        # 检查路线数量
        count = int(data.get("count", 0))
        if count == 0:
            return {
                "success": False,
                "data": None,
                "summary": "",
                "route_count": 0,
                "message": "未找到可用路线"
            }
        
        # 格式化摘要
        summary = _format_route_summary(mode, data, origin, destination)
        
        print(f"[工具] 路线规划成功: 找到 {count} 条路线方案")
        
        return {
            "success": True,
            "data": data,
            "summary": summary,
            "route_count": count,
            "mode": mode_name,
            "message": f"成功规划 {mode_name} 路线，共 {count} 条方案"
        }
        
    except requests.exceptions.Timeout:
        print("[工具] 路线规划请求超时")
        return {
            "success": False,
            "data": None,
            "summary": "",
            "route_count": 0,
            "message": "请求超时，请稍后重试"
        }
    except requests.exceptions.RequestException as e:
        print(f"[工具] 路线规划请求失败: {e}")
        return {
            "success": False,
            "data": None,
            "summary": "",
            "route_count": 0,
            "message": f"请求失败: {str(e)}"
        }
    except Exception as e:
        print(f"[工具] 路线规划失败: {e}")
        return {
            "success": False,
            "data": None,
            "summary": "",
            "route_count": 0,
            "message": f"规划失败: {str(e)}"
        }


# 工具元信息
route_planning.prompt_template = "default"
route_planning.description = """路线规划工具，支持驾车、步行、骑行、电动车、公交等多种出行方式。
输入起点和终点的经纬度坐标（格式："经度,纬度"），返回详细的路线规划方案，包括距离、耗时、路线说明等。
注意：公交路线需要额外提供起点和终点的城市代码（如北京为"010"）"""
route_planning.is_admin = False  # 所有用户可用

