import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from internal.document_client.document_processor import DocumentProcessor
from internal.service.orm.document_sever import DocumentService


class FakeUploadFile:
    def __init__(self, filename="notes.md", content=b"same file content"):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


class FakeDocumentRecord:
    def __init__(
        self,
        uuid="doc-existing",
        name="notes.md",
        content="",
        page=0,
        status=2,
        extra_data=None,
        url="/uploads/doc-existing.md",
        size=17,
        permission=0,
    ):
        self.uuid = uuid
        self.name = name
        self.content = content
        self.page = page
        self.status = status
        self.extra_data = extra_data or {}
        self.url = url
        self.size = size
        self.permission = permission
        self.create_at = None
        self.update_at = None
        self.inserted = False
        self.saved = False

    async def insert(self):
        self.inserted = True

    async def save(self):
        self.saved = True


class FakeDocumentModel:
    docs = []
    created = []
    last_find_query = None

    uuid = object()
    permission = object()
    status = object()
    extra_data = object()

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
    def find(cls, query):
        cls.last_find_query = query

        class Query:
            async def to_list(self):
                file_sha256 = query.get("extra_data.file_sha256")
                permission = query.get("permission")
                statuses = query.get("status", {}).get("$in", [])
                return [
                    doc for doc in cls.docs
                    if doc.extra_data.get("file_sha256") == file_sha256
                    and doc.permission == permission
                    and doc.status in statuses
                ]

        return Query()

    @classmethod
    async def find_one(cls, condition):
        return cls.docs[0] if cls.docs else None


class DocumentUploadDeduplicationTest(unittest.TestCase):
    def setUp(self):
        FakeDocumentModel.docs = []
        FakeDocumentModel.created = []
        FakeDocumentModel.last_find_query = None

    def test_duplicate_file_returns_existing_document_without_submitting_task(self):
        service = DocumentService()
        existing_hash = service._calculate_file_sha256(b"same file content")
        FakeDocumentModel.docs = [
            FakeDocumentRecord(
                uuid="doc-existing",
                name="old-name.md",
                page=4,
                status=2,
                permission=0,
                extra_data={"file_sha256": existing_hash, "chunks_count": 4},
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            service.upload_dir = Path(tmpdir)
            fake_processor = SimpleNamespace(submit_task=MagicMock(return_value=True))

            with patch("internal.service.orm.document_sever.DocumentModel", FakeDocumentModel), \
                 patch("internal.service.orm.document_sever.document_processor", fake_processor):
                message, ret, data = asyncio.run(
                    service.upload_document(
                        FakeUploadFile(filename="new-name.md", content=b"same file content"),
                        permission=0,
                        uploader_id="user-1",
                        uploader_name="admin",
                    )
                )
                saved_files = list(Path(tmpdir).iterdir())

        self.assertEqual(message, "文档已存在")
        self.assertEqual(ret, 0)
        self.assertEqual(data["uuid"], "doc-existing")
        self.assertEqual(data["dedup_status"], "duplicate")
        self.assertEqual(data["original_document_uuid"], "doc-existing")
        self.assertEqual(FakeDocumentModel.last_find_query["permission"], 0)
        self.assertEqual(FakeDocumentModel.last_find_query["status"], {"$in": [1, 2]})
        self.assertIn("extra_data.file_sha256", FakeDocumentModel.last_find_query)
        self.assertEqual(FakeDocumentModel.created, [])
        fake_processor.submit_task.assert_not_called()
        self.assertEqual(saved_files, [])

    def test_same_file_hash_with_different_permission_creates_independent_document(self):
        service = DocumentService()
        existing_hash = service._calculate_file_sha256(b"same file content")
        FakeDocumentModel.docs = [
            FakeDocumentRecord(
                uuid="doc-admin",
                status=2,
                permission=1,
                extra_data={"file_sha256": existing_hash},
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            service.upload_dir = Path(tmpdir)
            fake_processor = SimpleNamespace(submit_task=MagicMock(return_value=True))

            with patch("internal.service.orm.document_sever.DocumentModel", FakeDocumentModel), \
                 patch("internal.service.orm.document_sever.document_processor", fake_processor):
                message, ret, data = asyncio.run(
                    service.upload_document(
                        FakeUploadFile(content=b"same file content"),
                        permission=0,
                        uploader_id="user-1",
                        uploader_name="admin",
                    )
                )

        self.assertEqual(message, "上传成功")
        self.assertEqual(ret, 0)
        self.assertEqual(data["dedup_status"], "new")
        self.assertEqual(len(FakeDocumentModel.created), 1)
        fake_processor.submit_task.assert_called_once()

    def test_retry_failed_document_reuses_existing_uuid_and_marks_queued(self):
        service = DocumentService()
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "doc-retry.md"
            file_path.write_text("可以重新处理的内容", encoding="utf-8")
            service.upload_dir = Path(tmpdir)
            failed_doc = FakeDocumentRecord(
                uuid="doc-retry",
                name="doc-retry.md",
                status=3,
                permission=0,
                url=str(file_path),
                extra_data={"retry_count": 1, "uploader_id": "admin", "uploader_name": "admin"},
            )
            FakeDocumentModel.docs = [failed_doc]
            fake_processor = SimpleNamespace(submit_task=MagicMock(return_value=True))

            with patch("internal.service.orm.document_sever.DocumentModel", FakeDocumentModel), \
                 patch("internal.service.orm.document_sever.document_processor", fake_processor):
                message, ret, data = asyncio.run(service.retry_document_processing("doc-retry"))

        self.assertEqual(message, "已重新提交处理")
        self.assertEqual(ret, 0)
        self.assertEqual(data["uuid"], "doc-retry")
        self.assertEqual(failed_doc.status, 1)
        self.assertEqual(failed_doc.extra_data["processing_stage"], "queued")
        self.assertEqual(failed_doc.extra_data["retry_count"], 2)
        fake_processor.submit_task.assert_called_once()
        task = fake_processor.submit_task.call_args.args[0]
        self.assertEqual(task["document_uuid"], "doc-retry")

    def test_exact_duplicate_chunks_are_removed_before_embedding(self):
        processor = DocumentProcessor()
        chunks = [
            {"content": "第一步：创建项目", "metadata": {"chunk_index": 0}},
            {"content": "第一步：创建项目", "metadata": {"chunk_index": 1}},
            {"content": "第一步：创建项目 1", "metadata": {"chunk_index": 2}},
            {"content": "```python\nprint(1)\n```", "metadata": {"chunk_index": 3}},
            {"content": "```python\nprint(2)\n```", "metadata": {"chunk_index": 4}},
        ]

        deduped, stats = processor._deduplicate_exact_chunks(chunks)

        self.assertEqual([chunk["content"] for chunk in deduped], [
            "第一步：创建项目",
            "第一步：创建项目 1",
            "```python\nprint(1)\n```",
            "```python\nprint(2)\n```",
        ])
        self.assertEqual(stats["raw_chunks_count"], 5)
        self.assertEqual(stats["deduped_chunks_count"], 4)
        self.assertEqual(stats["duplicate_chunks_removed"], 1)


if __name__ == "__main__":
    unittest.main()
