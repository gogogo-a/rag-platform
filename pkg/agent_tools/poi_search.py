"""
POI 地点搜索工具
支持关键字搜索、周边搜索、多边形区域搜索、ID 搜索（使用高德地图 API）
"""
from typing import Dict, Any, Optional, List
import requests


def _format_poi_info(poi: Dict) -> str:
    """格式化单个 POI 信息"""
    name = poi.get("name", "未知")
    address = poi.get("address", "")
    location = poi.get("location", "")
    type_name = poi.get("type", "")
    tel = poi.get("tel", "")
    
    info_parts = [f"📍 {name}"]
    
    if address:
        info_parts.append(f"   地址: {address}")
    if location:
        info_parts.append(f"   坐标: {location}")
    if type_name:
        info_parts.append(f"   类型: {type_name}")
    if tel:
        info_parts.append(f"   电话: {tel}")
    
    # 商业信息（如果有）
    business_area = poi.get("business_area", "")
    rating = poi.get("rating", "")
    cost = poi.get("cost", "")
    
    if business_area:
        info_parts.append(f"   商圈: {business_area}")
    if rating:
        info_parts.append(f"   评分: {rating}")
    if cost:
        info_parts.append(f"   人均: {cost}元")
    
    return "\n".join(info_parts)


def poi_search(
    search_type: str = "text",
    keywords: Optional[str] = None,
    location: Optional[str] = None,
    radius: int = 5000,
    polygon: Optional[str] = None,
    poi_id: Optional[str] = None,
    types: Optional[str] = None,
    region: Optional[str] = None,
    city_limit: bool = False,
    page_size: int = 10,
    page_num: int = 1
) -> Dict[str, Any]:
    """
    POI 地点搜索工具（高德地图）
    支持多种搜索方式：关键字、周边、多边形区域、ID 搜索
    
    Args:
        search_type: 搜索类型
            - "text": 关键字搜索（默认）
            - "around": 周边搜索
            - "polygon": 多边形区域搜索
            - "detail": ID 搜索
        
        keywords: 搜索关键字（如："肯德基"、"北京大学"）
            - text/around/polygon 搜索时可用
            - 只支持一个关键字，最多 80 字符
        
        location: 中心点坐标（格式："经度,纬度"，如："116.473168,39.993015"）
            - around 搜索时必填
            
        radius: 搜索半径（米）
            - around 搜索时使用
            - 范围：0-50000，默认 5000
        
        polygon: 多边形区域坐标（格式："经度1,纬度1|经度2,纬度2|..."）
            - polygon 搜索时必填
            - 首尾坐标需相同（矩形除外）
        
        poi_id: POI ID（如："B000A7BM4H"）
            - detail 搜索时必填
            - 支持多个 ID，用"|"分隔，最多 10 个
        
        types: POI 类型（如："050301" 表示快餐店）
            - 可选，多个类型用"|"分隔
            - 参考 POI 分类码表
        
        region: 搜索区域（如："北京市"）
            - text 搜索时可用
            - 可输入城市名、citycode 或 adcode
        
        city_limit: 是否严格限制在区域内
            - 配合 region 使用
            - True: 仅返回区域内结果
        
        page_size: 每页数量（1-25，默认 10）
        page_num: 页码（默认 1）
        
    Returns:
        Dict: 搜索结果
            - success: 是否成功
            - count: 结果数量
            - pois: POI 列表
            - summary: 格式化的摘要
            
    示例:
        # 关键字搜索：搜索北京的肯德基
        result = poi_search(
            search_type="text",
            keywords="肯德基",
            region="北京市"
        )
        
        # 周边搜索：搜索附近的餐厅
        result = poi_search(
            search_type="around",
            location="116.473168,39.993015",
            radius=1000,
            types="050000"
        )
        
        # ID 搜索：根据 POI ID 查询详情
        result = poi_search(
            search_type="detail",
            poi_id="B000A7BM4H"
        )
    """
    try:
        from pkg.constants.constants import GAODE_API_KEY
        
        if not GAODE_API_KEY:
            return {
                "success": False,
                "count": 0,
                "pois": [],
                "summary": "",
                "message": "POI 搜索功能未配置（缺少 GAODE_API_KEY）"
            }
        
        # 根据搜索类型选择 API 端点
        endpoints = {
            "text": "https://restapi.amap.com/v5/place/text",
            "around": "https://restapi.amap.com/v5/place/around",
            "polygon": "https://restapi.amap.com/v5/place/polygon",
            "detail": "https://restapi.amap.com/v5/place/detail"
        }
        
        if search_type not in endpoints:
            return {
                "success": False,
                "count": 0,
                "pois": [],
                "summary": "",
                "message": f"不支持的搜索类型: {search_type}"
            }
        
        url = endpoints[search_type]
        
        print(f"[工具] POI 搜索: 类型={search_type}, 关键字={keywords or '无'}")
        
        # 构建请求参数
        params = {
            "key": GAODE_API_KEY,
            "output": "json",
            "show_fields": "business,photos,navi"  # 请求详细信息
        }
        
        # 根据搜索类型设置参数
        if search_type == "text":
            if not keywords and not types:
                return {
                    "success": False,
                    "count": 0,
                    "pois": [],
                    "summary": "",
                    "message": "关键字搜索需要提供 keywords 或 types 参数"
                }
            if keywords:
                params["keywords"] = keywords
            if types:
                params["types"] = types
            if region:
                params["region"] = region
            if city_limit:
                params["city_limit"] = "true"
            params["page_size"] = page_size
            params["page_num"] = page_num
            
        elif search_type == "around":
            if not location:
                return {
                    "success": False,
                    "count": 0,
                    "pois": [],
                    "summary": "",
                    "message": "周边搜索需要提供 location 参数（中心点坐标）"
                }
            params["location"] = location
            params["radius"] = radius
            if keywords:
                params["keywords"] = keywords
            if types:
                params["types"] = types
            if region:
                params["region"] = region
            if city_limit:
                params["city_limit"] = "true"
            params["page_size"] = page_size
            params["page_num"] = page_num
            
        elif search_type == "polygon":
            if not polygon:
                return {
                    "success": False,
                    "count": 0,
                    "pois": [],
                    "summary": "",
                    "message": "多边形搜索需要提供 polygon 参数（多边形坐标）"
                }
            params["polygon"] = polygon
            if keywords:
                params["keywords"] = keywords
            if types:
                params["types"] = types
            params["page_size"] = page_size
            params["page_num"] = page_num
            
        elif search_type == "detail":
            if not poi_id:
                return {
                    "success": False,
                    "count": 0,
                    "pois": [],
                    "summary": "",
                    "message": "ID 搜索需要提供 poi_id 参数"
                }
            params["id"] = poi_id
        
        # 发送请求
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # 解析响应
        data = response.json()
        
        # 检查返回状态
        if data.get("status") != "1":
            error_msg = data.get("info", "未知错误")
            print(f"[工具] POI 搜索失败: {error_msg}")
            return {
                "success": False,
                "count": 0,
                "pois": [],
                "summary": "",
                "message": f"搜索失败: {error_msg}"
            }
        
        # 提取 POI 列表
        pois = data.get("pois", [])
        count = int(data.get("count", 0))
        
        if count == 0:
            return {
                "success": False,
                "count": 0,
                "pois": [],
                "summary": "",
                "message": "未找到符合条件的 POI"
            }
        
        # 格式化摘要
        search_desc = {
            "text": f"关键字搜索: {keywords or types}",
            "around": f"周边搜索: {location} 半径 {radius}米",
            "polygon": "多边形区域搜索",
            "detail": f"ID 搜索: {poi_id}"
        }
        
        summary_parts = [
            f"🔍 {search_desc[search_type]}",
            f"📊 找到 {count} 个结果\n"
        ]
        
        # 显示前 5 个 POI 详情
        for i, poi in enumerate(pois[:5], 1):
            summary_parts.append(f"【{i}】{_format_poi_info(poi)}")
            summary_parts.append("")  # 空行
        
        if count > 5:
            summary_parts.append(f"... 还有 {count - 5} 个结果")
        
        summary = "\n".join(summary_parts).strip()
        
        print(f"[工具] 搜索成功: 找到 {count} 个 POI")
        
        return {
            "success": True,
            "count": count,
            "pois": pois,
            "summary": summary,
            "message": f"成功找到 {count} 个 POI"
        }
        
    except requests.exceptions.Timeout:
        print("[工具] POI 搜索请求超时")
        return {
            "success": False,
            "count": 0,
            "pois": [],
            "summary": "",
            "message": "请求超时，请稍后重试"
        }
    except requests.exceptions.RequestException as e:
        print(f"[工具] POI 搜索请求失败: {e}")
        return {
            "success": False,
            "count": 0,
            "pois": [],
            "summary": "",
            "message": f"请求失败: {str(e)}"
        }
    except Exception as e:
        print(f"[工具] POI 搜索失败: {e}")
        return {
            "success": False,
            "count": 0,
            "pois": [],
            "summary": "",
            "message": f"搜索失败: {str(e)}"
        }


# 工具元信息
poi_search.prompt_template = "default"
poi_search.description = """POI 地点搜索工具，支持 4 种搜索方式：
1. 关键字搜索：通过地点名称或地址搜索（如："北京大学"、"肯德基"）
2. 周边搜索：搜索指定坐标周边的地点（需提供中心点坐标和搜索半径）
3. 多边形区域搜索：搜索多边形区域内的地点（需提供多边形坐标点）
4. ID 搜索：根据已知的 POI ID 查询详细信息

返回结果包括：名称、地址、坐标、联系电话、评分、营业时间等详细信息"""
poi_search.is_admin = False  # 所有用户可用

