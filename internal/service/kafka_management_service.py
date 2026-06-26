"""Kafka management read service."""
from datetime import datetime
from typing import Any, Dict, List, Optional
import json

from kafka import KafkaConsumer, TopicPartition

from internal.document_client.config_loader import config
from internal.model.document import DocumentModel
from internal.model.evaluation import EvaluationModel
from internal.model.message import MessageModel
from internal.model.session import SessionModel
from internal.model.user_info import UserInfoModel
from log import logger


class KafkaManagementService:
    def __init__(
        self,
        kafka_config: Optional[Dict[str, Any]] = None,
        consumer_cls=KafkaConsumer,
        topic_partition_cls=TopicPartition,
        evaluation_model=EvaluationModel,
        message_model=MessageModel,
        session_model=SessionModel,
        user_model=UserInfoModel,
        document_model=DocumentModel,
    ):
        self.kafka_config = kafka_config if kafka_config is not None else config.kafka_config
        self.consumer_cls = consumer_cls
        self.topic_partition_cls = topic_partition_cls
        self.evaluation_model = evaluation_model
        self.message_model = message_model
        self.session_model = session_model
        self.user_model = user_model
        self.document_model = document_model

    async def get_topics(self) -> Dict[str, Any]:
        topics = self._configured_topics()
        consumer = self._create_consumer()
        try:
            rows = []
            for key, topic in topics.items():
                partitions = consumer.partitions_for_topic(topic) or set()
                topic_partitions = [self.topic_partition_cls(topic, partition) for partition in sorted(partitions)]
                latest_offset = 0
                message_count = 0
                partition_rows = []
                if topic_partitions:
                    end_offsets = consumer.end_offsets(topic_partitions)
                    beginning_offsets = consumer.beginning_offsets(topic_partitions)
                    latest_offset = sum(end_offsets.values())
                    for partition in topic_partitions:
                        beginning_offset = int(beginning_offsets.get(partition, 0) or 0)
                        end_offset = int(end_offsets.get(partition, 0) or 0)
                        count = max(0, end_offset - beginning_offset)
                        message_count += count
                        partition_rows.append({
                            "partition": partition.partition,
                            "beginning_offset": beginning_offset,
                            "end_offset": end_offset,
                            "message_count": count,
                        })
                active_partition_count = sum(1 for item in partition_rows if item["message_count"] > 0)
                rows.append({
                    "key": key,
                    "topic": topic,
                    "partition_count": len(partitions),
                    "active_partition_count": active_partition_count,
                    "empty_partition_count": max(0, len(partitions) - active_partition_count),
                    "latest_offset": latest_offset,
                    "message_count": message_count,
                    "partitions": partition_rows,
                    "consumer_group": self._consumer_group_for(key),
                })
            return {"topics": rows}
        finally:
            consumer.close()

    async def list_messages(
        self,
        topic: Optional[str] = None,
        keyword: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        question_id: Optional[str] = None,
        task_id: Optional[str] = None,
        expert_key: Optional[str] = None,
        evaluation_id: Optional[str] = None,
        document_uuid: Optional[str] = None,
        status: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 200,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        limit = max(1, min(int(limit or 200), 500))
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 20), 100))
        if not topic:
            return {
                "messages": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "topic_selected": False,
                "has_more": False,
            }
        topics = self._selected_topics(topic)
        if not topics:
            return {
                "messages": [],
                "total": 0,
                "page": page,
                "page_size": page_size,
                "topic_selected": False,
                "has_more": False,
            }
        messages = []
        scan_limit = min(500, max(limit, page * page_size * 2, page_size))
        expert_name_map = await self._load_agent_name_map()
        for topic_key, topic_name in topics.items():
            raw_messages = await self._read_recent_topic(topic_key, topic_name, scan_limit)
            expert_status_index = await self._build_expert_status_index(scan_limit) if topic_key == "expert_tasks" else {}
            for item in raw_messages:
                if item.get("expert_key"):
                    item["expert_name"] = self._expert_display_name(item.get("expert_key"), expert_name_map)
                if expert_status_index:
                    self._apply_expert_status(item, expert_status_index)
                enriched = await self._enrich_message(item)
                if self._matches(
                    enriched,
                    keyword=keyword,
                    user_id=user_id,
                    session_id=session_id,
                    question_id=question_id,
                    task_id=task_id,
                    expert_key=expert_key,
                    evaluation_id=evaluation_id,
                    document_uuid=document_uuid,
                    status=status,
                    start_time=start_time,
                    end_time=end_time,
                ):
                    messages.append(enriched)
        messages.sort(key=lambda row: row.get("timestamp") or "", reverse=True)
        total = len(messages)
        start = (page - 1) * page_size
        end = start + page_size
        return {
            "messages": messages[start:end],
            "total": total,
            "page": page,
            "page_size": page_size,
            "topic_selected": True,
            "has_more": end < total,
        }

    async def get_message_detail(self, topic: str, partition: int, offset: int) -> Optional[Dict[str, Any]]:
        topic_pairs = self._selected_topics(topic)
        if not topic_pairs:
            return None
        topic_key, topic_name = next(iter(topic_pairs.items()))
        consumer = self._create_consumer()
        try:
            topic_partition = self.topic_partition_cls(topic_name, int(partition))
            consumer.assign([topic_partition])
            consumer.seek(topic_partition, int(offset))
            batch = consumer.poll(timeout_ms=1000, max_records=1)
            for _partition, records in batch.items():
                for record in records:
                    if record.offset == int(offset):
                        item = self._record_to_message(topic_key, record)
                        if item.get("expert_key"):
                            item["expert_name"] = self._expert_display_name(item.get("expert_key"), await self._load_agent_name_map())
                        return await self._enrich_message(item)
            return None
        finally:
            consumer.close()

    def _configured_topics(self) -> Dict[str, str]:
        return dict(self.kafka_config.get("topics") or {})

    def _selected_topics(self, topic: Optional[str]) -> Dict[str, str]:
        topics = self._configured_topics()
        if not topic:
            return topics
        if topic in topics:
            return {topic: topics[topic]}
        for key, value in topics.items():
            if value == topic:
                return {key: value}
        return {}

    def _consumer_group_for(self, topic_key: str) -> str:
        groups = self.kafka_config.get("consumer_groups") or {}
        return groups.get(topic_key, self.kafka_config.get("consumer", {}).get("group_id", ""))

    def _common_consumer_config(self) -> Dict[str, Any]:
        common = {
            key: self.kafka_config[key]
            for key in ("api_version", "request_timeout_ms")
            if key in self.kafka_config
        }
        if isinstance(common.get("api_version"), list):
            common["api_version"] = tuple(common["api_version"])
        consumer_config = {**common, **(self.kafka_config.get("consumer") or {})}
        consumer_config.pop("group_id", None)
        consumer_config["enable_auto_commit"] = False
        consumer_config["auto_offset_reset"] = "latest"
        consumer_config["value_deserializer"] = self._deserialize_value
        consumer_config["key_deserializer"] = lambda key: key.decode("utf-8") if key else None
        return consumer_config

    def _create_consumer(self):
        return self.consumer_cls(
            bootstrap_servers=self.kafka_config.get("bootstrap_servers", ["8.140.245.242:9092"]),
            **self._common_consumer_config(),
        )

    async def _read_recent_topic(self, topic_key: str, topic_name: str, limit: int) -> List[Dict[str, Any]]:
        consumer = self._create_consumer()
        try:
            partitions = consumer.partitions_for_topic(topic_name) or set()
            topic_partitions = [self.topic_partition_cls(topic_name, partition) for partition in sorted(partitions)]
            if not topic_partitions:
                return []
            consumer.assign(topic_partitions)
            end_offsets = consumer.end_offsets(topic_partitions)
            beginning_offsets = consumer.beginning_offsets(topic_partitions)
            per_partition = max(1, min(limit, 500))
            for partition in topic_partitions:
                end_offset = end_offsets.get(partition, 0)
                start_offset = max(beginning_offsets.get(partition, 0), end_offset - per_partition)
                consumer.seek(partition, start_offset)
            records = []
            seen_offsets = set()
            while len(records) < limit:
                batch = consumer.poll(timeout_ms=1000, max_records=limit - len(records))
                if not batch:
                    break
                new_count = 0
                for _partition, messages in batch.items():
                    for message in messages:
                        offset_key = (message.topic, message.partition, message.offset)
                        if offset_key in seen_offsets:
                            continue
                        seen_offsets.add(offset_key)
                        records.append(self._record_to_message(topic_key, message))
                        new_count += 1
                        if len(records) >= limit:
                            break
                    if len(records) >= limit:
                        break
                if new_count == 0:
                    break
            return records
        finally:
            consumer.close()

    def _record_to_message(self, topic_key: str, record) -> Dict[str, Any]:
        payload = record.value if isinstance(record.value, dict) else {"value": record.value}
        timestamp = None
        if getattr(record, "timestamp", None):
            timestamp = datetime.fromtimestamp(record.timestamp / 1000).isoformat()
        base = {
            "topic_key": topic_key,
            "topic": record.topic,
            "partition": record.partition,
            "offset": record.offset,
            "key": record.key,
            "timestamp": timestamp,
            "payload": payload,
        }
        base.update(self._project_payload(topic_key, payload))
        return base

    def _project_payload(self, topic_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if topic_key == "rag_evaluation":
            return {
                "message_type": "RAG 评估",
                "status": self._status_text(payload.get("queue_status") or payload.get("ragas_status") or "queued"),
                "evaluation_id": payload.get("evaluation_id"),
                "summary": payload.get("question") or payload.get("retrieved_text") or "",
            }
        if topic_key in ("expert_tasks", "expert_results", "expert_dead_letters"):
            status = "待处理"
            if topic_key == "expert_results":
                status = "已完成" if payload.get("success", True) else "失败"
            if topic_key == "expert_dead_letters":
                status = "失败"
            return {
                "message_type": {
                    "expert_tasks": "专家任务",
                    "expert_results": "专家结果",
                    "expert_dead_letters": "失败任务",
                }.get(topic_key, "专家消息"),
                "status": status,
                "question_id": payload.get("question_id"),
                "task_id": payload.get("task_id"),
                "expert_key": payload.get("expert_key"),
                "expert_name": self._expert_display_name(payload.get("expert_key")),
                "answer": payload.get("answer"),
                "error": payload.get("error"),
                "success": payload.get("success"),
                "retry_count": payload.get("retry_count"),
                "summary": payload.get("task") or payload.get("answer") or payload.get("error") or "",
            }
        return {
            "message_type": "文档任务",
            "status": self._document_status_text(payload.get("status")),
            "document_uuid": payload.get("document_uuid"),
            "summary": payload.get("filename") or payload.get("document_uuid") or payload.get("task_type") or "",
        }

    async def _enrich_message(self, item: Dict[str, Any]) -> Dict[str, Any]:
        payload = item.get("payload") or {}
        if item.get("topic_key") == "rag_evaluation":
            await self._enrich_from_evaluation(item, payload.get("evaluation_id"))
        if item.get("question_id"):
            await self._enrich_from_question(item, item.get("question_id"))
        if item.get("document_uuid"):
            await self._enrich_from_document(item, item.get("document_uuid"))
        if item.get("session_id"):
            await self._enrich_from_session(item, item.get("session_id"))
        if item.get("user_id"):
            await self._enrich_from_user(item, item.get("user_id"))
        return item

    async def _build_expert_status_index(self, limit: int) -> Dict[str, Dict[str, Any]]:
        topics = self._configured_topics()
        status_index: Dict[str, Dict[str, Any]] = {}
        for topic_key in ("expert_results", "expert_dead_letters"):
            topic_name = topics.get(topic_key)
            if not topic_name:
                continue
            try:
                messages = await self._read_recent_topic(topic_key, topic_name, limit)
            except Exception:
                messages = []
            for message in messages:
                task_id = str(message.get("task_id") or "")
                if not task_id:
                    continue
                status_index[task_id] = message
        return status_index

    def _apply_expert_status(self, item: Dict[str, Any], status_index: Dict[str, Dict[str, Any]]) -> None:
        task_id = str(item.get("task_id") or "")
        if not task_id:
            return
        related = status_index.get(task_id)
        if not related:
            return
        item["related_result"] = related
        item["status"] = related.get("status") or item.get("status")

    async def _load_agent_name_map(self) -> Dict[str, str]:
        try:
            from internal.service.orm.agent_config_service import agent_config_service

            data = await agent_config_service.list_agents(page=1, page_size=500)
            return {
                item.get("agent_key"): item.get("agent_name")
                for item in data.get("items", [])
                if item.get("agent_key") and item.get("agent_name")
            }
        except Exception:
            return {}

    @staticmethod
    def _expert_display_name(expert_key: Optional[str], agent_name_map: Optional[Dict[str, str]] = None) -> str:
        key = str(expert_key or "")
        if agent_name_map and agent_name_map.get(key):
            return agent_name_map[key]
        names = {
            "knowledge": "知识库专家",
            "search": "搜索专家",
            "location": "位置专家",
            "email": "邮件专家",
        }
        return names.get(key, key or "-")

    async def _enrich_from_evaluation(self, item: Dict[str, Any], evaluation_id: Optional[str]) -> None:
        if not evaluation_id:
            return
        try:
            record = await self.evaluation_model.get(evaluation_id) if hasattr(self.evaluation_model, "get") else None
        except Exception:
            record = None
        if not record:
            try:
                record = await self.evaluation_model.find_one(self.evaluation_model.id == evaluation_id) if hasattr(self.evaluation_model, "id") else await self.evaluation_model.find_one(evaluation_id)
            except Exception:
                record = None
        if not record:
            return
        item["session_id"] = getattr(record, "session_id", None)
        item["user_id"] = getattr(record, "user_id", None)
        item["message_id"] = getattr(record, "message_id", None)
        item["document_uuid"] = getattr(record, "document_uuid", None)
        item["filename"] = getattr(record, "filename", None)
        item["status"] = self._status_text(getattr(record, "queue_status", None) or getattr(record, "ragas_status", None))
        item["related_evaluation"] = self._serialize_evaluation_record(record)

    async def _enrich_from_question(self, item: Dict[str, Any], question_id: str) -> None:
        try:
            record = await self.message_model.find_one({"extra_data.question_id": question_id})
        except Exception:
            record = None
        if not record:
            return
        item["message_id"] = getattr(record, "uuid", None)
        item["session_id"] = getattr(record, "session_id", None)
        item["user_id"] = getattr(record, "send_id", None)
        item["message_content"] = getattr(record, "content", None)

    async def _enrich_from_session(self, item: Dict[str, Any], session_id: str) -> None:
        try:
            record = await self.session_model.find_one(self.session_model.uuid == session_id)
        except Exception:
            record = None
        if record:
            item["session_name"] = getattr(record, "name", None)
            item["user_id"] = item.get("user_id") or getattr(record, "user_id", None)

    async def _enrich_from_user(self, item: Dict[str, Any], user_id: str) -> None:
        try:
            record = await self.user_model.find_one(self.user_model.uuid == user_id)
        except Exception:
            record = None
        if record:
            item["user_name"] = getattr(record, "nickname", None)
            item["user_email"] = getattr(record, "email", None)

    async def _enrich_from_document(self, item: Dict[str, Any], document_uuid: str) -> None:
        try:
            record = await self.document_model.find_one(self.document_model.uuid == document_uuid)
        except Exception:
            record = None
        if record:
            item["filename"] = getattr(record, "name", None)
            item["document_status"] = self._document_status_text(getattr(record, "status", None))
            extra_data = getattr(record, "extra_data", None) or {}
            item["user_id"] = item.get("user_id") or extra_data.get("uploader_id")
            item["user_name"] = item.get("user_name") or extra_data.get("uploader_name")

    def _matches(self, item: Dict[str, Any], **filters) -> bool:
        for key in ("user_id", "session_id", "question_id", "task_id", "expert_key", "evaluation_id", "document_uuid"):
            value = filters.get(key)
            if value and item.get(key) != value:
                return False
        status = filters.get("status")
        if status and status not in (item.get("status") or ""):
            return False
        keyword = filters.get("keyword")
        if keyword:
            haystack = json.dumps(item, ensure_ascii=False)
            if keyword not in haystack:
                return False
        start_time = filters.get("start_time")
        end_time = filters.get("end_time")
        timestamp = item.get("timestamp") or ""
        if start_time and timestamp < start_time:
            return False
        if end_time and timestamp > end_time:
            return False
        return True

    @staticmethod
    def _deserialize_value(value):
        if value is None:
            return None
        try:
            return json.loads(value.decode("utf-8"))
        except Exception:
            return value.decode("utf-8", errors="ignore")

    @staticmethod
    def _status_text(status: Optional[str]) -> str:
        mapping = {
            "queued": "排队中",
            "pending": "待评估",
            "running": "评估中",
            "completed": "已完成",
            "failed": "失败",
            "skipped": "已跳过",
        }
        return mapping.get(status or "", status or "待处理")

    @staticmethod
    def _document_status_text(status: Optional[int]) -> str:
        return {
            0: "未处理",
            1: "处理中",
            2: "已完成",
            3: "失败",
        }.get(status, "待处理")

    def _serialize_evaluation_record(self, record: Any) -> Dict[str, Any]:
        created_at = getattr(record, "created_at", None)
        queued_at = getattr(record, "queued_at", None)
        completed_at = getattr(record, "completed_at", None)
        return {
            "id": str(getattr(record, "id", "") or ""),
            "question": getattr(record, "question", "") or "",
            "answer": getattr(record, "answer", "") or "",
            "retrieved_text": getattr(record, "retrieved_text", "") or "",
            "filename": getattr(record, "filename", "") or "",
            "document_uuid": getattr(record, "document_uuid", "") or "",
            "overall_score": getattr(record, "overall_score", 0.0) or 0.0,
            "faithfulness": getattr(record, "faithfulness", 0.0) or 0.0,
            "answer_relevance": getattr(record, "answer_relevance", 0.0) or 0.0,
            "context_precision": getattr(record, "context_precision", 0.0) or 0.0,
            "context_recall": getattr(record, "context_recall", 0.0) or 0.0,
            "ragas_status": getattr(record, "ragas_status", "") or "",
            "queue_status": getattr(record, "queue_status", "") or "",
            "status": self._status_text(getattr(record, "queue_status", None) or getattr(record, "ragas_status", None)),
            "ragas_error": getattr(record, "ragas_error", "") or "",
            "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else "",
            "queued_at": queued_at.isoformat() if hasattr(queued_at, "isoformat") else "",
            "completed_at": completed_at.isoformat() if hasattr(completed_at, "isoformat") else "",
        }


kafka_management_service = KafkaManagementService()
