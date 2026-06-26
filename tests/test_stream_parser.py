import unittest

from internal.service.ai.stream_parser import StreamParser


class StreamParserTest(unittest.TestCase):
    def test_complete_final_answer_marker_starts_answer_stream(self):
        parser = StreamParser()

        result = parser.parse_chunk("Final Answer: 你好")

        self.assertEqual({"event": "answer_chunk", "content": "你好"}, result)

    def test_split_final_answer_marker_starts_answer_stream(self):
        parser = StreamParser()

        chunks = ["Final", " Answer", ":", " 你好", "，", "欢迎"]
        results = [parser.parse_chunk(chunk) for chunk in chunks]

        self.assertEqual(
            [
                {"event": "answer_chunk", "content": "你好"},
                {"event": "answer_chunk", "content": "，"},
                {"event": "answer_chunk", "content": "欢迎"},
            ],
            [result for result in results if result],
        )

    def test_answer_state_streams_following_chunks(self):
        parser = StreamParser()

        parser.parse_chunk("Answer:")
        first = parser.parse_chunk("第一段")
        second = parser.parse_chunk("第二段")

        self.assertEqual({"event": "answer_chunk", "content": "第一段"}, first)
        self.assertEqual({"event": "answer_chunk", "content": "第二段"}, second)

    def test_reasoning_markers_do_not_enter_answer_content(self):
        parser = StreamParser()

        chunks = [
            "Thought: 需要检索",
            "\nAction: knowledge_search",
            "\nObservation: 结果",
            "\nFinal Answer: 最终回答",
        ]
        results = [parser.parse_chunk(chunk) for chunk in chunks]

        self.assertEqual(
            [{"event": "answer_chunk", "content": "最终回答"}],
            [result for result in results if result and result["event"] == "answer_chunk"],
        )

    def test_unmarked_react_thought_streams_as_thought_before_action(self):
        parser = StreamParser()

        first = parser.parse_chunk("用户询问实习经历，需要检索知识库。")
        second = parser.parse_chunk("\nAction: knowledge_search")
        third = parser.parse_chunk('\nAction Input: {"query": "实习经历"}')

        self.assertEqual({"event": "thought", "content": "用户询问实习经历，需要检索知识库。"}, first)
        self.assertIsNone(second)
        self.assertIsNone(third)
        self.assertFalse(parser.is_answer_sent())

    def test_split_action_marker_flushes_collected_thought_once(self):
        parser = StreamParser()

        results = [
            parser.parse_chunk("Thought: 需要先检索知识库"),
            parser.parse_chunk("\nAct"),
            parser.parse_chunk("ion: knowledge_search"),
            parser.parse_chunk('\nAction Input: {"query": "实习经历"}'),
        ]

        self.assertEqual(
            [{"event": "thought", "content": "需要先检索知识库"}],
            [result for result in results if result],
        )

    def test_action_input_fragments_do_not_enter_answer(self):
        parser = StreamParser()

        chunks = [
            "Thought: 需要查询",
            "\nAction: knowledge_search",
            '\nAction Input: {"query": "耿浩 实习经历"}',
            "\nObservation: 检索结果",
            "\nFinal Answer: 耿浩有相关实习经历。",
        ]
        results = [parser.parse_chunk(chunk) for chunk in chunks]

        answer = "".join(
            result["content"]
            for result in results
            if result and result["event"] == "answer_chunk"
        )

        self.assertEqual("耿浩有相关实习经历。", answer)
        self.assertNotIn("Action", answer)
        self.assertNotIn("knowledge_search", answer)

    def test_unmarked_thought_before_action_is_not_answer_content(self):
        parser = StreamParser()

        chunks = [
            "用户询问“耿浩的实习经历有什么”，我需要先搜索知识库。",
            "\n\nAction",
            ": knowledge",
            "_search",
            "Action Input",
            ': {"query": "耿浩 实习经历"}',
            "\nFinal Answer: 根据知识库内容，耿浩有实习经历。",
        ]
        results = [parser.parse_chunk(chunk) for chunk in chunks]

        answer = "".join(
            result["content"]
            for result in results
            if result and result["event"] == "answer_chunk"
        )

        self.assertEqual("根据知识库内容，耿浩有实习经历。", answer)
        self.assertNotIn("Action", answer)
        self.assertNotIn("knowledge_search", answer)

    def test_callback_action_is_forwarded_to_action_event(self):
        parser = StreamParser()

        result = parser.handle_callback_event(
            "action",
            'knowledge_search({"query": "实习经历"})'
        )

        self.assertEqual(
            {
                "event": "action",
                "content": 'knowledge_search({"query": "实习经历"})'
            },
            result,
        )

    def test_final_answer_marker_is_required_before_answer_chunks(self):
        parser = StreamParser()

        results = [
            parser.parse_chunk("需要整理结果。"),
            parser.parse_chunk("\nFinal Answer: "),
            parser.parse_chunk("最终回答"),
        ]

        self.assertEqual(
            [{"event": "answer_chunk", "content": "最终回答"}],
            [result for result in results if result and result["event"] == "answer_chunk"],
        )

    def test_plain_answer_without_react_markers_streams_as_answer_chunks(self):
        parser = StreamParser()

        results = [
            parser.parse_chunk("你好，"),
            parser.parse_chunk("可以直接回答。"),
        ]

        self.assertEqual(
            [
                {"event": "answer_chunk", "content": "你好，"},
                {"event": "answer_chunk", "content": "可以直接回答。"},
            ],
            [result for result in results if result],
        )

    def test_react_trace_before_final_answer_never_enters_answer_content(self):
        parser = StreamParser()

        chunks = [
            "好的，我来查询。\n\n",
            "Action: web_search\n",
            'Action Input: {"query": "北京好玩的地方"}',
            "已经获取推荐信息。",
            "\n\nAction: weather_query\n",
            'Action Input: {"city": "北京"}',
            "\n\nFinal Answer:\n### 北京推荐\n- 故宫\n- 天坛",
        ]
        results = [parser.parse_chunk(chunk) for chunk in chunks]

        answer = "".join(
            result["content"]
            for result in results
            if result and result["event"] == "answer_chunk"
        )

        self.assertEqual("### 北京推荐\n- 故宫\n- 天坛", answer)
        self.assertNotIn("Action:", answer)
        self.assertNotIn("Action Input:", answer)
        self.assertNotIn("weather_query", answer)

    def test_markdown_wrapped_final_answer_marker_is_not_answer_content(self):
        parser = StreamParser()

        results = [
            parser.parse_chunk("**Final Answer:** 以下是结果"),
            parser.parse_chunk("\n\n### 北京推荐"),
        ]
        answer = "".join(
            result["content"]
            for result in results
            if result and result["event"] == "answer_chunk"
        )

        self.assertEqual("以下是结果\n\n### 北京推荐", answer)
        self.assertNotIn("Final Answer", answer)
        self.assertFalse(answer.startswith("**"))

    def test_action_after_answer_start_does_not_leak_into_answer_content(self):
        parser = StreamParser()

        chunks = [
            "Final Answer: 用户想了解如何自制一个深度学习框架。",
            "\nAction",
            "\nAction Input: {}",
            "\nObservation: 未找到相关搜索结果",
        ]
        results = [parser.parse_chunk(chunk) for chunk in chunks]

        answer = "".join(
            result["content"]
            for result in results
            if result and result["event"] == "answer_chunk"
        )

        self.assertEqual("用户想了解如何自制一个深度学习框架。", answer)
        self.assertNotIn("Action", answer)
        self.assertNotIn("Observation", answer)

    def test_user_intent_reasoning_and_bare_action_do_not_become_answer(self):
        parser = StreamParser()

        chunks = [
            "用户想了解如何自制一个深度学习框架，这是一个技术性较强的问题。我需要搜索相关资料来提供详细指导。",
            "\n\nAction",
        ]
        results = [parser.parse_chunk(chunk) for chunk in chunks]

        self.assertEqual(
            [
                {
                    "event": "thought",
                    "content": "用户想了解如何自制一个深度学习框架，这是一个技术性较强的问题。我需要搜索相关资料来提供详细指导。",
                }
            ],
            [result for result in results if result],
        )
        self.assertFalse(parser.is_answer_sent())

    def test_user_intent_reasoning_stays_out_of_answer_before_action_arrives(self):
        parser = StreamParser()

        result = parser.parse_chunk(
            "用户想了解如何自制一个深度学习框架，这是一个技术性较强的问题。我需要从知识库或网络中搜索相关资料来提供详细指导。"
        )

        self.assertEqual(
            {
                "event": "thought",
                "content": "用户想了解如何自制一个深度学习框架，这是一个技术性较强的问题。我需要从知识库或网络中搜索相关资料来提供详细指导。",
            },
            result,
        )
        self.assertFalse(parser.is_answer_sent())

    def test_search_plan_reasoning_stays_out_of_answer(self):
        parser = StreamParser()

        result = parser.parse_chunk(
            "用户想了解如何自制一个深度学习框架，需要提供系统性的指导。我可以先搜索知识库中是否有相关文档，同时也可以搜索网页获取最新资料。"
        )

        self.assertEqual(
            {
                "event": "thought",
                "content": "用户想了解如何自制一个深度学习框架，需要提供系统性的指导。我可以先搜索知识库中是否有相关文档，同时也可以搜索网页获取最新资料。",
            },
            result,
        )
        self.assertFalse(parser.is_answer_sent())

    def test_process_plan_followed_by_plain_answer_does_not_leak(self):
        parser = StreamParser()

        chunks = [
            "用户想了解如何自制一个深度学习框架。这是一个技术性较强的问题，我需要提供系统性的指导。我可以先搜索知识库中是否有相关文档，同时也可以进行网页搜索获取更全面的信息。",
            "\n\n想了解如何自制一个深度学习框架。这是一个技术性较强的问题，我需要提供系统性的指导。我可以先搜索知识库中是否有相关文档，同时也可以进行网页搜索获取更全面的信息。",
            "要自制一个深度学习框架，可以参考以下步骤和核心思路：",
        ]
        results = [parser.parse_chunk(chunk) for chunk in chunks]
        answer = "".join(
            result["content"]
            for result in results
            if result and result["event"] == "answer_chunk"
        )

        self.assertEqual("要自制一个深度学习框架，可以参考以下步骤和核心思路：", answer)
        self.assertNotIn("我可以先搜索", answer)
        self.assertNotIn("这是一个技术性较强的问题", answer)

    def test_clean_final_result_drops_unfinished_react_trace(self):
        parser = StreamParser()

        result = parser.clean_final_result(
            "用户想了解如何自制一个深度学习框架，这是一个技术性较强的问题。我需要从知识库或网络中搜索相关资料来提供详细指导。\n\nAction"
        )

        self.assertIsNone(result)

    def test_clean_final_result_extracts_final_answer(self):
        parser = StreamParser()

        result = parser.clean_final_result(
            "用户想了解问题。\nAction: search\nObservation: 找到资料\nFinal Answer: 可以从自动求导、张量、算子和优化器开始实现。"
        )

        self.assertEqual("可以从自动求导、张量、算子和优化器开始实现。", result)

    def test_clean_final_result_strips_cached_process_before_final_answer(self):
        parser = StreamParser()

        result = parser.clean_final_result(
            "用户询问如何自制一个深度学习框架，我需要先搜索资料。\n"
            "要自制一个深度学习框架，你需要从理解其核心原理开始。\n\n"
            "Final Answer: 要自制一个深度学习框架，你需要从自动微分、计算图、张量对象和优化器开始。"
        )

        self.assertEqual(
            "要自制一个深度学习框架，你需要从自动微分、计算图、张量对象和优化器开始。",
            result,
        )
        self.assertNotIn("我需要先搜索", result)
        self.assertNotIn("Final Answer", result)


if __name__ == "__main__":
    unittest.main()
