import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from internal.document_client.document_extract.extractors import TextExtractor
from internal.document_client.document_processor import DocumentProcessor


class DocumentProcessingRecoveryTest(unittest.TestCase):
    def test_text_extractor_reads_utf16_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "requirements.txt"
            file_path.write_text("aiohttp==3.11.18\nfastapi==0.115.0", encoding="utf-16")

            content = TextExtractor().extract_from_file(str(file_path))

        self.assertIn("aiohttp==3.11.18", content)
        self.assertIn("fastapi==0.115.0", content)

    def test_empty_text_file_returns_clear_failure_reason(self):
        processor = DocumentProcessor()
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "empty.md"
            file_path.write_text("", encoding="utf-8")

            result = processor.process_file(str(file_path), "doc-empty")

        self.assertFalse(result["success"])
        self.assertEqual(result["failure_stage"], "extract")
        self.assertEqual(result["message"], "文件内容为空")

    def test_failed_file_task_persists_failure_metadata(self):
        processor = DocumentProcessor()
        processor.process_file = MagicMock(return_value={
            "success": False,
            "message": "文件内容为空",
            "failure_stage": "split",
        })
        processor._update_document_status_sync = MagicMock()

        processor._process_file_task({
            "file_path": "uploads/empty.md",
            "document_uuid": "doc-empty",
            "metadata": {},
            "permission": 0,
        })

        processor._update_document_status_sync.assert_any_call(
            "doc-empty",
            status=1,
            extra_data_update=unittest.mock.ANY,
        )
        processor._update_document_status_sync.assert_any_call(
            "doc-empty",
            status=3,
            extra_data_update=unittest.mock.ANY,
        )
        failure_call = processor._update_document_status_sync.call_args_list[-1]
        extra_data = failure_call.kwargs["extra_data_update"]
        self.assertEqual(extra_data["failure_stage"], "split")
        self.assertEqual(extra_data["failure_reason"], "文件内容为空")
        self.assertIn("failed_at", extra_data)


if __name__ == "__main__":
    unittest.main()
