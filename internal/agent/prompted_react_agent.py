"""ReAct Agent variant that accepts an explicit prompt template."""

from typing import Callable, Dict, Optional

from langchain_core.prompts import PromptTemplate

from internal.agent.react_agent import ReActAgent, TolerantReActOutputParser


class PromptedReActAgent(ReActAgent):
    def __init__(
        self,
        llm_service,
        tools: Dict[str, Callable],
        prompt_template: str,
        max_iterations: int = 5,
        verbose: bool = False,
        callback: Optional[Callable] = None,
    ):
        self.prompt_template = prompt_template
        super().__init__(
            llm_service=llm_service,
            tools=tools,
            max_iterations=max_iterations,
            verbose=verbose,
            callback=callback,
        )

    def _create_agent(self):
        template = f"""{self.prompt_template}

你可以使用以下工具：

{{tools}}

严格按照以下格式输出：

Question: 需要回答的问题
Thought: 思考应该做什么
Action: 要执行的动作，必须是以下之一 [{{tool_names}}]
Action Input: 动作的输入参数
Observation: 动作的执行结果
... (Thought/Action/Action Input/Observation 可以重复N次)
Thought: 我现在知道最终答案了
Final Answer: 对原始问题的最终答案

{{chat_history}}

开始！

Question: {{input}}
Thought:{{agent_scratchpad}}"""

        prompt = PromptTemplate.from_template(template)
        from langchain.agents import create_react_agent

        return create_react_agent(
            llm=self.llm,
            tools=self.langchain_tools,
            prompt=prompt,
            output_parser=TolerantReActOutputParser(),
        )
