import unittest


class FakeAgentConfigService:
    def __init__(self, configs):
        self.configs = configs

    async def list_runtime_agents(self, tool_map):
        return self.configs


def fake_agent_config(agent_key, agent_name, description, mcp_tools, prompt_key=None, sort_order=10):
    return {
        "agent_key": agent_key,
        "agent_name": agent_name,
        "description": description,
        "mcp_tools": [tool for tool in mcp_tools],
        "prompt_key": prompt_key or agent_key,
        "enabled": True,
        "sort_order": sort_order,
    }


class ExpertAgentFrameworkTest(unittest.TestCase):
    def test_expert_prompt_loader_reads_from_prompt_service(self):
        import asyncio
        from unittest.mock import patch

        from internal.agent.expert_agent_registry import ExpertAgentRegistry

        class FakePromptService:
            async def get_active_prompt(self, agent_key):
                return f"{agent_key} prompt"

        registry = ExpertAgentRegistry({"knowledge_search": object()})
        with patch("internal.service.orm.prompt_service.prompt_service", FakePromptService()), patch(
            "internal.service.orm.agent_config_service.agent_config_service",
            FakeAgentConfigService([
                fake_agent_config("knowledge", "知识专家", "查询知识库、文档和内部资料。", ["knowledge_search"])
            ]),
        ):
            prompt = asyncio.run(registry.get_prompt_for_expert("knowledge"))

        self.assertEqual("knowledge prompt", prompt)

    def test_registry_groups_tools_by_domain(self):
        from internal.agent.expert_agent_registry import ExpertAgentRegistry

        registry = ExpertAgentRegistry(
            {
                "knowledge_search": object(),
                "web_search": object(),
                "geocode": object(),
                "ip_location": object(),
                "poi_search": object(),
                "route_planning": object(),
                "weather_query": object(),
                "email_sender": object(),
            }
        )

        self.assertEqual(["knowledge_search"], list(registry.get_tools_for_expert("knowledge").keys()))
        self.assertEqual(["web_search"], list(registry.get_tools_for_expert("search").keys()))
        self.assertEqual(["email_sender"], list(registry.get_tools_for_expert("email").keys()))
        self.assertEqual(
            ["geocode", "ip_location", "poi_search", "route_planning", "weather_query"],
            list(registry.get_tools_for_expert("location").keys()),
        )

    def test_registry_manifest_uses_runtime_available_experts(self):
        import asyncio
        from unittest.mock import patch

        from internal.agent.expert_agent_registry import ExpertAgentRegistry

        registry = ExpertAgentRegistry(
            {
                "web_search": object(),
                "weather_query": object(),
            }
        )

        with patch("internal.service.orm.agent_config_service.agent_config_service", FakeAgentConfigService([
            fake_agent_config("search", "搜索专家", "查询网页、实时信息和公开资料。", ["web_search"], "search", 20),
            fake_agent_config("location", "位置专家", "处理天气、地理编码、地点搜索、路线规划和 IP 定位。", ["weather_query"], "location", 30),
        ])):
            manifest = asyncio.run(registry.get_manifest())

        self.assertEqual(
            [
                {
                    "agent_key": "search",
                    "agent_name": "搜索专家",
                    "tool_name": "ask_search_expert",
                    "description": "查询网页、实时信息和公开资料。",
                    "tools": ["web_search"],
                    "enabled": True,
                },
                {
                    "agent_key": "location",
                    "agent_name": "位置专家",
                    "tool_name": "ask_location_expert",
                    "description": "处理天气、地理编码、地点搜索、路线规划和 IP 定位。",
                    "tools": ["weather_query"],
                    "enabled": True,
                },
            ],
            manifest,
        )

    def test_registry_does_not_fallback_to_fixed_experts_after_runtime_load(self):
        import asyncio
        from unittest.mock import patch

        from internal.agent.expert_agent_registry import ExpertAgentRegistry

        registry = ExpertAgentRegistry({"web_search": object(), "weather_query": object()})

        with patch("internal.service.orm.agent_config_service.agent_config_service", FakeAgentConfigService([])):
            manifest = asyncio.run(registry.get_manifest())

        self.assertEqual([], manifest)

    def test_expert_orchestrator_streams_child_agent_events_immediately(self):
        import asyncio

        from internal.agent.expert_orchestrator import ExpertOrchestrator

        events = []
        orchestrator = ExpertOrchestrator(
            llm_service=object(),
            tool_map={"web_search": object()},
            callback=lambda event_type, content: events.append((event_type, content)),
        )

        raw_process = []
        child_callback = orchestrator._build_expert_callback("search", "搜索专家", [], [], raw_process)
        child_callback("llm_chunk", "需要先查询天气")
        child_callback("action", "web_search(北京天气)")
        child_callback("observation", "晴")

        expert_processes = [
            content for event_type, content in events
            if event_type == "agent_process" and content["scope"] == "expert"
        ]
        self.assertEqual(
            ["需要先查询天气", "web_search(北京天气)", "晴"],
            [item["content"] for item in expert_processes],
        )
        self.assertEqual(
            ["需要先查询天气", "web_search(北京天气)", "晴"],
            [item["content"] for item in raw_process],
        )

    def test_message_request_defaults_to_single_agent_mode(self):
        from internal.dto.request.message_request import SendMessageRequest

        request = SendMessageRequest(content="你好")

        self.assertEqual("single", request.agent_mode)

    def test_expert_context_uses_recent_five_messages_without_process(self):
        from internal.agent.expert_context_builder import ExpertContextBuilder

        history = [
            {"role": "user", "content": f"问题{i}", "extra_data": {"thoughts": ["过程"]}}
            for i in range(1, 8)
        ]
        builder = ExpertContextBuilder(max_history_count=5)

        expert_input = builder.build_expert_input(
            expert_name="search",
            task="查询北京天气",
            original_question="北京明天天气",
            history=history,
        )

        self.assertNotIn("问题1", expert_input)
        self.assertNotIn("问题2", expert_input)
        self.assertIn("问题3", expert_input)
        self.assertIn("问题7", expert_input)
        self.assertNotIn("过程", expert_input)

    def test_expert_task_queue_creates_question_and_task_ids(self):
        from internal.agent.expert_task_queue import ExpertTaskQueue

        queue = ExpertTaskQueue(client=None, topics={
            "tasks": "expert_tasks",
            "results": "expert_results",
            "dead_letters": "expert_dead_letters",
        })

        envelope = queue.build_task(
            question_id="question-1",
            expert_key="search",
            task="查询北京天气",
            context="user: 北京明天天气",
        )

        self.assertEqual("question-1", envelope["question_id"])
        self.assertEqual("search", envelope["expert_key"])
        self.assertTrue(envelope["task_id"].startswith("question-1-search-"))
        self.assertEqual(0, envelope["retry_count"])

    def test_expert_task_queue_routes_failed_task_to_dead_letter_after_five_attempts(self):
        from internal.agent.expert_task_queue import ExpertTaskQueue

        sent = []

        class FakeClient:
            def send_message(self, topic, message, key=None):
                sent.append((topic, message, key))
                return True

        queue = ExpertTaskQueue(client=FakeClient(), topics={
            "tasks": "expert_tasks",
            "results": "expert_results",
            "dead_letters": "expert_dead_letters",
        })
        task = queue.build_task(
            question_id="question-1",
            expert_key="search",
            task="查询北京天气",
            context="user: 北京明天天气",
        )
        task["retry_count"] = 4

        routed = queue.route_failure(task, "搜索结果不可用", raw_process=["查询失败"])

        self.assertEqual("dead_letter", routed)
        self.assertEqual("expert_dead_letters", sent[0][0])
        self.assertEqual("question-1", sent[0][2])
        self.assertEqual("搜索结果不可用", sent[0][1]["error"])
        self.assertEqual(["查询失败"], sent[0][1]["raw_process"])

    def test_expert_result_store_groups_results_by_question_id(self):
        from internal.agent.expert_task_queue import ExpertResultStore

        store = ExpertResultStore()
        store.add_result({
            "question_id": "question-1",
            "task_id": "task-a",
            "expert_key": "search",
            "answer": "北京旅游景点",
            "success": True,
        })
        store.add_result({
            "question_id": "question-2",
            "task_id": "task-b",
            "expert_key": "location",
            "answer": "上海天气",
            "success": True,
        })

        self.assertEqual(["北京旅游景点"], [item["answer"] for item in store.get_results("question-1")])

    def test_expert_result_store_deduplicates_same_task_attempt(self):
        from internal.agent.expert_task_queue import ExpertResultStore

        store = ExpertResultStore()
        result = {
            "question_id": "question-1",
            "task_id": "task-a",
            "expert_key": "search",
            "answer": "北京旅游景点",
            "success": True,
            "retry_count": 0,
        }

        store.add_result(result)
        store.add_result(result.copy())

        self.assertEqual(1, len(store.get_results("question-1")))

    def test_iteration_limit_answer_is_not_useful(self):
        from internal.agent.expert_orchestrator import ExpertOrchestrator

        self.assertFalse(
            ExpertOrchestrator._is_useful_answer("Agent stopped due to iteration limit or time limit.")
        )

    def test_successful_result_emits_visible_expert_processes(self):
        import asyncio

        from internal.agent.expert_orchestrator import ExpertOrchestrator
        from internal.agent.expert_task_queue import ExpertResultStore

        events = []
        orchestrator = ExpertOrchestrator(
            llm_service=object(),
            tool_map={"weather_query": object()},
            callback=lambda event_type, content: events.append((event_type, content)),
        )
        orchestrator.question_id = "question-1"
        orchestrator.result_store = ExpertResultStore()

        task = {
            "question_id": "question-1",
            "task_id": "task-1",
            "expert_key": "location",
            "retry_count": 0,
        }
        result = {
            "success": True,
            "answer": "北京晴，29°C。",
            "raw_process": [
                {"phase": "thought", "content": "Thought"},
                {"phase": "thought", "content": ": 查询天气"},
                {"phase": "thought", "content": "\nThought: 判断用户需要实时天气"},
                {"phase": "action", "content": "weather_query({})"},
                {"phase": "action", "content": 'Action Input: {"city":"北京"}'},
                {"phase": "observation", "content": 'Observation: {"success": true, "summary": "北京晴，29°C。"}'},
                {"phase": "final_answer", "content": "Final Answer: 北京晴，29°C。"},
            ],
        }

        asyncio.run(orchestrator._handle_task_result(task, result))

        expert_processes = [
            content for event_type, content in events
            if event_type == "agent_process" and content["scope"] == "expert"
        ]
        self.assertEqual(
            [
                "查询天气 思考：判断用户需要实时天气",
                "weather_query({})",
                '{"city":"北京"}',
                '{"success": true, "summary": "北京晴，29°C。"}',
                "北京晴，29°C。",
            ],
            [item["content"] for item in expert_processes],
        )
        self.assertEqual(
            ["thought", "action", "action", "observation", "final_answer"],
            [item["phase"] for item in expert_processes],
        )

    def test_supervisor_emits_real_call_and_observation_processes(self):
        import asyncio

        from internal.agent.expert_orchestrator import ExpertOrchestrator
        from internal.agent.expert_task_queue import ExpertResultStore

        events = []
        orchestrator = ExpertOrchestrator(
            llm_service=object(),
            tool_map={"weather_query": object()},
            callback=lambda event_type, content: events.append((event_type, content)),
        )
        orchestrator.question_id = "question-1"
        orchestrator.result_store = ExpertResultStore()
        task = {
            "question_id": "question-1",
            "task_id": "task-1",
            "expert_key": "location",
            "task": "位置专家处理：北京明天天气",
            "retry_count": 0,
        }
        result = {
            "success": True,
            "answer": "北京明天多云，适合去故宫。",
            "raw_process": [],
        }

        asyncio.run(orchestrator._handle_task_result(task, result))

        supervisor_processes = [
            content for event_type, content in events
            if event_type == "agent_process" and content["scope"] == "supervisor"
        ]
        self.assertEqual(
            [
                {
                    "scope": "supervisor",
                    "agent_key": "supervisor",
                    "agent_name": "主助手",
                    "phase": "observation",
                    "content": "位置专家输出：北京明天多云，适合去故宫。",
                    "step_index": 1,
                }
            ],
            supervisor_processes,
        )

    def test_unusable_result_still_emits_expert_raw_process_once(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        from internal.agent.expert_orchestrator import ExpertOrchestrator

        events = []
        orchestrator = ExpertOrchestrator(
            llm_service=object(),
            tool_map={"web_search": object()},
            callback=lambda event_type, content: events.append((event_type, content)),
        )
        orchestrator.question_id = "question-1"
        orchestrator.task_queue.max_retries = 2
        task = {
            "question_id": "question-1",
            "task_id": "task-1",
            "expert_key": "search",
            "task": "搜索专家处理：北京天气",
            "retry_count": 0,
        }
        result = {
            "success": False,
            "answer": "Agent stopped due to iteration limit or time limit.",
            "error": "结果不可用",
            "raw_process": [
                {"phase": "thought", "content": "需要搜索天气"},
                {"phase": "action", "content": "web_search(北京天气)"},
                {"phase": "observation", "content": "没有可用结果"},
            ],
        }

        with patch.object(orchestrator, "_dispatch_and_run_task", AsyncMock()):
            awaitable = orchestrator._handle_task_result(task, result)
            asyncio.run(awaitable)

        expert_processes = [
            content for event_type, content in events
            if event_type == "agent_process" and content["scope"] == "expert"
        ]
        self.assertEqual(
            ["需要搜索天气", "web_search(北京天气)", "没有可用结果"],
            [item["content"] for item in expert_processes],
        )

    def test_run_stream_dispatches_selected_experts_concurrently(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        from internal.agent.expert_orchestrator import ExpertOrchestrator

        events = []
        orchestrator = ExpertOrchestrator(
            llm_service=object(),
            tool_map={"web_search": object(), "weather_query": object()},
            callback=lambda event_type, content: events.append((event_type, content)),
        )
        started = []

        async def delayed_dispatch(task):
            started.append(task["expert_key"])
            if task["expert_key"] == "search":
                await asyncio.sleep(0.05)
            orchestrator.result_store.add_result({
                "question_id": task["question_id"],
                "task_id": task["task_id"],
                "expert_key": task["expert_key"],
                "answer": f"{task['expert_key']} result",
                "success": True,
                "process_summary": "",
                "raw_process": [],
                "documents": [],
                "rag_results": [],
                "retry_count": task.get("retry_count", 0),
            })

        with patch("internal.service.orm.agent_config_service.agent_config_service", FakeAgentConfigService([
                fake_agent_config("search", "搜索专家", "查询网页、实时信息和公开资料。", ["web_search"], "search", 20),
                fake_agent_config("location", "位置专家", "处理天气、地理编码、地点搜索、路线规划和 IP 定位。", ["weather_query"], "location", 30),
             ])), \
             patch.object(orchestrator, "_dispatch_and_run_task", AsyncMock(side_effect=delayed_dispatch)), \
             patch.object(orchestrator, "_save_experience", AsyncMock()):
            answer = asyncio.run(orchestrator.run_stream("搜索北京明天天气"))

        supervisor_processes = [
            content for event_type, content in events
            if event_type == "agent_process" and content["scope"] == "supervisor"
        ]
        self.assertEqual("thought", supervisor_processes[0]["phase"])
        self.assertEqual("识别到需要调用：搜索专家、位置专家", supervisor_processes[0]["content"])
        self.assertEqual(["search", "location"], started)
        self.assertIn("搜索专家：search result", answer)
        self.assertIn("位置专家：location result", answer)

    def test_process_markers_inside_expert_text_are_localized_without_changing_content(self):
        from internal.agent.expert_orchestrator import ExpertOrchestrator

        self.assertEqual(
            "我已完成查询。输出：北京明天晴，适合去故宫。",
            ExpertOrchestrator._clean_process_display_text(
                "thought",
                "我已完成查询。FinalAnswer:北京明天晴，适合去故宫。",
            ),
        )

    def test_prompt_control_fragments_are_hidden_from_expert_process(self):
        from internal.agent.expert_orchestrator import ExpertOrchestrator

        for fragment in ["Question", "Question:", "开始！"]:
            self.assertEqual(
                "",
                ExpertOrchestrator._clean_process_display_text("thought", fragment),
            )

    def test_orchestrator_dispatches_tasks_without_running_child_agent_locally(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        from internal.agent.expert_orchestrator import ExpertOrchestrator

        sent = []

        class FakeClient:
            def send_message(self, topic, message, key=None):
                sent.append((topic, message, key))
                return True

        orchestrator = ExpertOrchestrator(
            llm_service=object(),
            tool_map={"web_search": object()},
        )
        orchestrator.task_queue.client = FakeClient()

        async def add_result_after_dispatch(task):
            orchestrator.result_store.add_result({
                "question_id": task["question_id"],
                "task_id": task["task_id"],
                "expert_key": "search",
                "answer": "北京天气晴。",
                "success": True,
                "process_summary": "查询公开资料",
                "raw_process": [],
                "documents": [],
                "rag_results": [],
                "retry_count": 0,
            })

        with patch("internal.service.orm.agent_config_service.agent_config_service", FakeAgentConfigService([
                fake_agent_config("search", "搜索专家", "查询网页、实时信息和公开资料。", ["web_search"], "search", 20),
             ])), \
             patch.object(orchestrator, "_ask_expert", AsyncMock(side_effect=AssertionError("child agent should run in worker"))), \
             patch.object(orchestrator, "_wait_for_task_result", AsyncMock(side_effect=add_result_after_dispatch)), \
             patch.object(orchestrator, "_save_experience", AsyncMock()):
            answer = asyncio.run(orchestrator.run_stream("搜索北京天气"))

        self.assertEqual("北京天气晴。", answer)
        self.assertEqual("expert_tasks", sent[0][0])
        self.assertEqual(orchestrator.question_id, sent[0][2])

    def test_expert_worker_consumes_task_and_sends_result(self):
        import asyncio
        from unittest.mock import AsyncMock, patch

        from internal.agent.expert_worker import ExpertTaskWorker

        sent = []

        class FakeClient:
            def send_message(self, topic, message, key=None):
                sent.append((topic, message, key))
                return True

        worker = ExpertTaskWorker(llm_service=object(), tool_map={"web_search": object()}, client=FakeClient())
        task = {
            "question_id": "question-1",
            "task_id": "task-1",
            "expert_key": "search",
            "task": "查询北京天气",
            "context": "user: 北京天气",
            "retry_count": 0,
        }

        with patch.object(worker, "_ask_expert", AsyncMock(return_value='{"answer":"北京天气晴。","raw_process":[],"documents":[],"rag_results":[],"process_summary":"查询公开资料"}')):
            asyncio.run(worker.handle_task(task))

        self.assertEqual("expert_results", sent[0][0])
        self.assertEqual("question-1", sent[0][2])
        self.assertEqual("task-1", sent[0][1]["task_id"])
        self.assertEqual("北京天气晴。", sent[0][1]["answer"])
        self.assertTrue(sent[0][1]["success"])

    def test_orchestrator_dead_letters_unusable_expert_result_after_one_retry(self):
        import asyncio
        from unittest.mock import patch

        from internal.agent.expert_orchestrator import ExpertOrchestrator

        events = []
        sent = []

        class FakeClient:
            def send_message(self, topic, message, key=None):
                sent.append((topic, message.copy(), key))
                return True

        orchestrator = ExpertOrchestrator(
            llm_service=object(),
            tool_map={"web_search": object()},
            callback=lambda event_type, content: events.append((event_type, content)),
        )
        orchestrator.task_queue.client = FakeClient()
        orchestrator.task_queue.max_retries = 2
        orchestrator.question_id = "question-1"
        task = orchestrator.task_queue.build_task(
            question_id="question-1",
            expert_key="search",
            task="查询北京天气",
            context="user: 北京明天天气",
        )

        async def patched_wait(dispatched_task):
            if int(dispatched_task.get("retry_count") or 0) < 1:
                orchestrator.result_store.add_result({
                    "question_id": dispatched_task["question_id"],
                    "task_id": dispatched_task["task_id"],
                    "expert_key": "search",
                    "answer": "抱歉，我无法回答这个问题。",
                    "raw_process": [{"phase": "observation", "content": "没有结果"}],
                    "success": False,
                    "error": "结果不可用",
                    "retry_count": dispatched_task.get("retry_count", 0),
                })
            else:
                orchestrator.result_store.add_dead_letter({
                    "question_id": dispatched_task["question_id"],
                    "task_id": dispatched_task["task_id"],
                    "expert_key": "search",
                    "raw_process": [{"phase": "observation", "content": "没有结果"}],
                    "success": False,
                    "error": "结果不可用",
                    "retry_count": dispatched_task.get("retry_count", 0),
                })
            await ExpertOrchestrator._wait_for_task_result(orchestrator, dispatched_task)

        with patch.object(orchestrator, "_wait_for_task_result", patched_wait):
            asyncio.run(orchestrator._dispatch_and_run_task(task))

        statuses = [
            content["status"]
            for event_type, content in events
            if event_type == "expert_task_status"
        ]
        self.assertEqual(2, statuses.count("created"))
        self.assertIn("dead_letter", statuses)
        self.assertEqual(1, len(orchestrator.dead_letter_tasks))
        self.assertEqual(2, len([item for item in sent if item[0] == "expert_tasks"]))
        call_processes = [
            content for event_type, content in events
            if event_type == "agent_process" and content["phase"] == "call"
        ]
        self.assertTrue(call_processes)
        self.assertEqual("搜索专家\n任务：查询北京天气", call_processes[0]["content"])

    def test_expert_consumers_register_task_result_and_dead_letter_topics(self):
        from unittest.mock import patch

        from internal.agent import expert_consumers

        started = []

        class FakeMessageClient:
            mode = "kafka"
            client = object()

            def start_consumer(self, handler, topic=None, num_consumers=None):
                started.append((topic, handler.__name__))

        class FakeConfig:
            @staticmethod
            def get(key, default=None):
                if key == "kafka.topics":
                    return {
                        "expert_tasks": "expert_tasks",
                        "expert_results": "expert_results",
                        "expert_dead_letters": "expert_dead_letters",
                    }
                return default

        expert_consumers.stop_expert_consumers()
        with patch("internal.document_client.message_client.message_client", FakeMessageClient()), \
             patch("internal.document_client.config_loader.config", FakeConfig()), \
             patch("internal.agent.expert_consumers._build_worker_llm_service", return_value=object()):
            expert_consumers.start_expert_consumers(tool_map={"web_search": object()})

        self.assertEqual(
            [
                ("expert_tasks", "handle_expert_task_message"),
                ("expert_results", "handle_expert_result_message"),
                ("expert_dead_letters", "handle_expert_dead_letter_message"),
            ],
            started,
        )
        expert_consumers.stop_expert_consumers()

    def test_message_stream_persists_agent_processes(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from internal.service.orm.message_sever import MessageService

        saved_extra_data = {}

        async def fake_reply_stream(*args, **kwargs):
            yield {
                "event": "expert_question",
                "data": {"question_id": "question-1"},
            }
            yield {
                "event": "expert_manifest",
                "data": {
                    "experts": [
                        {
                            "agent_key": "search",
                            "agent_name": "搜索专家",
                            "description": "查询网页、实时信息和公开资料。",
                            "tools": ["web_search"],
                        }
                    ]
                },
            }
            yield {
                "event": "agent_process",
                "data": {
                    "scope": "expert",
                    "agent_key": "search",
                    "agent_name": "搜索专家",
                    "phase": "action",
                    "content": "web_search(北京天气)",
                    "step_index": 1,
                },
            }
            yield {
                "event": "expert_task_status",
                "data": {
                    "question_id": "question-1",
                    "task_id": "task-1",
                    "expert_key": "search",
                    "status": "completed",
                    "message": "搜索专家已返回结果。",
                    "result": {
                        "answer": "北京天气晴。",
                        "process_summary": "查询公开资料",
                        "success": True,
                    },
                },
            }
            yield {
                "event": "expert_experience",
                "data": {"experience_chain_id": "experience-1"},
            }
            yield {
                "event": "agent_context_usage",
                "data": {
                    "primary_agent_usage": {
                        "agent_key": "supervisor",
                        "agent_name": "主助手",
                        "used_tokens": 30,
                        "context_window": 1000,
                        "percent": 3,
                        "sections": [],
                    },
                    "child_agent_usages": [
                        {
                            "agent_key": "search",
                            "agent_name": "搜索专家",
                            "used_tokens": 12,
                            "context_window": 1000,
                            "percent": 1.2,
                            "sections": [],
                        }
                    ],
                },
            }
            yield {"event": "answer_chunk", "data": {"content": "北京天气晴。"}}

        async def fake_save_ai_message(*args, **kwargs):
            saved_extra_data.update(kwargs["extra_data"])
            return SimpleNamespace(uuid="ai-message-id", content="北京天气晴。")

        class FakeField:
            def __eq__(self, other):
                return True

        class FakeUserInfoModel:
            uuid = FakeField()

            @staticmethod
            async def find_one(*args, **kwargs):
                return None

        service = MessageService()
        with (
            patch("internal.service.orm.message_sever.session_manager.create_or_get_session", AsyncMock(return_value=("session-id", "会话"))),
            patch("internal.service.orm.message_sever.message_crud_service.save_user_message", AsyncMock(return_value=SimpleNamespace(uuid="user-message-id", content="查北京天气"))),
            patch("internal.service.orm.message_sever.history_manager.get_session_history", AsyncMock(return_value=[])),
            patch("internal.model.user_info.UserInfoModel", FakeUserInfoModel),
            patch("internal.service.orm.message_sever.qa_evaluator.start_evaluation"),
            patch("internal.service.orm.message_sever.ai_reply_service.generate_reply_stream", fake_reply_stream),
            patch("internal.service.orm.message_sever.message_crud_service.save_ai_message", fake_save_ai_message),
            patch("internal.service.orm.message_sever.qa_evaluator.get_evaluation_result", AsyncMock(return_value=False)),
            patch("internal.service.orm.message_sever.thought_chain_store.save_chain", AsyncMock(return_value="thought-chain-id")),
            patch("internal.service.orm.message_sever.session_manager.update_last_message", AsyncMock()),
            patch("internal.service.orm.message_sever.summary_service.check_and_save_summary", AsyncMock()),
            patch("internal.service.orm.message_sever.message_crud_service.count_session_messages", AsyncMock(return_value=3)),
        ):
            events = asyncio.run(self._collect_stream(service))

        self.assertIn("expert_manifest", [event["event"] for event in events])
        self.assertIn("agent_process", [event["event"] for event in events])
        self.assertIn("expert_task_status", [event["event"] for event in events])
        self.assertEqual("question-1", saved_extra_data["question_id"])
        self.assertEqual("search", saved_extra_data["agent_manifest"][0]["agent_key"])
        self.assertEqual("web_search(北京天气)", saved_extra_data["agent_processes"][0]["content"])
        self.assertEqual("task-1", saved_extra_data["expert_tasks"][0]["task_id"])
        self.assertEqual("北京天气晴。", saved_extra_data["expert_results"][0]["answer"])
        self.assertEqual("experience-1", saved_extra_data["experience_chain_id"])
        self.assertEqual("主助手", saved_extra_data["agent_context_usage"]["primary_agent_usage"]["agent_name"])
        self.assertEqual("search", saved_extra_data["agent_context_usage"]["child_agent_usages"][0]["agent_key"])
        self.assertIn("elapsed_seconds", saved_extra_data)
        done_events = [event for event in events if event["event"] == "done"]
        self.assertEqual(1, len(done_events))
        self.assertIn("elapsed_seconds", done_events[0]["data"])

    async def _collect_stream(self, service):
        events = []
        async for event in service.send_message_stream(
            content="查北京天气",
            user_id="user-id",
            send_name="用户",
            send_avatar="",
            show_thinking=True,
            agent_mode="expert",
        ):
            events.append(event)
        return events


if __name__ == "__main__":
    unittest.main()
