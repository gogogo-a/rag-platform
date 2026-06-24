import unittest

from langchain_core.agents import AgentFinish

from internal.agent.react_agent import TolerantReActOutputParser


class TolerantReActOutputParserTest(unittest.TestCase):
    def test_plain_answer_is_treated_as_final_answer(self):
        parser = TolerantReActOutputParser()

        parsed = parser.parse("根据知识库信息，耿浩的实习经历包括 AI 产品后台管理系统及官网建设。")

        self.assertIsInstance(parsed, AgentFinish)
        self.assertIn("耿浩的实习经历", parsed.return_values["output"])


if __name__ == "__main__":
    unittest.main()
