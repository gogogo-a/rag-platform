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


if __name__ == "__main__":
    unittest.main()
