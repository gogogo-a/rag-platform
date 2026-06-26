import unittest

from langchain_core.exceptions import OutputParserException
from langchain_core.agents import AgentFinish

from internal.agent.react_agent import TolerantReActOutputParser


class TolerantReActOutputParserTest(unittest.TestCase):
    def test_plain_answer_is_treated_as_final_answer(self):
        parser = TolerantReActOutputParser()

        parsed = parser.parse("根据知识库信息，耿浩的实习经历包括 AI 产品后台管理系统及官网建设。")

        self.assertIsInstance(parsed, AgentFinish)
        self.assertIn("耿浩的实习经历", parsed.return_values["output"])

    def test_incomplete_action_trace_is_not_treated_as_final_answer(self):
        parser = TolerantReActOutputParser()

        with self.assertRaises(OutputParserException):
            parser.parse(
                "用户想了解如何自制一个深度学习框架，这是一个技术性较强的问题。我需要从知识库或网络中搜索相关资料来提供详细指导。\n\nAction"
            )

    def test_search_intent_text_is_not_treated_as_final_answer(self):
        parser = TolerantReActOutputParser()

        with self.assertRaises(OutputParserException):
            parser.parse(
                "用户想了解如何自制一个深度学习框架，需要提供系统性的指导。我可以先搜索知识库中是否有相关文档，同时也可以搜索网页获取最新资料。"
            )


if __name__ == "__main__":
    unittest.main()


class MCPToolInputNormalizerTest(unittest.TestCase):
    def test_weather_query_extracts_json_wrapped_inside_query(self):
        from pkg.agent_tools_mcp.mcp_manager import normalize_mcp_tool_arguments

        args = normalize_mcp_tool_arguments(
            "weather_query",
            {
                "query": '** {"city": "北京", "extensions": "all"}'
            },
        )

        self.assertEqual({"city": "北京", "extensions": "all"}, args)

    def test_weather_query_uses_beijing_from_plain_text_query(self):
        from pkg.agent_tools_mcp.mcp_manager import normalize_mcp_tool_arguments

        args = normalize_mcp_tool_arguments("weather_query", {"query": "查询北京明天天气"})

        self.assertEqual({"city": "北京", "extensions": "all"}, args)

    def test_web_search_keeps_query_and_defaults(self):
        from pkg.agent_tools_mcp.mcp_manager import normalize_mcp_tool_arguments

        args = normalize_mcp_tool_arguments("web_search", {"query": "北京好玩的地方"})

        self.assertEqual("北京好玩的地方", args["query"])
        self.assertEqual(5, args["max_results"])
