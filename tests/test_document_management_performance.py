import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from internal.document_client.message_client import MessageClient
from internal.document_client.document_processor import DocumentProcessor
from internal.service.orm.document_sever import DocumentService


class FakeUploadFile:
    def __init__(self, filename="report.pdf", content=b"file bytes"):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


class FakeDocumentRecord:
    def __init__(
        self,
        uuid="doc-1",
        name="report.pdf",
        content="",
        page=0,
        status=2,
        extra_data=None,
        url=None,
        size=123,
        permission=0,
    ):
        self.uuid = uuid
        self.name = name
        self.content = content
        self.page = page
        self.url = url or f"/uploads/{uuid}.pdf"
        self.size = size
        self.status = status
        self.permission = permission
        self.extra_data = extra_data or {}
        self.create_at = None
        self.update_at = None
        self.inserted = False
        self.saved = False

    async def insert(self):
        self.inserted = True

    async def save(self):
        self.saved = True


class FakeFindQuery:
    def __init__(self, docs):
        self.docs = docs

    async def count(self):
        return len(self.docs)

    def skip(self, skip):
        self.docs = self.docs[skip:]
        return self

    def limit(self, limit):
        self.docs = self.docs[:limit]
        return self

    async def to_list(self):
        return self.docs


class FakeDocumentModel:
    created = []
    docs = []

    uuid = object()

    def __init__(self, **kwargs):
        self.record = FakeDocumentRecord(**kwargs)
        FakeDocumentModel.created.append(self.record)

    async def insert(self):
        await self.record.insert()

    async def save(self):
        await self.record.save()

    def __getattr__(self, item):
        return getattr(self.record, item)

    def __setattr__(self, key, value):
        if key == "record":
            super().__setattr__(key, value)
        else:
            setattr(self.record, key, value)

    @classmethod
    async def count(cls):
        return len(cls.docs)

    @classmethod
    def find_all(cls):
        return FakeFindQuery(list(cls.docs))

    @classmethod
    def find(cls, query):
        return FakeFindQuery(list(cls.docs))

    @classmethod
    async def find_one(cls, condition):
        return cls.docs[0] if cls.docs else None


class DocumentManagementPerformanceTest(unittest.TestCase):
    def setUp(self):
        FakeDocumentModel.created = []
        FakeDocumentModel.docs = []

    def test_upload_returns_processing_without_parsing_document_content(self):
        service = DocumentService()
        with tempfile.TemporaryDirectory() as tmpdir:
            service.upload_dir = Path(tmpdir)
            fake_processor = SimpleNamespace(submit_task=MagicMock(return_value=True))

            with patch("internal.service.orm.document_sever.DocumentModel", FakeDocumentModel), \
                 patch("internal.service.orm.document_sever.document_processor", fake_processor), \
                 patch("internal.document_client.document_extract.DocumentExtractorManager.load_document") as load_document:
                message, ret, data = asyncio.run(
                    service.upload_document(
                        FakeUploadFile(content=b"large document"),
                        permission=0,
                        uploader_id="user-1",
                        uploader_name="admin",
                    )
                )

        self.assertEqual(message, "上传成功")
        self.assertEqual(ret, 0)
        self.assertEqual(data["status"], 1)
        self.assertEqual(data["content_length"], 0)
        self.assertEqual(FakeDocumentModel.created[0].content, "")
        load_document.assert_not_called()
        fake_processor.submit_task.assert_called_once()

    def test_list_uses_saved_chunk_counts_without_vector_counting(self):
        service = DocumentService()
        FakeDocumentModel.docs = [
            FakeDocumentRecord(uuid="doc-1", page=7, extra_data={"chunks_count": 9}),
            FakeDocumentRecord(uuid="doc-2", page=5, extra_data={}),
        ]

        service._get_chunk_count_from_vector_store = MagicMock(return_value=99)

        with patch("internal.service.orm.document_sever.DocumentModel", FakeDocumentModel):
            message, ret, data = asyncio.run(service.get_document_list(page=1, page_size=20))

        self.assertEqual(message, "查询成功")
        self.assertEqual(ret, 0)
        self.assertEqual([item["chunk_count"] for item in data["documents"]], [9, 5])
        service._get_chunk_count_from_vector_store.assert_not_called()

    def test_detail_uses_saved_chunk_count_and_returns_content(self):
        service = DocumentService()
        FakeDocumentModel.docs = [
            FakeDocumentRecord(
                uuid="doc-1",
                content="正文内容",
                page=4,
                extra_data={"chunks_count": 6},
            )
        ]
        service._get_chunk_count_from_vector_store = MagicMock(return_value=99)

        with patch("internal.service.orm.document_sever.DocumentModel", FakeDocumentModel):
            message, ret, data = asyncio.run(service.get_document_detail("doc-1"))

        self.assertEqual(message, "查询成功")
        self.assertEqual(ret, 0)
        self.assertEqual(data["content"], "正文内容")
        self.assertEqual(data["content_length"], 4)
        self.assertEqual(data["chunk_count"], 6)
        service._get_chunk_count_from_vector_store.assert_not_called()

    def test_process_file_task_writes_full_content_back_to_document(self):
        processor = DocumentProcessor()
        processor.process_file = MagicMock(return_value={
            "success": True,
            "chunks_count": 3,
            "vectors_count": 3,
            "embedding_time": 0.1,
            "processing_time": 0.2,
            "start_datetime": "2026-06-23T10:00:00",
            "complete_datetime": "2026-06-23T10:00:01",
            "full_content": "完整正文",
        })
        processor._update_document_status_sync = MagicMock()

        processor._process_file_task({
            "file_path": "uploads/doc.pdf",
            "document_uuid": "doc-1",
            "metadata": {},
            "permission": 0,
        })

        processor._update_document_status_sync.assert_called_once()
        _, kwargs = processor._update_document_status_sync.call_args
        self.assertEqual(kwargs["content"], "完整正文")
        self.assertEqual(kwargs["page"], 3)
        self.assertEqual(kwargs["extra_data_update"]["chunks_count"], 3)

    def test_kafka_common_config_is_applied_to_producer_and_consumer(self):
        with patch("internal.document_client.message_client.config") as fake_config, \
             patch("internal.document_client.message_client.get_kafka_client") as get_kafka_client:
            fake_config.message_mode = "kafka"
            fake_config.kafka_config = {
                "bootstrap_servers": ["8.140.245.242:9092"],
                "api_version": [4, 3],
                "request_timeout_ms": 10000,
                "max_block_ms": 10000,
                "topics": {"document_embedding": "document_embedding"},
                "producer": {"acks": "all", "max_block_ms": 10000},
                "consumer": {"group_id": "brainwave_embedding_group"},
            }

            client = MessageClient()

        get_kafka_client.assert_called_once()
        _, kwargs = get_kafka_client.call_args
        self.assertEqual(kwargs["bootstrap_servers"], ["8.140.245.242:9092"])
        self.assertEqual(kwargs["producer_config"]["api_version"], (4, 3))
        self.assertEqual(kwargs["consumer_config"]["api_version"], (4, 3))
        self.assertEqual(kwargs["producer_config"]["request_timeout_ms"], 10000)
        self.assertEqual(kwargs["consumer_config"]["request_timeout_ms"], 10000)
        self.assertEqual(kwargs["producer_config"]["max_block_ms"], 10000)
        self.assertNotIn("max_block_ms", kwargs["consumer_config"])
        self.assertEqual(kwargs["producer_config"]["acks"], "all")
        self.assertEqual(kwargs["consumer_config"]["group_id"], "brainwave_embedding_group")
        self.assertIs(client.client, get_kafka_client.return_value)


if __name__ == "__main__":
    unittest.main()
