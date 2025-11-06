"""
IP 定位工具
将 IP 地址转换为地理位置信息（使用高德地图 API）
"""
from typing import Dict, Any, Optional
import requests


def ip_location(ip: Optional[str] = None) -> Dict[str, Any]:
    """
    IP 定位工具
    将 IP 地址转换为地理位置信息（仅支持国内 IP）
    
    Args:
        ip: IP 地址（可选）
            - 如果提供 IP 地址，则查询该 IP 的位置
            - 如果不提供，则自动获取客户端 IP 并定位
            - 仅支持国内 IP 地址
        
    Returns:
        Dict: IP 定位结果
            - success: 是否成功
            - ip: 查询的 IP 地址
            - province: 省份名称
            - city: 城市名称
            - adcode: 城市编码
            - rectangle: 城市矩形区域范围
            - summary: 格式化的位置摘要
            
    示例:
        # 查询指定 IP
        result = ip_location("114.247.50.2")
        
        # 查询当前客户端 IP
        result = ip_location()
    """
    try:
        # 从环境变量获取 API Key
        from pkg.constants.constants import GAODE_API_KEY
        
        if not GAODE_API_KEY:
            print("[工具] ⚠️ 高德地图 API Key 未配置")
            return {
                "success": False,
                "ip": ip or "未知",
                "province": "",
                "city": "",
                "adcode": "",
                "rectangle": "",
                "summary": "",
                "message": "IP 定位功能未配置（缺少 GAODE_API_KEY）"
            }
        
        print(f"[工具] IP 定位: {ip if ip else '客户端 IP'}")
        
        # 构建请求 URL
        url = "https://restapi.amap.com/v3/ip"
        
        params = {
            "key": GAODE_API_KEY,
            "output": "json"
        }
        
        # 如果提供了 IP，添加到参数中
        if ip:
            params["ip"] = ip
        
        # 发送请求
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # 解析响应
        data = response.json()
        
        # 检查返回状态
        if data.get("status") != "1":
            error_msg = data.get("info", "未知错误")
            infocode = data.get("infocode", "")
            print(f"[工具] IP 定位失败: {error_msg} (infocode: {infocode})")
            return {
                "success": False,
                "ip": ip or "未知",
                "province": "",
                "city": "",
                "adcode": "",
                "rectangle": "",
                "summary": "",
                "message": f"定位失败: {error_msg}"
            }
        
        # 提取位置信息
        province = data.get("province", "")
        city = data.get("city", "")
        adcode = data.get("adcode", "")
        rectangle = data.get("rectangle", "")
        
        # 处理特殊情况
        if not province and not city:
            print("[工具] 未找到位置信息（可能是局域网 IP 或国外 IP）")
            return {
                "success": False,
                "ip": ip or "未知",
                "province": "",
                "city": "",
                "adcode": "",
                "rectangle": "",
                "summary": "",
                "message": "未找到位置信息（可能是局域网 IP、非法 IP 或国外 IP）"
            }
        
        # 处理直辖市情况（province 和 city 相同）
        location_str = ""
        if province == city:
            location_str = province
        else:
            location_str = f"{province} {city}"
        
        # 格式化摘要
        summary_parts = [
            f"📍 IP 地址: {ip if ip else '客户端 IP'}",
            f"🌍 位置: {location_str}",
        ]
        
        if adcode:
            summary_parts.append(f"🏙️ 城市编码: {adcode}")
        
        if rectangle:
            summary_parts.append(f"📐 区域范围: {rectangle}")
        
        summary = "\n".join(summary_parts)
        
        print(f"[工具] 定位成功: {location_str}")
        
        return {
            "success": True,
            "ip": ip if ip else "客户端 IP",
            "province": province,
            "city": city,
            "adcode": adcode,
            "rectangle": rectangle,
            "summary": summary,
            "message": f"成功定位到: {location_str}"
        }
        
    except requests.exceptions.Timeout:
        print("[工具] IP 定位请求超时")
        return {
            "success": False,
            "ip": ip or "未知",
            "province": "",
            "city": "",
            "adcode": "",
            "rectangle": "",
            "summary": "",
            "message": "请求超时，请稍后重试"
        }
    except requests.exceptions.RequestException as e:
        print(f"[工具] IP 定位请求失败: {e}")
        return {
            "success": False,
            "ip": ip or "未知",
            "province": "",
            "city": "",
            "adcode": "",
            "rectangle": "",
            "summary": "",
            "message": f"请求失败: {str(e)}"
        }
    except Exception as e:
        print(f"[工具] IP 定位失败: {e}")
        return {
            "success": False,
            "ip": ip or "未知",
            "province": "",
            "city": "",
            "adcode": "",
            "rectangle": "",
            "summary": "",
            "message": f"定位失败: {str(e)}"
        }


# 工具元信息
ip_location.prompt_template = "default"
ip_location.description = "IP 定位工具，将 IP 地址转换为地理位置信息（省份、城市等）。支持查询指定 IP 或自动获取客户端 IP。仅支持国内 IP 地址"
ip_location.is_admin = False  # 所有用户可用

