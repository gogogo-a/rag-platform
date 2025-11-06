"""
MongoDB 查询工具
在 MongoDB 数据库中执行查询操作（仅支持读取，不支持写入/删除）
"""
from typing import Dict, Any, Optional
import json
from pymongo import MongoClient
from bson import ObjectId


def mongodb_query(
    collection: str,
    filter: str = "{}",
    limit: int = 10,
    projection: Optional[str] = None,
    sort: Optional[str] = None
) -> Dict[str, Any]:
    """
    MongoDB 查询工具
    在指定集合中执行查询操作（仅支持读取）
    
    Args:
        collection: 集合名称（可选：documents, message, user_info, session）
        filter: 查询条件（JSON 字符串格式），例如：'{"name": "张三"}' 或 '{"age": {"$gt": 18}}'
        limit: 返回结果数量限制（默认10，最大100）
        projection: 投影字段（JSON 字符串格式），例如：'{"name": 1, "age": 1}'，不指定则返回所有字段
        sort: 排序条件（JSON 字符串格式），例如：'{"created_at": -1}'（-1降序，1升序）
        
    Returns:
        Dict: 包含查询结果的字典
            - success: 是否成功
            - results: 查询结果列表
            - count: 结果数量
            - collection: 查询的集合名称
            - message: 错误信息（如果失败）
            
    Example:
        # 查询所有文档
        mongodb_query(collection="documents", filter="{}", limit=5)
        
        # 查询特定用户
        mongodb_query(collection="user_info", filter='{"username": "admin"}')
        
        # 复杂查询：查询创建时间大于某个时间的消息
        mongodb_query(
            collection="message",
            filter='{"created_at": {"$gt": "2024-01-01"}}',
            sort='{"created_at": -1}',
            limit=20
        )
    """
    try:
        # 验证集合名称（安全检查）
        allowed_collections = ["documents", "message", "user_info", "session"]
        if collection not in allowed_collections:
            return {
                "success": False,
                "results": [],
                "count": 0,
                "collection": collection,
                "message": f"不支持的集合名称: {collection}。允许的集合: {', '.join(allowed_collections)}"
            }
        
        # 限制查询数量，防止查询过多数据
        limit = min(max(1, int(limit)), 100)  # 限制在 1-100 之间
        
        # 解析 filter（JSON 字符串 → 字典）
        try:
            print(f"[调试] 接收到的 filter 参数: {repr(filter)}")
            print(f"[调试] filter 类型: {type(filter)}")
            
            # 智能处理：如果包含字面量 \"（反斜杠+双引号），说明是错误的转义格式
            # 例如：{\"is_admin\": 1} 应该是 {"is_admin": 1}
            if '\\' in filter and '"' in filter:
                # 检查是否有 \" 模式
                if '\\"' in filter:
                    # 移除多余的转义：\" → "
                    filter = filter.replace('\\"', '"')
                    print(f"[调试] 移除转义后的 filter: {repr(filter)}")
            
            filter_dict = json.loads(filter)
        except json.JSONDecodeError as e:
            print(f"[调试] JSON 解析失败: {e}")
            print(f"[调试] 尝试的 filter 字符串: {repr(filter)}")
            return {
                "success": False,
                "results": [],
                "count": 0,
                "collection": collection,
                "message": f"filter 参数格式错误（需要 JSON 字符串）: {e}"
            }
        
        # 解析 projection（可选）
        projection_dict = None
        if projection:
            try:
                # 智能处理转义
                if '\\' in projection and '"' in projection and '\\"' in projection:
                    projection = projection.replace('\\"', '"')
                projection_dict = json.loads(projection)
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "results": [],
                    "count": 0,
                    "collection": collection,
                    "message": f"projection 参数格式错误（需要 JSON 字符串）: {e}"
                }
        
        # 解析 sort（可选）
        sort_list = None
        if sort:
            try:
                # 智能处理转义
                if '\\' in sort and '"' in sort and '\\"' in sort:
                    sort = sort.replace('\\"', '"')
                sort_dict = json.loads(sort)
                # MongoDB Motor 的 sort 需要列表格式：[("field", 1), ...]
                sort_list = [(k, v) for k, v in sort_dict.items()]
            except json.JSONDecodeError as e:
                return {
                    "success": False,
                    "results": [],
                    "count": 0,
                    "collection": collection,
                    "message": f"sort 参数格式错误（需要 JSON 字符串）: {e}"
                }
        
        print(f"[工具] MongoDB 查询: 集合={collection}, filter={filter}, limit={limit}")
        
        # 执行同步查询（使用 pymongo 避免事件循环冲突）
        from pkg.constants.constants import MONGODB_URL, MONGODB_DATABASE
        
        # 创建同步 MongoDB 客户端（连接会自动管理）
        client = MongoClient(MONGODB_URL)
        
        try:
            # 获取数据库和集合
            db = client[MONGODB_DATABASE]
            coll = db[collection]
            
            # 构建查询（pymongo 的 projection 作为 find 的第二个参数）
            if projection_dict:
                cursor = coll.find(filter_dict, projection_dict)
            else:
                cursor = coll.find(filter_dict)
            
            # 应用排序（链式调用）
            if sort_list:
                cursor = cursor.sort(sort_list)
            
            # 限制数量（链式调用）
            cursor = cursor.limit(limit)
            
            # 执行查询并转换为列表
            results = list(cursor)
            
            # 转换 ObjectId 为字符串（JSON 序列化需要）
            for result in results:
                if '_id' in result:
                    result['_id'] = str(result['_id'])
            
        finally:
            # 关闭客户端连接
            client.close()
        
        # 构建类似 MySQL 的表格形式返回（完整数据）
        if results:
            # 获取所有字段名（从第一条记录）
            if results:
                all_fields = list(results[0].keys())
                # 排除 _id，把它放到最后（如果存在）
                fields = [f for f in all_fields if f != '_id']
                if '_id' in all_fields:
                    fields.append('_id')
                
                # 构建表格
                table_lines = []
                table_lines.append(f"查询成功，返回 {len(results)} 条记录")
                table_lines.append("")
                
                # 计算每列的最大宽度（用于对齐）
                col_widths = {}
                for field in fields:
                    # 字段名长度
                    max_width = len(field)
                    # 检查所有值的长度
                    for result in results:
                        value_str = str(result.get(field, ''))
                        # 限制单个字段最大显示长度
                        if len(value_str) > 50:
                            value_str = value_str[:47] + '...'
                        max_width = max(max_width, len(value_str))
                    col_widths[field] = min(max_width, 50)  # 最大50字符
                
                # 表头
                header = "| " + " | ".join(f"{field:<{col_widths[field]}}" for field in fields) + " |"
                separator = "|-" + "-|-".join("-" * col_widths[field] for field in fields) + "-|"
                
                table_lines.append(header)
                table_lines.append(separator)
                
                # 数据行
                for result in results:
                    row_values = []
                    for field in fields:
                        value = result.get(field, '')
                        value_str = str(value)
                        # 截断过长的值
                        if len(value_str) > 50:
                            value_str = value_str[:47] + '...'
                        row_values.append(f"{value_str:<{col_widths[field]}}")
                    
                    row = "| " + " | ".join(row_values) + " |"
                    table_lines.append(row)
                
                message = "\n".join(table_lines)
            else:
                message = f"查询成功，返回 {len(results)} 条记录"
        else:
            message = f"查询成功，但未找到符合条件的记录"
        
        print(f"[工具] MongoDB 查询成功: 返回 {len(results)} 条记录")
        
        return {
            "success": True,
            "results": results,
            "count": len(results),
            "collection": collection,
            "message": message
        }
        
    except Exception as e:
        error_msg = f"MongoDB 查询失败: {str(e)}"
        print(f"[工具] {error_msg}")
        return {
            "success": False,
            "results": [],
            "count": 0,
            "collection": collection,
            "message": error_msg
        }


# 工具元数据（用于 Agent 注册）
TOOL_METADATA = {
    "name": "mongodb_query",
    "description": "在 MongoDB 数据库中查询数据（仅支持读取操作）",
    "parameters": {
        "collection": {
            "type": "string",
            "description": "集合名称（可选：documents, message, user_info, session）",
            "required": True
        },
        "filter": {
            "type": "string",
            "description": "查询条件（JSON 字符串），例如：'{\"name\": \"张三\"}' 或 '{\"age\": {\"$gt\": 18}}'，空条件用 '{}'",
            "required": False,
            "default": "{}"
        },
        "limit": {
            "type": "integer",
            "description": "返回结果数量（默认10，最大100）",
            "required": False,
            "default": 10
        },
        "projection": {
            "type": "string",
            "description": "投影字段（JSON 字符串），例如：'{\"name\": 1, \"age\": 1}'，不指定则返回所有字段",
            "required": False
        },
        "sort": {
            "type": "string",
            "description": "排序条件（JSON 字符串），例如：'{\"created_at\": -1}'（-1降序，1升序）",
            "required": False
        }
    }
}

