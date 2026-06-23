from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pymongo import MongoClient, UpdateOne

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from internal.db.qdrant import qdrant_client
from internal.document_client.document_extract import extractor_manager
from internal.document_client.document_processor import document_processor
from pkg.constants.constants import QDRANT_COLLECTION_NAME, MONGODB_DATABASE, MONGODB_URL
from pkg.model_list import BGE_LARGE_ZH_V1_5
from pkg.utils.password_utils import hash_password


ACCOUNT_ROWS = [
    {"uuid": "admin", "nickname": "admin", "email": "admin@rag-platform.local", "is_admin": 1},
    {"uuid": "user", "nickname": "user", "email": "user@rag-platform.local", "is_admin": 0},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild MongoDB and Qdrant knowledge data.")
    parser.add_argument("--uploads-dir", default=str(PROJECT_ROOT / "uploads"))
    parser.add_argument("--reset-vectors", action="store_true")
    parser.add_argument("--reset-documents", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def get_document_uuid(path: Path) -> str:
    return str(uuid4()) if path.stem.startswith("tmp-") else path.stem


def seed_accounts(database: Any) -> None:
    now = datetime.now()
    password = hash_password("123456")
    operations = []
    for row in ACCOUNT_ROWS:
        operations.append(
            UpdateOne(
                {"nickname": row["nickname"]},
                {
                    "$set": {
                        "uuid": row["uuid"],
                        "nickname": row["nickname"],
                        "email": row["email"],
                        "password": password,
                        "is_admin": row["is_admin"],
                        "status": 0,
                        "deleted_at": None,
                    },
                    "$setOnInsert": {
                        "avatar": "https://cube.elemecdn.com/0/88/03b0d39583f48206768a7534e55bcpng.png",
                        "gender": 0,
                        "birthday": None,
                        "created_at": now,
                    },
                },
                upsert=True,
            )
        )
    if operations:
        database.user_info.bulk_write(operations)


def upsert_document(database: Any, path: Path, document_uuid: str, permission: int) -> None:
    now = datetime.now()
    database.documents.update_one(
        {"uuid": document_uuid},
        {
            "$set": {
                "uuid": document_uuid,
                "name": path.name,
                "content": "",
                "page": 0,
                "url": f"/uploads/{path.name}",
                "size": path.stat().st_size,
                "status": 1,
                "permission": permission,
                "update_at": now,
                "extra_data": {
                    "uploader_id": "admin",
                    "uploader_name": "admin",
                    "upload_time": now.isoformat(),
                    "file_extension": path.suffix.lower(),
                    "embedding_model": BGE_LARGE_ZH_V1_5.name,
                    "embedding_dimension": BGE_LARGE_ZH_V1_5.dimension,
                },
            },
            "$setOnInsert": {"create_at": now},
        },
        upsert=True,
    )


def update_document_result(database: Any, document_uuid: str, result: dict[str, Any]) -> None:
    now = datetime.now()
    status = 2 if result.get("success") else 3
    database.documents.update_one(
        {"uuid": document_uuid},
        {
            "$set": {
                "status": status,
                "page": result.get("chunks_count", 0),
                "update_at": now,
                "extra_data": {
                    "embedding_model": BGE_LARGE_ZH_V1_5.name,
                    "embedding_dimension": BGE_LARGE_ZH_V1_5.dimension,
                    "chunks_count": result.get("chunks_count", 0),
                    "vectors_count": result.get("vectors_count", 0),
                    "processing_time_seconds": result.get("processing_time"),
                    "embedding_time_seconds": result.get("embedding_time"),
                    "message": result.get("message", ""),
                },
            }
        },
    )


def list_upload_files(uploads_dir: Path, limit: int) -> list[Path]:
    files = [
        path
        for path in sorted(uploads_dir.iterdir())
        if path.is_file() and extractor_manager.is_supported(str(path))
    ]
    return files[:limit] if limit > 0 else files


def main() -> int:
    args = parse_args()
    uploads_dir = Path(args.uploads_dir).resolve()
    if not uploads_dir.exists():
        print(f"uploads 目录不存在: {uploads_dir}")
        return 1

    client = MongoClient(MONGODB_URL)
    database = client[MONGODB_DATABASE]
    database.command("ping")

    qdrant_client.ensure_collection(QDRANT_COLLECTION_NAME)
    if args.reset_vectors:
        for document in database.documents.find({}, {"uuid": 1}):
            qdrant_client.delete_by_document_uuid(document["uuid"], collection_name=QDRANT_COLLECTION_NAME)
    if args.reset_documents:
        database.documents.delete_many({})

    seed_accounts(database)

    files = list_upload_files(uploads_dir, args.limit)
    if not files:
        print("没有找到可解析的上传文件")
        return 1

    succeeded = 0
    failed = 0
    total_chunks = 0
    for path in files:
        document_uuid = get_document_uuid(path)
        permission = 1 if "admin" in path.name.lower() else 0
        upsert_document(database, path, document_uuid, permission)
        result = document_processor.process_file(
            file_path=str(path),
            document_uuid=document_uuid,
            collection_name=QDRANT_COLLECTION_NAME,
            extra_metadata={"source_name": path.name},
            permission=permission,
        )
        update_document_result(database, document_uuid, result)
        if result.get("success"):
            succeeded += 1
            total_chunks += int(result.get("chunks_count", 0))
        else:
            failed += 1
            print(f"解析失败: {path.name} - {result.get('message', '')}")

    print(f"文档总数: {len(files)}")
    print(f"解析成功: {succeeded}")
    print(f"解析失败: {failed}")
    print(f"分块总数: {total_chunks}")
    return 0 if succeeded > 0 and failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
