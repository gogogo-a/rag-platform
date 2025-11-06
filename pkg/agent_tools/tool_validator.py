"""
工具参数验证和自动修正系统
解决 AI 调用工具时的参数错误问题
"""
from typing import Dict, Any, Callable, Optional, Tuple
import inspect
from loguru import logger
import re

# ==================== 参数别名映射 ====================
# 将 AI 可能使用的错误参数名映射到正确的参数名

PARAM_ALIASES = {
    # web_search 工具
    "web_search": {
        "top_k": "max_results",          # AI 经常混淆 top_k 和 max_results
        "time_range": "search_recency",  # time_range 也是常见错误
        "limit": "max_results",          # limit 也映射到 max_results
        "num": "max_results",            # num 也映射到 max_results
    },
    # poi_search 工具
    "poi_search": {
        "city": "region",                # city 应该是 region
        "location_type": "search_type",  # 类型相关的别名
        "type": "search_type",           # type 映射到 search_type
    },
    # knowledge_search 工具
    "knowledge_search": {
        "max_results": "top_k",          # 反向映射
        "limit": "top_k",
        "num": "top_k",
    },
    # route_planning 工具
    "route_planning": {
        "start": "origin",               # start 映射到 origin
        "end": "destination",            # end 映射到 destination
        "mode": "strategy",              # mode 映射到 strategy
    },
}


# ==================== 参数默认值 ====================
# 为工具提供合理的默认值

PARAM_DEFAULTS = {
    "web_search": {
        "max_results": 5,
        "search_recency": "week",
    },
    "poi_search": {
        "search_type": "text",
        "radius": 5000,
        "page_size": 10,
        "page_num": 1,
    },
    "knowledge_search": {
        "top_k": 5,
    },
    "weather_query": {
        "extensions": "base",
    },
    "route_planning": {
        "strategy": "0",  # 默认最快路线
    },
    "geocode": {
        "extensions": "base",
    },
}


# ==================== 参数验证规则 ====================

PARAM_VALIDATORS = {
    "web_search": {
        "max_results": lambda x: isinstance(x, int) and 1 <= x <= 20,
        "search_recency": lambda x: x in ["day", "week", "month", "year", "all"],
    },
    "poi_search": {
        "search_type": lambda x: x in ["text", "around", "polygon", "detail"],
        "radius": lambda x: isinstance(x, int) and 0 <= x <= 50000,
        "keywords": lambda x: True,  # 总是通过，但会在 _try_correct_value 中处理
    },
    "weather_query": {
        "extensions": lambda x: x in ["base", "all"],
    },
    "route_planning": {
        "strategy": lambda x: str(x) in ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"],
    },
}


# ==================== 参数智能转换规则 ====================
# 某些参数需要特殊处理和智能转换

PARAM_TRANSFORMERS = {
    "poi_search": {
        "keywords": lambda x: _transform_keywords(x),
    },
    "email_sender": {
        "content": lambda x: _unescape_string(x) if x else x,
        "html_content": lambda x: _unescape_string(x) if x else x,
    },
}


def _unescape_string(text: str) -> str:
    """
    将字符串字面量中的转义序列转换为实际字符
    
    AI 在生成工具参数时，可能会输出字面量 "\\n" 而不是换行符。
    此函数将这些字面量转换为实际的转义字符。
    
    Args:
        text: 原始字符串
        
    Returns:
        处理后的字符串
    """
    if not text:
        return text
    
    # 安全地替换转义序列，使用占位符避免重复替换
    import uuid
    
    # 1. 先用唯一占位符保护已转义的反斜杠 \\\\
    placeholder = f"__ESCAPED_BACKSLASH_{uuid.uuid4().hex}__"
    result = text.replace('\\\\', placeholder)
    
    # 2. 替换其他转义序列
    replacements = [
        ('\\n', '\n'),   # 换行符
        ('\\r', '\r'),   # 回车符  
        ('\\t', '\t'),   # 制表符
        ('\\"', '"'),    # 双引号
        ("\\'", "'"),    # 单引号
    ]
    
    for literal, actual in replacements:
        result = result.replace(literal, actual)
    
    # 3. 最后将占位符还原为单个反斜杠
    result = result.replace(placeholder, '\\')
    
    return result


def _transform_keywords(keywords: str) -> str:
    """
    智能转换关键词格式
    
    高德 API 要求：
    - 多个关键词用 "|" 分隔
    - 单个关键词最多 80 字符
    
    Args:
        keywords: 原始关键词字符串
        
    Returns:
        转换后的关键词字符串
    """
    if not keywords:
        return keywords
    
    # 如果已经包含 "|"，说明格式正确
    if "|" in keywords:
        return keywords
    
    # 如果包含空格、逗号、顿号等分隔符，自动转换为 "|"
    separators = [" ", "，", ",", "、", "。", "；", ";"]
    
    result = keywords
    for sep in separators:
        if sep in result:
            # 分割后过滤空字符串，然后用 "|" 连接
            parts = [part.strip() for part in result.split(sep) if part.strip()]
            result = "|".join(parts)
            break
    
    # 限制长度
    if len(result) > 80:
        result = result[:80]
    
    return result


class ToolValidator:
    """工具参数验证器"""
    
    def __init__(self, tool_name: str, tool_func: Callable):
        """
        初始化验证器
        
        Args:
            tool_name: 工具名称
            tool_func: 工具函数
        """
        self.tool_name = tool_name
        self.tool_func = tool_func
        self.signature = inspect.signature(tool_func)
        self.param_names = list(self.signature.parameters.keys())
        
    def normalize_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        标准化参数：修正参数名称、添加默认值、验证参数
        
        Args:
            params: 原始参数字典
            
        Returns:
            标准化后的参数字典
        """
        normalized = {}
        corrections = []  # 记录修正信息
        
        # 1. 参数别名映射（修正错误的参数名）
        aliases = PARAM_ALIASES.get(self.tool_name, {})
        for key, value in params.items():
            if key in aliases:
                correct_key = aliases[key]
                normalized[correct_key] = value
                corrections.append(f"参数名修正: {key} → {correct_key}")
                logger.info(f"[工具验证] {self.tool_name}: 参数名修正 {key} → {correct_key}")
            elif key in self.param_names:
                normalized[key] = value
            else:
                # 未知参数，记录警告但不阻止
                logger.warning(f"[工具验证] {self.tool_name}: 未知参数 {key}，已忽略")
        
        # 1.5. 应用参数智能转换（在别名映射之后）
        transformers = PARAM_TRANSFORMERS.get(self.tool_name, {})
        for key, transformer in transformers.items():
            if key in normalized:
                original_value = normalized[key]
                transformed_value = transformer(original_value)
                
                if transformed_value != original_value:
                    normalized[key] = transformed_value
                    corrections.append(f"参数值转换: {key}")
                    logger.info(f"[工具验证] {self.tool_name}: 参数 {key} 已转换")
        
        # 2. 添加默认值（对于缺失的参数）
        defaults = PARAM_DEFAULTS.get(self.tool_name, {})
        for key, default_value in defaults.items():
            if key not in normalized:
                # 检查是否为必填参数
                param = self.signature.parameters.get(key)
                if param and param.default == inspect.Parameter.empty:
                    # 必填参数，不添加默认值
                    continue
                normalized[key] = default_value
                corrections.append(f"使用默认值: {key}={default_value}")
                logger.info(f"[工具验证] {self.tool_name}: 参数 {key} 使用默认值 {default_value}")
        
        # 3. 参数验证
        validators = PARAM_VALIDATORS.get(self.tool_name, {})
        for key, validator in validators.items():
            if key in normalized:
                value = normalized[key]
                if not validator(value):
                    # 验证失败，尝试修正
                    corrected_value = self._try_correct_value(key, value)
                    if corrected_value is not None:
                        normalized[key] = corrected_value
                        corrections.append(f"参数值修正: {key}={value} → {corrected_value}")
                        logger.warning(f"[工具验证] {self.tool_name}: 参数 {key} 值无效({value})，已修正为 {corrected_value}")
                    else:
                        logger.error(f"[工具验证] {self.tool_name}: 参数 {key} 值无效({value})，且无法自动修正")
        
        # 4. 打印修正摘要
        if corrections:
            logger.info(f"[工具验证] {self.tool_name} 参数已自动修正:")
            for correction in corrections:
                logger.info(f"  - {correction}")
        
        return normalized
    
    def _try_correct_value(self, param_name: str, value: Any) -> Optional[Any]:
        """
        尝试修正无效的参数值
        
        Args:
            param_name: 参数名称
            value: 当前值
            
        Returns:
            修正后的值，如果无法修正则返回 None
        """
        # 特定参数的修正逻辑
        if param_name == "search_recency":
            # 时间范围的常见错误映射
            time_mapping = {
                "day": "day",
                "today": "day",
                "1day": "day",
                "week": "week",
                "1week": "week",
                "month": "month",
                "1month": "month",
                "year": "year",
                "1year": "year",
                "all": "all",
            }
            return time_mapping.get(str(value).lower())
        
        elif param_name == "max_results":
            # 尝试转换为整数并限制范围
            try:
                num = int(value)
                return max(1, min(20, num))
            except (ValueError, TypeError):
                return 5  # 默认值
        
        elif param_name == "radius":
            # 尝试转换为整数并限制范围
            try:
                num = int(value)
                return max(0, min(50000, num))
            except (ValueError, TypeError):
                return 5000  # 默认值
        
        elif param_name == "strategy":
            # 路线规划策略映射
            strategy_mapping = {
                "fastest": "0",
                "shortest": "1",
                "avoid_highway": "2",
                "walking": "1",
                "bicycle": "0",
                "driving": "0",
            }
            return strategy_mapping.get(str(value).lower(), str(value))
        
        return None
    
    def validate_required_params(self, params: Dict[str, Any]) -> Tuple[bool, str]:
        """
        验证必填参数是否齐全
        
        Args:
            params: 参数字典
            
        Returns:
            (is_valid, error_message)
        """
        missing = []
        for param_name, param in self.signature.parameters.items():
            if param.default == inspect.Parameter.empty:
                # 必填参数
                if param_name not in params:
                    missing.append(param_name)
        
        if missing:
            return False, f"缺少必填参数: {', '.join(missing)}"
        
        return True, ""


def validate_and_fix_params(tool_name: str, tool_func: Callable, params: Dict[str, Any]) -> Dict[str, Any]:
    """
    验证并修正工具参数（统一入口）
    
    Args:
        tool_name: 工具名称
        tool_func: 工具函数
        params: 原始参数字典
        
    Returns:
        修正后的参数字典
        
    Raises:
        ValueError: 如果参数验证失败且无法自动修正
    """
    validator = ToolValidator(tool_name, tool_func)
    
    # 标准化参数
    normalized_params = validator.normalize_params(params)
    
    # 特殊处理：email_sender 的 HTML 内容智能检测
    if tool_name == "email_sender" and "content" in normalized_params and normalized_params["content"]:
        content = normalized_params["content"]
        # 检测是否包含 HTML 标签
        has_html = any([
            '<html' in content.lower(),
            '<body' in content.lower(),
            '<div' in content.lower() and '>' in content,
            ('<h1' in content.lower() or '<h2' in content.lower() or '<h3' in content.lower()) and '>' in content,
            '<p>' in content.lower(),
            '<ul>' in content.lower() or '<ol>' in content.lower(),
            '<style' in content.lower(),
            '<!DOCTYPE' in content
        ])
        
        if has_html:
            # 如果已经有 html_content，保留原值；否则移动过去
            if "html_content" not in normalized_params or not normalized_params["html_content"]:
                normalized_params["html_content"] = normalized_params["content"]
                # 生成纯文本备份（简单去除 HTML 标签）
                plain_text = re.sub(r'<[^>]+>', '', normalized_params["content"])
                plain_text = re.sub(r'\s+', ' ', plain_text).strip()
                normalized_params["content"] = plain_text if plain_text else "邮件内容（请查看 HTML 版本）"
    
    # 修正 HTML 属性中的单引号为双引号（邮件客户端兼容性）
    if tool_name == "email_sender" and "html_content" in normalized_params and normalized_params["html_content"]:
        html = normalized_params["html_content"]
        
        # 将 =' ... ' 模式替换为 =" ... "
        if "='" in html:
            try:
                # 匹配 key='value' 模式
                html_fixed = re.sub(r"""(\w+)='([^']*)'""", r'\1="\2"', html)
                if len(html_fixed) >= len(html):
                    normalized_params["html_content"] = html_fixed
            except Exception:
                pass  # 转换失败时保留原内容
    
    # 验证必填参数
    is_valid, error_msg = validator.validate_required_params(normalized_params)
    if not is_valid:
        raise ValueError(f"工具 {tool_name} 参数验证失败: {error_msg}")
    
    return normalized_params

