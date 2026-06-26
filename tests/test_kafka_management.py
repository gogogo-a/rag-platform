import asyncio
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


class FakeKafkaRecord:
    def __init__(self, topic, partition, offset, key, value, timestamp):
        self.topic = topic
        self.partition = partition
        self.offset = offset
        self.key = key
        self.value = value
        self.timestamp = timestamp


class FakeTopicPartition:
    def __init__(self, topic, partition):
        self.topic = topic
        self.partition = partition

    def __hash__(self):
        return hash((self.topic, self.partition))

    def __eq__(self, other):
        return (self.topic, self.partition) == (other.topic, other.partition)


class FakeKafkaConsumer:
    committed = False
    poll_count = 0

    def __init__(self, *args, **kwargs):
        self.config = kwargs
        self.assigned = []
        self.seek_calls = []
        self.closed = False
        self.records = {}

    def partitions_for_topic(self, topic):
        return {0, 1} if topic == "expert_tasks" else {0}

    def assign(self, partitions):
        self.assigned = partitions

    def end_offsets(self, partitions):
        return {partition: (15 if partition.partition == 0 else 0) for partition in partitions}

    def beginning_offsets(self, partitions):
        return {partition: 0 for partition in partitions}

    def seek(self, partition, offset):
        self.seek_calls.append((partition, offset))

    def poll(self, timeout_ms=1000, max_records=100):
        FakeKafkaConsumer.poll_count += 1
        partition = FakeTopicPartition("expert_tasks", 0)
        return {
            partition: [
                FakeKafkaRecord(
                    topic="expert_tasks",
                    partition=0,
                    offset=13,
                    key="question-1",
                    value={
                        "question_id": "question-1",
                        "task_id": "task-1",
                        "expert_key": "knowledge",
                        "task": "查询制度",
                        "retry_count": 0,
                        "created_at": "2026-06-25T10:00:00",
                    },
                    timestamp=1782362400000,
                )
            ]
        }

    def commit(self, *args, **kwargs):
        FakeKafkaConsumer.committed = True

    def close(self):
        self.closed = True


class FakeEvaluationRecord:
    def __init__(self):
        self.id = "eval-1"
        self.question = "制度怎么查"
        self.answer = "可以查询知识库"
        self.retrieved_text = "制度正文"
        self.session_id = "session-1"
        self.user_id = "user-1"
        self.message_id = "message-1"
        self.document_uuid = "doc-1"
        self.filename = "制度.pdf"
        self.ragas_status = "queued"
        self.queue_status = "queued"


class FakeMessageRecord:
    def __init__(self):
        self.uuid = "message-1"
        self.session_id = "session-1"
        self.send_id = "user-1"
        self.content = "请查询制度"
        self.extra_data = {"question_id": "question-1"}


class FakeSessionRecord:
    user_id = object()

    def __init__(self):
        self.uuid = "session-1"
        self.user_id = "user-1"
        self.name = "制度查询"


class FakeDocumentRecord:
    def __init__(self):
        self.uuid = "doc-1"
        self.name = "制度.pdf"
        self.status = 2
        self.extra_data = {"uploader_id": "user-1", "uploader_name": "管理员"}


class FakeUserRecord:
    def __init__(self):
        self.uuid = "user-1"
        self.nickname = "管理员"
        self.email = "admin@example.com"


class AsyncFindOneModel:
    uuid = object()

    def __init__(self, record):
        self.record = record

    async def find_one(self, *_args, **_kwargs):
        return self.record


class FakeMessageModel:
    session_id = object()
    extra_data = object()

    @classmethod
    async def find_one(cls, *_args, **_kwargs):
        return FakeMessageRecord()


class FakeAgentConfigService:
    async def list_agents(self, page=1, page_size=500, keyword=None, enabled=None):
        return {
            "items": [
                {
                    "agent_key": "search",
                    "agent_name": "联网搜索专家",
                    "enabled": True,
                }
            ],
            "total": 1,
        }


class KafkaManagementTest(unittest.TestCase):
    def test_topics_read_configured_kafka_topics_and_groups(self):
        from internal.service.kafka_management_service import KafkaManagementService

        service = KafkaManagementService(
            kafka_config={
                "bootstrap_servers": ["8.140.245.242:9092"],
                "topics": {
                    "expert_tasks": "expert_tasks",
                    "rag_evaluation": "rag_evaluation",
                },
                "consumer_groups": {
                    "expert_tasks": "brainwave_expert_worker_group",
                    "rag_evaluation": "brainwave_ragas_group",
                },
                "api_version": [4, 3],
            },
            consumer_cls=FakeKafkaConsumer,
            topic_partition_cls=FakeTopicPartition,
        )

        data = asyncio.run(service.get_topics())

        self.assertEqual([item["key"] for item in data["topics"]], ["expert_tasks", "rag_evaluation"])
        self.assertEqual(data["topics"][0]["topic"], "expert_tasks")
        self.assertEqual(data["topics"][0]["consumer_group"], "brainwave_expert_worker_group")
        self.assertEqual(data["topics"][0]["partition_count"], 2)
        self.assertEqual(data["topics"][0]["latest_offset"], 15)
        self.assertEqual(data["topics"][0]["active_partition_count"], 1)
        self.assertEqual(data["topics"][0]["empty_partition_count"], 1)
        self.assertEqual(data["topics"][0]["partitions"][0]["message_count"], 15)
        self.assertEqual(data["topics"][0]["partitions"][1]["message_count"], 0)

    def test_messages_require_selected_topic_and_do_not_scan_all_topics(self):
        from internal.service.kafka_management_service import KafkaManagementService

        FakeKafkaConsumer.poll_count = 0
        service = KafkaManagementService(
            kafka_config={
                "bootstrap_servers": ["8.140.245.242:9092"],
                "topics": {
                    "expert_tasks": "expert_tasks",
                    "rag_evaluation": "rag_evaluation",
                },
                "api_version": [4, 3],
            },
            consumer_cls=FakeKafkaConsumer,
            topic_partition_cls=FakeTopicPartition,
        )

        data = asyncio.run(service.list_messages(page=1, page_size=20))

        self.assertEqual(data["messages"], [])
        self.assertEqual(data["total"], 0)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 20)
        self.assertFalse(data["topic_selected"])
        self.assertEqual(FakeKafkaConsumer.poll_count, 0)

    def test_recent_messages_are_read_without_committing_offsets(self):
        from internal.service.kafka_management_service import KafkaManagementService

        FakeKafkaConsumer.committed = False
        service = KafkaManagementService(
            kafka_config={
                "bootstrap_servers": ["8.140.245.242:9092"],
                "topics": {"expert_tasks": "expert_tasks"},
                "api_version": [4, 3],
            },
            consumer_cls=FakeKafkaConsumer,
            topic_partition_cls=FakeTopicPartition,
        )

        data = asyncio.run(service.list_messages(topic="expert_tasks", page=1, page_size=20))

        self.assertFalse(FakeKafkaConsumer.committed)
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["page"], 1)
        self.assertEqual(data["page_size"], 20)
        self.assertTrue(data["topic_selected"])
        self.assertEqual(data["messages"][0]["topic"], "expert_tasks")
        self.assertEqual(data["messages"][0]["partition"], 0)
        self.assertEqual(data["messages"][0]["offset"], 13)
        self.assertEqual(data["messages"][0]["question_id"], "question-1")
        self.assertEqual(data["messages"][0]["task_id"], "task-1")
        self.assertEqual(data["messages"][0]["message_type"], "专家任务")
        self.assertEqual(data["messages"][0]["status"], "待处理")
        self.assertEqual(data["messages"][0]["expert_name"], "知识库专家")

    def test_expert_task_status_is_enriched_from_result_topic(self):
        from internal.service.kafka_management_service import KafkaManagementService

        class ExpertLifecycleConsumer(FakeKafkaConsumer):
            def partitions_for_topic(self, topic):
                return {0}

            def poll(self, timeout_ms=1000, max_records=100):
                topic = self.assigned[0].topic
                if topic == "expert_tasks":
                    return {
                        FakeTopicPartition("expert_tasks", 0): [
                            FakeKafkaRecord(
                                topic="expert_tasks",
                                partition=0,
                                offset=10,
                                key="question-1",
                                value={
                                    "question_id": "question-1",
                                    "task_id": "task-1",
                                    "expert_key": "search",
                                    "task": "搜索天气",
                                },
                                timestamp=1782362400000,
                            )
                        ]
                    }
                if topic == "expert_results":
                    return {
                        FakeTopicPartition("expert_results", 0): [
                            FakeKafkaRecord(
                                topic="expert_results",
                                partition=0,
                                offset=12,
                                key="question-1",
                                value={
                                    "question_id": "question-1",
                                    "task_id": "task-1",
                                    "expert_key": "search",
                                    "answer": "北京明天有雨",
                                    "success": True,
                                },
                                timestamp=1782362401000,
                            )
                        ]
                    }
                return {}

        service = KafkaManagementService(
            kafka_config={
                "bootstrap_servers": ["8.140.245.242:9092"],
                "topics": {
                    "expert_tasks": "expert_tasks",
                    "expert_results": "expert_results",
                    "expert_dead_letters": "expert_dead_letters",
                },
                "api_version": [4, 3],
            },
            consumer_cls=ExpertLifecycleConsumer,
            topic_partition_cls=FakeTopicPartition,
        )

        with patch("internal.service.orm.agent_config_service.agent_config_service", FakeAgentConfigService()):
            data = asyncio.run(service.list_messages(topic="expert_tasks", page=1, page_size=20))

        message = data["messages"][0]
        self.assertEqual(message["expert_key"], "search")
        self.assertEqual(message["expert_name"], "联网搜索专家")
        self.assertEqual(message["status"], "已完成")
        self.assertEqual(message["related_result"]["answer"], "北京明天有雨")

    def test_recent_messages_apply_backend_pagination(self):
        from internal.service.kafka_management_service import KafkaManagementService

        class MultiRecordConsumer(FakeKafkaConsumer):
            def poll(self, timeout_ms=1000, max_records=100):
                return {
                    FakeTopicPartition("expert_tasks", 0): [
                        FakeKafkaRecord(
                            topic="expert_tasks",
                            partition=0,
                            offset=offset,
                            key=f"question-{offset}",
                            value={
                                "question_id": f"question-{offset}",
                                "task_id": f"task-{offset}",
                                "expert_key": "knowledge",
                                "task": f"查询制度 {offset}",
                            },
                            timestamp=1782362400000 + offset,
                        )
                        for offset in range(10, 15)
                    ]
                }

        service = KafkaManagementService(
            kafka_config={
                "bootstrap_servers": ["8.140.245.242:9092"],
                "topics": {"expert_tasks": "expert_tasks"},
                "api_version": [4, 3],
            },
            consumer_cls=MultiRecordConsumer,
            topic_partition_cls=FakeTopicPartition,
        )

        data = asyncio.run(service.list_messages(topic="expert_tasks", page=2, page_size=2))

        self.assertEqual(data["total"], 5)
        self.assertEqual(data["page"], 2)
        self.assertEqual(data["page_size"], 2)
        self.assertEqual([item["offset"] for item in data["messages"]], [12, 11])

    def test_messages_are_enriched_with_related_session_user_and_document(self):
        from internal.service.kafka_management_service import KafkaManagementService

        service = KafkaManagementService(
            kafka_config={
                "bootstrap_servers": ["8.140.245.242:9092"],
                "topics": {"expert_tasks": "expert_tasks"},
                "api_version": [4, 3],
            },
            consumer_cls=FakeKafkaConsumer,
            topic_partition_cls=FakeTopicPartition,
            message_model=FakeMessageModel,
            session_model=AsyncFindOneModel(FakeSessionRecord()),
            user_model=AsyncFindOneModel(FakeUserRecord()),
            document_model=AsyncFindOneModel(FakeDocumentRecord()),
        )

        data = asyncio.run(service.list_messages(topic="expert_tasks", user_id="user-1", session_id="session-1"))

        message = data["messages"][0]
        self.assertEqual(message["session_id"], "session-1")
        self.assertEqual(message["session_name"], "制度查询")
        self.assertEqual(message["user_id"], "user-1")
        self.assertEqual(message["user_name"], "管理员")
        self.assertEqual(message["summary"], "查询制度")

    def test_rag_evaluation_message_enriches_from_evaluation_record(self):
        from internal.service.kafka_management_service import KafkaManagementService

        class RAGConsumer(FakeKafkaConsumer):
            def partitions_for_topic(self, topic):
                return {0}

            def poll(self, timeout_ms=1000, max_records=100):
                return {
                    FakeTopicPartition("rag_evaluation", 0): [
                        FakeKafkaRecord(
                            topic="rag_evaluation",
                            partition=0,
                            offset=7,
                            key="eval-1",
                            value={
                                "evaluation_id": "eval-1",
                                "question": "制度怎么查",
                                "answer": "可以查询知识库",
                                "retrieved_text": "制度正文",
                            },
                            timestamp=1782362400000,
                        )
                    ]
                }

        service = KafkaManagementService(
            kafka_config={
                "bootstrap_servers": ["8.140.245.242:9092"],
                "topics": {"rag_evaluation": "rag_evaluation"},
                "api_version": [4, 3],
            },
            consumer_cls=RAGConsumer,
            topic_partition_cls=FakeTopicPartition,
            evaluation_model=AsyncFindOneModel(FakeEvaluationRecord()),
            user_model=AsyncFindOneModel(FakeUserRecord()),
        )

        data = asyncio.run(service.list_messages(topic="rag_evaluation", evaluation_id="eval-1"))

        message = data["messages"][0]
        self.assertEqual(message["message_type"], "RAG 评估")
        self.assertEqual(message["status"], "排队中")
        self.assertEqual(message["session_id"], "session-1")
        self.assertEqual(message["user_id"], "user-1")
        self.assertEqual(message["document_uuid"], "doc-1")
        self.assertEqual(message["related_evaluation"]["id"], "eval-1")
        self.assertEqual(message["related_evaluation"]["question"], "制度怎么查")
        self.assertEqual(message["related_evaluation"]["status"], "排队中")

    def test_controller_uses_admin_guard(self):
        from api.v1 import kafka_controller

        request = SimpleNamespace()
        with patch.object(kafka_controller, "get_user_from_request", return_value={"is_admin": 0}):
            response = asyncio.run(kafka_controller.get_kafka_topics(request))

        self.assertIn(b"\xe6\x97\xa0\xe6\x9d\x83\xe8\xae\xbf\xe9\x97\xae", response.body)


if __name__ == "__main__":
    unittest.main()
