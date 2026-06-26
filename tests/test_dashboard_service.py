import unittest
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from internal.service.dashboard_service import DashboardService


class FakeDashboardQuery:
    projection_model = None

    def sort(self, *args, **kwargs):
        return self

    async def to_list(self):
        return [
            SimpleNamespace(
                name="a.pdf",
                url="/uploads/a.pdf",
                page=2,
                status=2,
                extra_data={"chunks_count": 8},
                create_at=datetime.now() - timedelta(days=1),
                update_at=datetime.now(),
            )
        ]


class FakeDashboardDocumentModel:
    update_at = 1

    @classmethod
    def find_all(cls, projection_model=None):
        FakeDashboardQuery.projection_model = projection_model
        return FakeDashboardQuery()


class DashboardServiceTest(unittest.IsolatedAsyncioTestCase):
    async def test_overview_loads_only_dashboard_document_fields(self):
        FakeDashboardQuery.projection_model = None
        service = DashboardService()

        with patch("internal.service.dashboard_service.DocumentModel", FakeDashboardDocumentModel), \
                patch.object(service, "_kafka_stats", new=AsyncMock(return_value={
                    "total_messages": 0,
                    "active_partitions": 0,
                    "topic_distribution": [],
                    "partition_heatmap": [],
                    "unavailable": True,
                    "message": "队列数据暂时无法读取",
                })):
            overview = await service.get_overview()

        self.assertEqual(overview["summary"]["document_total"], 1)
        self.assertEqual(overview["summary"]["chunk_total"], 8)
        self.assertIsNotNone(FakeDashboardQuery.projection_model)
        self.assertFalse(hasattr(FakeDashboardQuery.projection_model, "content"))

    async def test_kafka_stats_returns_when_topic_read_blocks(self):
        service = DashboardService()

        async def blocking_topic_read():
            time.sleep(2.5)
            return {"topics": [{"key": "expert_tasks", "topic": "expert_tasks", "message_count": 99}]}

        started = time.monotonic()
        with patch("internal.service.dashboard_service.kafka_management_service.get_topics", blocking_topic_read):
            stats = await service._kafka_stats()
        elapsed = time.monotonic() - started

        self.assertLess(elapsed, 2.3)
        self.assertTrue(stats["unavailable"])
        self.assertEqual(stats["total_messages"], 0)


if __name__ == "__main__":
    unittest.main()
