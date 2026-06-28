import asyncio
import unittest

from langchain_core.messages import AIMessage

from internal.agent.langgraph_agent import LangGraphAgent
from internal.service.ai.ai_reply_service import AIReplyService
from pkg.constants.constants import AGENT_TYPE, ENABLE_QA_CACHE


class FakeLLMService:
    def __init__(self, responses, stream_by_char=False):
        self.llm = FakeLLM(responses, stream_by_char=stream_by_char)

    def get_history(self):
        return []


class FakeLLM:
    def __init__(self, responses, stream_by_char=False):
        self.responses = list(responses)
        self.prompts = []
        self.stream_by_char = stream_by_char

    async def ainvoke(self, prompt, config=None):
        self.prompts.append(prompt)
        response = self.responses.pop(0) if self.responses else "Final Answer: 默认回答"
        for callback in (config or {}).get("callbacks", []):
            if hasattr(callback, "on_llm_new_token"):
                if self.stream_by_char:
                    for char in response:
                        callback.on_llm_new_token(char)
                else:
                    callback.on_llm_new_token(response)
        return AIMessage(content=response)


class LangGraphAgentSelfHealingTest(unittest.TestCase):
    def test_default_agent_type_is_langgraph(self):
        self.assertEqual("langgraph", AGENT_TYPE)

    def test_qa_cache_is_disabled_by_default(self):
        self.assertFalse(ENABLE_QA_CACHE)

    def test_ai_reply_service_creates_langgraph_agent_by_default(self):
        service = AIReplyService()
        agent = service._create_agent(FakeLLMService(["Final Answer: 好"]), {}, lambda *_: None)

        self.assertIsInstance(agent, LangGraphAgent)

    def test_empty_search_input_uses_user_question(self):
        calls = []

        async def web_search(tool_input=None, **kwargs):
            calls.append(tool_input)
            return "未找到相关搜索结果"

        agent = LangGraphAgent(
            llm_service=FakeLLMService([
                "Thought: 需要搜索\nAction: web_search\nAction Input: {}",
            ]),
            tools={"web_search": web_search},
            max_iterations=1,
            callback=lambda *_: None,
        )

        asyncio.run(agent.run("我如何自制一个深度学习框架呢"))

        self.assertEqual(["我如何自制一个深度学习框架呢"], calls)

    def test_failed_web_search_does_not_repeat_when_knowledge_result_exists(self):
        calls = []

        async def knowledge_search(tool_input=None, **kwargs):
            calls.append(("knowledge_search", tool_input))
            return (
                '{"context":"《深度学习自制框架》介绍了从零开始用 Python 创建深度学习框架，分 60 个步骤完成。",'
                '"documents":[{"uuid":"doc-1","name":"深度学习自制框架.pdf"}],"results":[]}'
            )

        async def web_search(tool_input=None, **kwargs):
            calls.append(("web_search", tool_input))
            return "未找到相关搜索结果"

        agent = LangGraphAgent(
            llm_service=FakeLLMService([
                "Thought: 先查知识库\nAction: knowledge_search\nAction Input: {}",
                "Thought: 再查网页\nAction: web_search\nAction Input: {}",
                "Thought: 再试一次网页\nAction: web_search\nAction Input: {}",
                "这是一段不该作为最终答案的搜索计划",
            ]),
            tools={"knowledge_search": knowledge_search, "web_search": web_search},
            max_iterations=5,
            callback=lambda *_: None,
        )

        answer = asyncio.run(agent.run("我如何自制一个深度学习框架呢"))

        self.assertEqual(
            [
                ("knowledge_search", "我如何自制一个深度学习框架呢"),
                ("web_search", "我如何自制一个深度学习框架呢"),
            ],
            calls,
        )
        self.assertIn("深度学习自制框架", answer)
        self.assertIn("60 个步骤", answer)
        self.assertNotIn("Thought", answer)
        self.assertNotIn("Action", answer)
        self.assertNotIn("Observation", answer)

    def test_process_sentence_after_tools_is_replaced_by_direct_answer(self):
        events = []

        async def knowledge_search(tool_input=None, **kwargs):
            return (
                '{"context":"《深度学习自制框架》会带领读者从零开始创建 DeZero，'
                '用最少的代码实现现代深度学习框架功能，并分 60 个步骤完成。",'
                '"documents":[{"uuid":"doc-1","name":"深度学习自制框架.pdf"}],"results":[]}'
            )

        agent = LangGraphAgent(
            llm_service=FakeLLMService([
                "Thought: 先查知识库\nAction: knowledge_search\nAction Input: {}",
                "我已经获取到了一些关于自制深度学习框架的文档信息，为了更全面地回答用户的问题，我需要进一步搜索更详细的步骤或教程。",
            ]),
            tools={"knowledge_search": knowledge_search},
            max_iterations=3,
            callback=lambda event_type, content: events.append((event_type, content)),
        )

        answer = asyncio.run(agent.run("我如何自制一个深度学习框架呢"))
        final_answer_events = [content for event_type, content in events if event_type == "final_answer"]

        self.assertIn("深度学习自制框架", answer)
        self.assertIn("60 个步骤", answer)
        self.assertNotIn("进一步搜索", answer)
        self.assertTrue(final_answer_events)
        self.assertIn("深度学习自制框架", final_answer_events[-1])

    def test_final_answer_after_tools_is_sent_once_after_cleaning(self):
        events = []

        async def knowledge_search(tool_input=None, **kwargs):
            return '{"context":"DeZero 通过 60 个步骤自制深度学习框架。","documents":[],"results":[]}'

        streamed_answer = "Final Answer: 要自制一个深度学习框架，可以从自动微分开始。"
        agent = LangGraphAgent(
            llm_service=FakeLLMService([
                "Thought: 先查资料\nAction: knowledge_search\nAction Input: {}",
                streamed_answer,
            ]),
            tools={"knowledge_search": knowledge_search},
            max_iterations=3,
            callback=lambda event_type, content: events.append((event_type, content)),
        )

        answer = asyncio.run(agent.run("我如何自制一个深度学习框架呢"))
        final_answer_events = [content for event_type, content in events if event_type == "final_answer"]

        self.assertEqual("要自制一个深度学习框架，可以从自动微分开始。", answer)
        self.assertEqual(["要自制一个深度学习框架，可以从自动微分开始。"], final_answer_events)

    def test_finalize_summary_is_cleaned_before_callback(self):
        events = []

        async def knowledge_search(tool_input=None, **kwargs):
            return '{"context":"DeZero 通过 60 个步骤自制深度学习框架。","documents":[],"results":[]}'

        agent = LangGraphAgent(
            llm_service=FakeLLMService([
                "Thought: 先查资料\nAction: knowledge_search\nAction Input: {}",
                "我先整理一下答案。\n\nFinal Answer: 要自制一个深度学习框架，可以从自动微分、计算图、张量对象和优化器开始。",
            ]),
            tools={"knowledge_search": knowledge_search},
            max_iterations=3,
            callback=lambda event_type, content: events.append((event_type, content)),
        )

        answer = asyncio.run(agent.run("我如何自制一个深度学习框架呢"))
        final_answer_events = [content for event_type, content in events if event_type == "final_answer"]

        self.assertEqual("要自制一个深度学习框架，可以从自动微分、计算图、张量对象和优化器开始。", answer)
        self.assertEqual(["要自制一个深度学习框架，可以从自动微分、计算图、张量对象和优化器开始。"], final_answer_events)
        self.assertNotIn("Final Answer", final_answer_events[0])
        self.assertNotIn("我先整理", final_answer_events[0])

    def test_final_answer_after_tools_streams_only_answer_chunks(self):
        events = []

        async def knowledge_search(tool_input=None, **kwargs):
            return '{"context":"DeZero 通过 60 个步骤自制深度学习框架。","documents":[],"results":[]}'

        agent = LangGraphAgent(
            llm_service=FakeLLMService([
                "Thought: 先查资料\nAction: knowledge_search\nAction Input: {}",
                "我先整理检索结果。\nFinal Answer: 要自制一个深度学习框架，先实现自动微分，再实现优化器。",
            ], stream_by_char=True),
            tools={"knowledge_search": knowledge_search},
            max_iterations=3,
            callback=lambda event_type, content: events.append((event_type, content)),
        )

        answer = asyncio.run(agent.run("我如何自制一个深度学习框架呢"))
        action_index = next(index for index, event in enumerate(events) if event[0] == "action")
        answer_chunks = [
            content
            for event_type, content in events[action_index + 1:]
            if event_type == "llm_chunk"
        ]

        self.assertEqual("要自制一个深度学习框架，先实现自动微分，再实现优化器。", answer)
        self.assertGreater(len(answer_chunks), 1)
        streamed_text = "".join(answer_chunks)
        self.assertEqual(answer, streamed_text)
        self.assertNotIn("我先整理", streamed_text)
        self.assertNotIn("Final Answer", streamed_text)

    def test_tool_action_and_observation_are_emitted_as_agent_processes(self):
        events = []

        async def knowledge_search(tool_input=None, **kwargs):
            return '{"context":"DeZero 通过 60 个步骤自制深度学习框架。","documents":[],"results":[]}'

        agent = LangGraphAgent(
            llm_service=FakeLLMService([
                "Thought: 先查资料\nAction: knowledge_search\nAction Input: {}",
                "Final Answer: 要自制一个深度学习框架，可以从自动微分开始。",
            ]),
            tools={"knowledge_search": knowledge_search},
            max_iterations=3,
            callback=lambda event_type, content: events.append((event_type, content)),
        )

        asyncio.run(agent.run("我如何自制一个深度学习框架呢"))
        process_events = [
            content for event_type, content in events if event_type == "agent_process"
        ]

        self.assertEqual(
            ["action", "observation"],
            [event["phase"] for event in process_events],
        )
        self.assertEqual({"single"}, {event["scope"] for event in process_events})
        self.assertIn("knowledge_search", process_events[0]["content"])
        self.assertIn("DeZero", process_events[1]["content"])


if __name__ == "__main__":
    unittest.main()
