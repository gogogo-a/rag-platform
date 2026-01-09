"""
问答质量评估服务
异步评估问答是否值得缓存到 QA 库
"""
import asyncio
from typing import Optional, Dict, Any
from log import logger
from pkg.model_list import DEEPSEEK_CHAT
from pkg.constants.constants import ENABLE_QA_CACHE


# 评估提示词
EVALUATION_PROMPT = """你是一个问答质量评估专家。请判断以下用户问题是否值得缓存到知识库中。

评估标准：
1. 知识性问题（如政策、规定、流程、专业知识）→ 值得缓存
2. 具体的业务咨询（如奖学金评定、课程安排、办事流程）→ 值得缓存
3. 简单寒暄（如"你好"、"谢谢"、"再见"）→ 不值得缓存
4. 闲聊对话（如"今天天气怎么样"、"你是谁"）→ 不值得缓存
5. 过于个人化的问题（如"我的成绩怎么样"）→ 不值得缓存
6. 问题太短或太模糊（少于5个字）→ 不值得缓存
7. 实时性问题（答案会随时间变化）→ 不值得缓存，包括：
   - 天气查询（如"今天天气"、"明天会下雨吗"）
   - 时间日期（如"现在几点"、"今天星期几"）
   - 实时新闻/热点（如"最新新闻"、"今天发生了什么"）
   - 股票/汇率/价格（如"黄金价格"、"美元汇率"）
   - 交通路况（如"现在堵车吗"、"路线规划"）
   - 位置查询（如"附近有什么餐厅"、"最近的医院"）

请只回复 "YES" 或 "NO"，不要有任何其他内容。

用户问题：{question}"""


class QAEvaluator:
    """
    问答质量评估器（单例模式）
    
    异步评估问题是否值得缓存，不阻塞主流程
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._pending_evaluations: Dict[str, asyncio.Task] = {}
    
    async def evaluate_question(self, question: str) -> bool:
        """
        评估问题是否值得缓存
        
        Args:
            question: 用户问题
            
        Returns:
            True 表示值得缓存，False 表示不值得
        """
        # 如果未启用 QA 缓存，直接返回 False
        if not ENABLE_QA_CACHE:
            return False
        
        # 快速规则过滤（避免调用 AI）
        if not self._quick_filter(question):
            return False
        
        try:
            from internal.llm.llm_service import LLMService
            
            # 使用轻量模型进行评估
            llm_service = LLMService(
                model_name=DEEPSEEK_CHAT.name,
                model_type=DEEPSEEK_CHAT.model_type,
                auto_summary=False
            )
            
            # 构建评估消息
            prompt = EVALUATION_PROMPT.format(question=question)
            
            # 调用 LLM 评估（非流式，快速返回）
            response = llm_service.chat(
                user_message=prompt,
                stream=False,
                use_history=False
            )
            
            # 解析结果
            result = response.strip().upper()
            should_cache = result == "YES"
            
            logger.debug(f"问答评估: question={question[:30]}..., result={result}, should_cache={should_cache}")
            return should_cache
            
        except Exception as e:
            logger.error(f"问答评估失败: {e}")
            # 评估失败时，默认不缓存
            return False
    
    def _quick_filter(self, question: str) -> bool:
        """
        快速规则过滤，避免不必要的 AI 调用
        
        Args:
            question: 用户问题
            
        Returns:
            True 表示需要进一步 AI 评估，False 表示直接拒绝
        """
        question_lower = question.strip().lower()
        
        # 问题太短
        if len(question_lower) < 5:
            return False
        
        # 简单寒暄词
        greetings = {'你好', '您好', '谢谢', '感谢', '再见', '拜拜', 'hi', 'hello', 'thanks', 'bye'}
        if question_lower in greetings:
            return False
        
        # 以寒暄词开头且很短
        for g in greetings:
            if question_lower.startswith(g) and len(question) < 10:
                return False
        
        # 实时性关键词 - 直接拒绝缓存
        realtime_keywords = [
            '天气', '气温', '下雨', '下雪', '温度',
            '现在几点', '今天星期', '什么时候',
            '股票', '股价', '汇率', '价格', '行情',
            '路况', '堵车', '路线', '导航', '怎么走',
            '附近', '最近的', '周边',
            '最新', '今日', '实时', '当前'
        ]
        for keyword in realtime_keywords:
            if keyword in question_lower:
                logger.debug(f"实时性问题，跳过缓存: {question[:30]}...")
                return False
        
        return True
    
    def start_evaluation(self, question: str, evaluation_id: str) -> asyncio.Task:
        """
        启动异步评估任务
        
        Args:
            question: 用户问题
            evaluation_id: 评估任务ID（通常用 session_id + message_id）
            
        Returns:
            评估任务
        """
        task = asyncio.create_task(self.evaluate_question(question))
        self._pending_evaluations[evaluation_id] = task
        return task
    
    async def get_evaluation_result(self, evaluation_id: str, timeout: float = 5.0) -> bool:
        """
        获取评估结果
        
        Args:
            evaluation_id: 评估任务ID
            timeout: 超时时间（秒）
            
        Returns:
            评估结果，超时或失败返回 False
        """
        task = self._pending_evaluations.get(evaluation_id)
        if not task:
            return False
        
        try:
            result = await asyncio.wait_for(task, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            logger.warning(f"问答评估超时: {evaluation_id}")
            return False
        except Exception as e:
            logger.error(f"获取评估结果失败: {e}")
            return False
        finally:
            # 清理已完成的任务
            self._pending_evaluations.pop(evaluation_id, None)
    
    def cancel_evaluation(self, evaluation_id: str):
        """取消评估任务"""
        task = self._pending_evaluations.pop(evaluation_id, None)
        if task and not task.done():
            task.cancel()


# 创建单例实例
qa_evaluator = QAEvaluator()
