import json
import unittest

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient


class ReturnLoggingMiddlewareTest(unittest.TestCase):
    def test_json_response_body_is_logged_and_returned_unchanged(self):
        from pkg.middleware.response_logger import ReturnLoggingMiddleware
        from pkg.utils.return_logger import record_database_duration

        records = []
        app = FastAPI()
        app.add_middleware(ReturnLoggingMiddleware, log_sink=records.append)

        @app.get("/items")
        async def items():
            record_database_duration(12.5)
            return JSONResponse({"name": "报告", "count": 2})

        response = TestClient(app).get("/items")

        self.assertEqual(200, response.status_code)
        self.assertEqual({"name": "报告", "count": 2}, response.json())
        self.assertEqual(1, len(records))
        self.assertEqual("GET", records[0]["method"])
        self.assertEqual("/items", records[0]["path"])
        self.assertEqual(200, records[0]["status_code"])
        self.assertEqual(12.5, records[0]["database_duration_ms"])
        self.assertEqual(1, records[0]["database_query_count"])
        self.assertEqual('{"name":"报告","count":2}', records[0]["body"])

    def test_long_json_response_body_is_truncated_in_log_record(self):
        from pkg.middleware.response_logger import ReturnLoggingMiddleware

        records = []
        app = FastAPI()
        app.add_middleware(ReturnLoggingMiddleware, log_sink=records.append)

        @app.get("/items")
        async def items():
            return JSONResponse({"content": "一二三四五六七八九十" * 50})

        response = TestClient(app).get("/items")

        self.assertEqual(200, response.status_code)
        self.assertEqual("一二三四五六七八九十" * 50, response.json()["content"])
        self.assertEqual(403, len(records[0]["body"]))
        self.assertTrue(records[0]["body"].endswith("..."))

    def test_event_stream_response_is_not_consumed(self):
        from pkg.middleware.response_logger import ReturnLoggingMiddleware

        records = []
        app = FastAPI()
        app.add_middleware(ReturnLoggingMiddleware, log_sink=records.append)

        @app.get("/stream")
        async def stream():
            async def events():
                yield "event: answer_chunk\n"
                yield 'data: {"content": "你好"}\n\n'

            return StreamingResponse(events(), media_type="text/event-stream")

        response = TestClient(app).get("/stream")

        self.assertEqual(200, response.status_code)
        self.assertIn("event: answer_chunk", response.text)
        self.assertEqual([], records)


class DatabaseReturnLoggerTest(unittest.TestCase):
    def test_database_logger_can_be_installed_more_than_once(self):
        from pkg.middleware.database_logger import install_database_return_logger

        install_database_return_logger()
        install_database_return_logger()


if __name__ == "__main__":
    unittest.main()
