"""
高德天气查询工具 - FastMCP 版本
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from mcp.server import FastMCP
from typing import Dict, Any
import requests

app = FastMCP("weather_query")


@app.tool()
def weather_query(city: str, extensions: str = "base") -> Dict[str, Any]:
    """
    高德天气查询工具
    
    Args:
        city: 城市名称（如：北京、上海）
        extensions: 气象类型（base=实况，all=预报）
        
    Returns:
        Dict: 包含天气信息的字典
    """
    try:
        from pkg.constants.constants import GAODE_API_KEY
        
        if not GAODE_API_KEY:
            return {
                "success": False,
                "summary": "天气查询功能未配置"
            }
        
        url = "https://restapi.amap.com/v3/weather/weatherInfo"
        params = {
            "key": GAODE_API_KEY,
            "city": city,
            "extensions": extensions,
            "output": "JSON"
        }
        
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        
        if data.get("status") != "1":
            return {
                "success": False,
                "summary": f"查询失败: {data.get('info', '未知错误')}"
            }
        
        if extensions == "base":
            lives = data.get("lives", [])
            if not lives:
                return {"success": False, "summary": "未找到实况天气数据"}
            
            live_data = lives[0]
            summary = f"""📍 {live_data.get('province', '')} {live_data.get('city', '')}
🌡️ 温度: {live_data.get('temperature', '')}°C
☁️ 天气: {live_data.get('weather', '')}
💨 风向: {live_data.get('winddirection', '')}风 {live_data.get('windpower', '')}级
💧 湿度: {live_data.get('humidity', '')}%"""
            
            return {"success": True, "summary": summary}
        else:
            forecasts = data.get("forecasts", [])
            if not forecasts:
                return {"success": False, "summary": "未找到预报天气数据"}
            
            forecast_data = forecasts[0]
            casts = forecast_data.get("casts", [])
            
            summary_parts = [f"📍 {forecast_data.get('city', '')} 天气预报"]
            for i, cast in enumerate(casts, 1):
                day_info = f"""【第{i}天 - {cast.get('date', '')}】
白天: {cast.get('dayweather', '')} {cast.get('daytemp', '')}°C
夜间: {cast.get('nightweather', '')} {cast.get('nighttemp', '')}°C"""
                summary_parts.append(day_info)
            
            return {"success": True, "summary": "\n\n".join(summary_parts)}
        
    except Exception as e:
        return {"success": False, "summary": f"查询失败: {str(e)}"}


if __name__ == "__main__":
    app.run(transport="stdio")
