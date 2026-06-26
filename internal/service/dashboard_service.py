"""Admin dashboard aggregation service."""
import asyncio
from collections import Counter, defaultdict
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel
from internal.model.document import DocumentModel
from internal.service.kafka_management_service import kafka_management_service
from log import logger


class DashboardDocumentItem(BaseModel):
    name: str = ""
    page: int = 0
    status: int = 0
    extra_data: Dict[str, Any] = {}
    url: str = ""
    create_at: Optional[datetime] = None
    update_at: Optional[datetime] = None


class DashboardService:
    async def get_overview(self) -> Dict[str, Any]:
        documents = (
            await DocumentModel.find_all(projection_model=DashboardDocumentItem)
            .sort(-DocumentModel.update_at)
            .to_list()
        )
        now = datetime.now()
        today_start = datetime.combine(now.date(), time.min)
        yesterday_start = today_start - timedelta(days=1)

        document_stats = self._document_stats(documents, today_start, yesterday_start)
        kafka_stats = await self._kafka_stats()

        return {
            "generated_at": now.isoformat(),
            "summary": {
                "document_total": document_stats["document_total"],
                "chunk_total": document_stats["chunk_total"],
                "today_updated_chunks": document_stats["today_updated_chunks"],
                "yesterday_updated_chunks": document_stats["yesterday_updated_chunks"],
                "chunk_change": document_stats["today_updated_chunks"] - document_stats["yesterday_updated_chunks"],
                "failed_documents": document_stats["status_counts"].get("处理失败", 0),
                "kafka_messages": kafka_stats["total_messages"],
                "active_partitions": kafka_stats["active_partitions"],
            },
            "documents": document_stats,
            "kafka": kafka_stats,
        }

    def _document_stats(self, documents: List[Any], today_start: datetime, yesterday_start: datetime) -> Dict[str, Any]:
        status_text = {
            0: "未处理",
            1: "处理中",
            2: "处理完成",
            3: "处理失败",
        }
        type_counts = Counter()
        type_chunks = defaultdict(int)
        status_counts = Counter()
        daily_chunks = defaultdict(int)
        today_updated_chunks = 0
        yesterday_updated_chunks = 0
        chunk_total = 0

        for doc in documents:
            chunks = self._chunk_count(doc)
            chunk_total += chunks
            label = self._file_type_label(getattr(doc, "name", ""), getattr(doc, "url", ""))
            type_counts[label] += 1
            type_chunks[label] += chunks
            status_counts[status_text.get(getattr(doc, "status", None), "未知")] += 1

            updated_at = getattr(doc, "update_at", None) or getattr(doc, "create_at", None)
            if isinstance(updated_at, datetime):
                day_key = updated_at.strftime("%m-%d")
                daily_chunks[day_key] += chunks
                if updated_at >= today_start:
                    today_updated_chunks += chunks
                elif yesterday_start <= updated_at < today_start:
                    yesterday_updated_chunks += chunks

        last_7_days = []
        base_date = today_start.date()
        for offset in range(6, -1, -1):
            day = base_date - timedelta(days=offset)
            key = day.strftime("%m-%d")
            last_7_days.append({
                "date": key,
                "chunks": daily_chunks.get(key, 0),
            })

        return {
            "document_total": len(documents),
            "chunk_total": chunk_total,
            "today_updated_chunks": today_updated_chunks,
            "yesterday_updated_chunks": yesterday_updated_chunks,
            "type_distribution": [
                {
                    "name": name,
                    "value": count,
                    "chunks": type_chunks.get(name, 0),
                }
                for name, count in type_counts.most_common()
            ],
            "status_distribution": [
                {"name": name, "value": count}
                for name, count in status_counts.items()
            ],
            "chunk_trend": last_7_days,
            "status_counts": dict(status_counts),
        }

    async def _kafka_stats(self) -> Dict[str, Any]:
        try:
            topics_result = await asyncio.wait_for(
                asyncio.to_thread(lambda: asyncio.run(kafka_management_service.get_topics())),
                timeout=1.5,
            )
            topics = topics_result.get("topics", [])
            unavailable = False
            message = ""
        except asyncio.TimeoutError:
            logger.warning("Kafka 总览读取超时")
            topics = []
            unavailable = True
            message = "队列数据暂时无法读取"
        except Exception as exc:
            logger.warning(f"Kafka 总览暂时无法读取: {exc}")
            topics = []
            unavailable = True
            message = "队列数据暂时无法读取"

        total_messages = 0
        active_partitions = 0
        topic_distribution = []
        partition_heatmap = []

        for topic in topics:
            message_count = int(topic.get("message_count") or 0)
            total_messages += message_count
            active_partitions += int(topic.get("active_partition_count") or 0)
            topic_distribution.append({
                "key": topic.get("key"),
                "name": self._topic_label(topic.get("key") or topic.get("topic") or ""),
                "topic": topic.get("topic"),
                "value": message_count,
                "partition_count": topic.get("partition_count") or 0,
                "active_partition_count": topic.get("active_partition_count") or 0,
            })
            for partition in topic.get("partitions") or []:
                partition_heatmap.append({
                    "topic": self._topic_label(topic.get("key") or topic.get("topic") or ""),
                    "partition": f"P{partition.get('partition')}",
                    "messages": int(partition.get("message_count") or 0),
                })

        topic_distribution.sort(key=lambda item: item["value"], reverse=True)
        partition_heatmap.sort(key=lambda item: item["messages"], reverse=True)

        return {
            "total_messages": total_messages,
            "active_partitions": active_partitions,
            "topic_distribution": topic_distribution,
            "partition_heatmap": partition_heatmap[:48],
            "unavailable": unavailable,
            "message": message,
        }

    def _chunk_count(self, doc: Any) -> int:
        extra_data = getattr(doc, "extra_data", None) or {}
        chunks_count = extra_data.get("chunks_count")
        if isinstance(chunks_count, int) and chunks_count >= 0:
            return chunks_count
        page = getattr(doc, "page", 0) or 0
        return page if isinstance(page, int) and page >= 0 else 0

    def _file_type_label(self, name: str, url: str) -> str:
        suffix = (Path(name or url or "").suffix or "").lower()
        return {
            ".pdf": "PDF",
            ".md": "Markdown",
            ".txt": "文本",
            ".doc": "Word",
            ".docx": "Word",
            ".ppt": "PPT",
            ".pptx": "PPT",
            ".xls": "Excel",
            ".xlsx": "Excel",
            ".csv": "CSV",
            ".json": "JSON",
            ".html": "HTML",
            ".htm": "HTML",
        }.get(suffix, "其他")

    def _topic_label(self, key: str) -> str:
        return {
            "document_embedding": "文档处理",
            "rag_evaluation": "评估任务",
            "expert_tasks": "专家任务",
            "expert_results": "专家结果",
            "expert_dead_letters": "失败队列",
        }.get(key, key)


dashboard_service = DashboardService()
