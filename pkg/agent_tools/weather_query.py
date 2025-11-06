"""
高德天气查询工具
查询城市天气信息（实况或预报）
"""
from typing import Dict, Any
import requests


def weather_query(city: str, extensions: str = "base") -> Dict[str, Any]:
    """
    高德天气查询工具
    查询指定城市的天气信息（使用高德地图 API）
    
    Args:
        city: 城市名称（如：北京、上海）或城市编码（如：110101）
            - 支持中文城市名（会自动查询对应的 adcode）
            - 支持直接使用 adcode（城市编码）
        extensions: 气象类型
            - "base": 返回实况天气（当前天气状况）
            - "all": 返回预报天气（未来3-4天预报）
        
    Returns:
        Dict: 包含天气信息的字典
            - success: 是否成功
            - data: 天气数据（实况或预报）
            - summary: 格式化的天气摘要文本
            - city_name: 城市名称
            - adcode: 城市编码
            
    示例:
        # 查询北京实况天气
        result = weather_query("北京", "base")
        
        # 查询上海天气预报
        result = weather_query("上海", "all")
        
        # 使用城市编码查询
        result = weather_query("110101", "base")
    """
    try:
        # 从环境变量获取 API Key
        from pkg.constants.constants import GAODE_API_KEY
        
        if not GAODE_API_KEY:
            print("[工具] ⚠️ 高德地图 API Key 未配置")
            return {
                "success": False,
                "data": None,
                "summary": "",
                "city_name": city,
                "adcode": "",
                "message": "天气查询功能未配置（缺少 GAODE_API_KEY）"
            }
        
        print(f"[工具] 天气查询: {city} (类型: {'实况' if extensions == 'base' else '预报'})")
        
        # 如果输入的是中文城市名，需要先转换为 adcode
        # 这里简化处理：如果是纯数字，认为是 adcode；否则当作城市名直接查询
        # 高德 API 支持直接使用城市名（中文）查询
        city_param = city
        
        # 构建请求 URL
        url = "https://restapi.amap.com/v3/weather/weatherInfo"
        
        params = {
            "key": GAODE_API_KEY,
            "city": city_param,
            "extensions": extensions,
            "output": "JSON"
        }
        
        # 发送请求
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # 解析响应
        data = response.json()
        
        # 检查返回状态
        if data.get("status") != "1":
            error_msg = data.get("info", "未知错误")
            print(f"[工具] 天气查询失败: {error_msg}")
            return {
                "success": False,
                "data": None,
                "summary": "",
                "city_name": city,
                "adcode": "",
                "message": f"查询失败: {error_msg}"
            }
        
        # 检查是否有数据
        if data.get("count") == "0":
            print(f"[工具] 未找到城市 '{city}' 的天气数据")
            return {
                "success": False,
                "data": None,
                "summary": "",
                "city_name": city,
                "adcode": "",
                "message": f"未找到城市 '{city}' 的天气数据，请检查城市名称或使用城市编码"
            }
        
        # 根据类型处理数据
        if extensions == "base":
            # 实况天气
            lives = data.get("lives", [])
            if not lives:
                return {
                    "success": False,
                    "data": None,
                    "summary": "",
                    "city_name": city,
                    "adcode": "",
                    "message": "未找到实况天气数据"
                }
            
            live_data = lives[0]
            city_name = live_data.get("city", city)
            adcode = live_data.get("adcode", "")
            
            # 格式化摘要
            summary = f"""
📍 {live_data.get('province', '')} {city_name}
🌡️ 温度: {live_data.get('temperature', '')}°C
☁️ 天气: {live_data.get('weather', '')}
💨 风向: {live_data.get('winddirection', '')}风 {live_data.get('windpower', '')}级
💧 湿度: {live_data.get('humidity', '')}%
🕒 更新时间: {live_data.get('reporttime', '')}
"""
            
            print(f"[工具] 查询成功: {city_name} - {live_data.get('weather', '')}")
            
            return {
                "success": True,
                "data": live_data,
                "summary": summary.strip(),
                "city_name": city_name,
                "adcode": adcode,
                "message": f"成功获取 {city_name} 的实况天气"
            }
            
        else:
            # 预报天气
            forecasts = data.get("forecasts", [])
            if not forecasts:
                return {
                    "success": False,
                    "data": None,
                    "summary": "",
                    "city_name": city,
                    "adcode": "",
                    "message": "未找到预报天气数据"
                }
            
            forecast_data = forecasts[0]
            city_name = forecast_data.get("city", city)
            adcode = forecast_data.get("adcode", "")
            casts = forecast_data.get("casts", [])
            
            # 格式化预报摘要
            summary_parts = [
                f"📍 {forecast_data.get('province', '')} {city_name}",
                f"🕒 预报发布时间: {forecast_data.get('reporttime', '')}",
                ""
            ]
            
            for i, cast in enumerate(casts, 1):
                day_info = f"""
【第{i}天 - {cast.get('date', '')} {cast.get('week', '')}】
白天: {cast.get('dayweather', '')} {cast.get('daytemp', '')}°C {cast.get('daywind', '')}风{cast.get('daypower', '')}级
夜间: {cast.get('nightweather', '')} {cast.get('nighttemp', '')}°C {cast.get('nightwind', '')}风{cast.get('nightpower', '')}级
"""
                summary_parts.append(day_info.strip())
            
            summary = "\n\n".join(summary_parts)
            
            print(f"[工具] 查询成功: {city_name} - 未来{len(casts)}天预报")
            
            return {
                "success": True,
                "data": forecast_data,
                "summary": summary.strip(),
                "city_name": city_name,
                "adcode": adcode,
                "casts": casts,
                "message": f"成功获取 {city_name} 未来{len(casts)}天的天气预报"
            }
        
    except requests.exceptions.Timeout:
        print("[工具] 天气查询超时")
        return {
            "success": False,
            "data": None,
            "summary": "",
            "city_name": city,
            "adcode": "",
            "message": "查询请求超时，请稍后重试"
        }
    except requests.exceptions.RequestException as e:
        print(f"[工具] 天气查询请求失败: {e}")
        return {
            "success": False,
            "data": None,
            "summary": "",
            "city_name": city,
            "adcode": "",
            "message": f"查询请求失败: {str(e)}"
        }
    except Exception as e:
        print(f"[工具] 天气查询失败: {e}")
        return {
            "success": False,
            "data": None,
            "summary": "",
            "city_name": city,
            "adcode": "",
            "message": f"查询失败: {str(e)}"
        }


# 工具元信息
weather_query.prompt_template = "default"
weather_query.description = "查询城市天气信息，支持实况天气和未来天气预报。输入城市名称（如：北京、上海）或城市编码即可查询"
weather_query.is_admin = False  # 所有用户可用

