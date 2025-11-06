"""
地理编码/逆地理编码工具
支持地址与经纬度之间的相互转换（使用高德地图 API）
"""
from typing import Dict, Any, Optional
import requests


def geocode(
    address: Optional[str] = None,
    location: Optional[str] = None,
    city: Optional[str] = None,
    extensions: str = "base"
) -> Dict[str, Any]:
    """
    地理编码/逆地理编码工具（高德地图）
    支持地址与经纬度之间的相互转换
    
    Args:
        address: 结构化地址信息（地理编码时使用）
            - 规则：国家、省份、城市、区县、城镇、乡村、街道、门牌号码
            - 示例："北京市朝阳区阜通东大街6号"、"天安门"
            - 如果提供此参数，执行 地理编码（地址 → 坐标）
        
        location: 经纬度坐标（逆地理编码时使用）
            - 格式："经度,纬度"（注意：经度在前，纬度在后）
            - 示例："116.481488,39.990464"
            - 如果提供此参数，执行 逆地理编码（坐标 → 地址）
        
        city: 指定查询的城市（地理编码时可选）
            - 可选内容：城市中文（如"北京"）、全拼（beijing）、citycode（010）、adcode（110000）
            - 不指定时，会进行全国范围内的检索
        
        extensions: 返回结果控制（逆地理编码时使用）
            - "base"：返回基本地址信息（默认）
            - "all"：返回基本地址 + 附近POI + 道路信息 + 道路交叉口
    
    Returns:
        Dict: 转换结果
            - success: 是否成功
            - type: 转换类型（"geo" 或 "regeo"）
            - result: 转换结果数据
            - summary: 格式化的结果摘要
    
    示例:
        # 地理编码：地址 → 坐标
        result = geocode(address="北京市朝阳区阜通东大街6号")
        result = geocode(address="天安门", city="北京")
        
        # 逆地理编码：坐标 → 地址
        result = geocode(location="116.481488,39.990464")
        result = geocode(location="116.481488,39.990464", extensions="all")
    """
    try:
        from pkg.constants.constants import GAODE_API_KEY
        
        if not GAODE_API_KEY:
            return {
                "success": False,
                "type": "unknown",
                "result": {},
                "summary": "",
                "message": "地理编码功能未配置（缺少 GAODE_API_KEY）"
            }
        
        # 判断是地理编码还是逆地理编码
        if address:
            # 地理编码：地址 → 坐标
            return _geocode_address(address, city, GAODE_API_KEY)
        elif location:
            # 逆地理编码：坐标 → 地址
            return _geocode_location(location, extensions, GAODE_API_KEY)
        else:
            return {
                "success": False,
                "type": "unknown",
                "result": {},
                "summary": "",
                "message": "请提供 address（地址）或 location（坐标）参数"
            }
        
    except Exception as e:
        print(f"[工具] 地理编码失败: {e}")
        return {
            "success": False,
            "type": "unknown",
            "result": {},
            "summary": "",
            "message": f"转换失败: {str(e)}"
        }


def _geocode_address(address: str, city: Optional[str], api_key: str) -> Dict[str, Any]:
    """
    地理编码：将地址转换为坐标
    
    Args:
        address: 结构化地址
        city: 指定城市（可选）
        api_key: 高德 API Key
    
    Returns:
        转换结果
    """
    try:
        print(f"[工具] 地理编码: 地址='{address}', 城市='{city or '全国'}'")
        
        # 构建请求 URL
        url = "https://restapi.amap.com/v3/geocode/geo"
        
        params = {
            "key": api_key,
            "address": address,
            "output": "json"
        }
        
        # 如果指定了城市，添加到参数
        if city:
            params["city"] = city
        
        # 发送请求
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # 解析响应
        data = response.json()
        
        # 检查返回状态
        if data.get("status") != "1":
            error_msg = data.get("info", "未知错误")
            print(f"[工具] 地理编码失败: {error_msg}")
            return {
                "success": False,
                "type": "geo",
                "result": {},
                "summary": "",
                "message": f"转换失败: {error_msg}"
            }
        
        # 提取地理编码结果
        geocodes = data.get("geocodes", [])
        count = int(data.get("count", 0))
        
        if count == 0:
            return {
                "success": False,
                "type": "geo",
                "result": {},
                "summary": "",
                "message": "未找到匹配的地址"
            }
        
        # 取第一个结果（最佳匹配）
        geo = geocodes[0]
        
        location = geo.get("location", "")
        formatted_address = geo.get("formatted_address", "")
        province = geo.get("province", "")
        city_name = geo.get("city", "")
        district = geo.get("district", "")
        level = geo.get("level", "")
        
        # 格式化摘要
        summary_parts = [
            f"📍 地址: {address}",
            f"🎯 坐标: {location}",
            f"📮 完整地址: {formatted_address}",
        ]
        
        if province:
            summary_parts.append(f"🏛️ 省份: {province}")
        if city_name:
            summary_parts.append(f"🏙️ 城市: {city_name}")
        if district:
            summary_parts.append(f"🏘️ 区县: {district}")
        if level:
            summary_parts.append(f"🎚️ 匹配级别: {level}")
        
        summary = "\n".join(summary_parts)
        
        print(f"[工具] 地理编码成功: {location}")
        
        return {
            "success": True,
            "type": "geo",
            "result": {
                "location": location,
                "formatted_address": formatted_address,
                "province": province,
                "city": city_name,
                "district": district,
                "level": level,
                "geocode": geo  # 完整的地理编码数据
            },
            "summary": summary,
            "message": f"成功将地址转换为坐标: {location}"
        }
        
    except requests.exceptions.Timeout:
        print("[工具] 地理编码请求超时")
        return {
            "success": False,
            "type": "geo",
            "result": {},
            "summary": "",
            "message": "请求超时，请稍后重试"
        }
    except requests.exceptions.RequestException as e:
        print(f"[工具] 地理编码请求失败: {e}")
        return {
            "success": False,
            "type": "geo",
            "result": {},
            "summary": "",
            "message": f"请求失败: {str(e)}"
        }


def _geocode_location(location: str, extensions: str, api_key: str) -> Dict[str, Any]:
    """
    逆地理编码：将坐标转换为地址
    
    Args:
        location: 经纬度坐标
        extensions: 返回结果控制（base/all）
        api_key: 高德 API Key
    
    Returns:
        转换结果
    """
    try:
        print(f"[工具] 逆地理编码: 坐标='{location}', extensions='{extensions}'")
        
        # 构建请求 URL
        url = "https://restapi.amap.com/v3/geocode/regeo"
        
        params = {
            "key": api_key,
            "location": location,
            "extensions": extensions,
            "output": "json"
        }
        
        # 发送请求
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # 解析响应
        data = response.json()
        
        # 检查返回状态
        if data.get("status") != "1":
            error_msg = data.get("info", "未知错误")
            print(f"[工具] 逆地理编码失败: {error_msg}")
            return {
                "success": False,
                "type": "regeo",
                "result": {},
                "summary": "",
                "message": f"转换失败: {error_msg}"
            }
        
        # 提取逆地理编码结果
        regeocode = data.get("regeocode", {})
        
        if not regeocode:
            return {
                "success": False,
                "type": "regeo",
                "result": {},
                "summary": "",
                "message": "未找到对应的地址信息"
            }
        
        formatted_address = regeocode.get("formatted_address", "")
        address_component = regeocode.get("addressComponent", {})
        
        province = address_component.get("province", "")
        city = address_component.get("city", "")
        district = address_component.get("district", "")
        township = address_component.get("township", "")
        street = address_component.get("streetNumber", {}).get("street", "")
        number = address_component.get("streetNumber", {}).get("number", "")
        
        # 格式化摘要
        summary_parts = [
            f"📍 坐标: {location}",
            f"📮 地址: {formatted_address}",
        ]
        
        if province:
            summary_parts.append(f"🏛️ 省份: {province}")
        if city:
            summary_parts.append(f"🏙️ 城市: {city}")
        if district:
            summary_parts.append(f"🏘️ 区县: {district}")
        if township:
            summary_parts.append(f"🏡 乡镇/街道: {township}")
        if street:
            summary_parts.append(f"🛣️ 街道: {street}")
        if number:
            summary_parts.append(f"🏠 门牌号: {number}")
        
        # 如果是 all 模式，添加附近 POI 信息
        if extensions == "all":
            pois = regeocode.get("pois", [])
            if pois:
                summary_parts.append(f"\n📌 附近 POI ({len(pois)}个):")
                for i, poi in enumerate(pois[:3], 1):  # 只显示前3个
                    poi_name = poi.get("name", "")
                    poi_type = poi.get("type", "")
                    poi_distance = poi.get("distance", "")
                    summary_parts.append(f"  {i}. {poi_name} ({poi_type}) - {poi_distance}米")
                if len(pois) > 3:
                    summary_parts.append(f"  ... 还有 {len(pois) - 3} 个 POI")
        
        summary = "\n".join(summary_parts)
        
        print(f"[工具] 逆地理编码成功: {formatted_address}")
        
        return {
            "success": True,
            "type": "regeo",
            "result": {
                "formatted_address": formatted_address,
                "province": province,
                "city": city,
                "district": district,
                "township": township,
                "street": street,
                "number": number,
                "regeocode": regeocode  # 完整的逆地理编码数据
            },
            "summary": summary,
            "message": f"成功将坐标转换为地址: {formatted_address}"
        }
        
    except requests.exceptions.Timeout:
        print("[工具] 逆地理编码请求超时")
        return {
            "success": False,
            "type": "regeo",
            "result": {},
            "summary": "",
            "message": "请求超时，请稍后重试"
        }
    except requests.exceptions.RequestException as e:
        print(f"[工具] 逆地理编码请求失败: {e}")
        return {
            "success": False,
            "type": "regeo",
            "result": {},
            "summary": "",
            "message": f"请求失败: {str(e)}"
        }


# 工具元信息
geocode.prompt_template = "default"
geocode.description = """地理编码/逆地理编码工具，支持地址与经纬度之间的相互转换。
1. 地理编码（地址 → 坐标）：将结构化地址转换为高德经纬度坐标，支持地标性建筑解析
2. 逆地理编码（坐标 → 地址）：将经纬度转换为详细地址，可返回附近POI、道路等信息

使用场景：
- 查询某个地址的具体坐标位置
- 将GPS坐标转换为可读的地址信息
- 配合 POI 搜索、路线规划等工具使用"""
geocode.is_admin = False  # 所有用户可用

