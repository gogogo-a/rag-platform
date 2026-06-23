from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from internal.document_client.document_extract import extractor_manager
from pkg.constants.constants import MONGODB_DATABASE, MONGODB_URL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill empty document content from uploaded files.")
    parser.add_argument("--uploads-dir", default=str(PROJECT_ROOT / "uploads"))
    parser.add_argument("--limit", type=int, default=0)
    return parser.parse_args()


def resolve_upload_path(uploads_dir: Path, document: dict[str, Any]) -> Path | None:
    url = document.get("url") or ""
    if url:
        path = PROJECT_ROOT / url.lstrip("/")
        if path.exists():
            return path
        fallback = uploads_dir / Path(url).name
        if fallback.exists():
            return fallback

    document_uuid = document.get("uuid")
    if not document_uuid:
        return None

    for path in uploads_dir.glob(f"{document_uuid}.*"):
        if path.is_file():
            return path
    return None


def extract_content(path: Path) -> tuple[str, int]:
    loaded_docs = extractor_manager.load_document(str(path))
    content = "\n\n".join(doc.get("content", "") for doc in loaded_docs)
    return content, len(loaded_docs)


def backfill_documents(database: Any, uploads_dir: Path, limit: int) -> dict[str, int]:
    query = {"$or": [{"content": {"$exists": False}}, {"content": ""}, {"content": None}]}
    cursor = database.documents.find(query, {"uuid": 1, "name": 1, "url": 1, "page": 1}).sort("create_at", -1)
    if limit > 0:
        cursor = cursor.limit(limit)

    stats = {"checked": 0, "updated": 0, "skipped": 0, "failed": 0}
    for document in cursor:
        stats["checked"] += 1
        path = resolve_upload_path(uploads_dir, document)
        if path is None or not path.exists() or not extractor_manager.is_supported(str(path)):
            stats["skipped"] += 1
            continue

        try:
            content, page = extract_content(path)
        except Exception:
            stats["failed"] += 1
            continue

        if not content:
            stats["skipped"] += 1
            continue

        update_data = {"content": content, "update_at": datetime.now()}
        if not document.get("page"):
            update_data["page"] = page
        database.documents.update_one({"_id": document["_id"]}, {"$set": update_data})
        stats["updated"] += 1

    return stats


def main() -> int:
    args = parse_args()
    uploads_dir = Path(args.uploads_dir).resolve()
    if not uploads_dir.exists():
        print(f"uploads 目录不存在: {uploads_dir}")
        return 1

    client = MongoClient(MONGODB_URL)
    try:
        database = client[MONGODB_DATABASE]
        database.command("ping")
        stats = backfill_documents(database, uploads_dir, args.limit)
    finally:
        client.close()

    print(f"检查文档: {stats['checked']}")
    print(f"补齐正文: {stats['updated']}")
    print(f"跳过文档: {stats['skipped']}")
    print(f"解析失败: {stats['failed']}")
    return 0 if stats["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
