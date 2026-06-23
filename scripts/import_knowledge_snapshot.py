from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from pymongo import MongoClient
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from pkg.constants.constants import QDRANT_COLLECTION_NAME, QDRANT_HOST, QDRANT_PORT, MONGODB_DATABASE, MONGODB_URL
except ModuleNotFoundError:
    QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
    QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
    QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "documents")
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://127.0.0.1:27017/")
    MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "rag_platform")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import knowledge data snapshot.")
    parser.add_argument("snapshot")
    parser.add_argument("--recreate-qdrant", action="store_true")
    parser.add_argument("--reset-mongo", action="store_true")
    return parser.parse_args()


def read_snapshot(path: Path) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    mongo_rows: dict[str, list[dict[str, Any]]] = {}
    vector_rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if not line.strip():
                continue
            item = json.loads(line)
            if item["type"] == "mongo":
                mongo_rows.setdefault(item["collection"], []).append(item["document"])
            elif item["type"] == "qdrant":
                vector_rows.append(item["row"])
    return mongo_rows, vector_rows


def import_mongo(database: Any, rows: dict[str, list[dict[str, Any]]], reset: bool) -> None:
    for collection_name, documents in rows.items():
        if reset:
            database[collection_name].delete_many({})
        if documents:
            for document in documents:
                document.pop("_id", None)
            database[collection_name].insert_many(documents)


def import_qdrant(rows: list[dict[str, Any]], recreate: bool) -> None:
    client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    if recreate:
        client.recreate_collection(
            collection_name=QDRANT_COLLECTION_NAME,
            vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
        )
    else:
        collections = {item.name for item in client.get_collections().collections}
        if QDRANT_COLLECTION_NAME not in collections:
            client.create_collection(
                collection_name=QDRANT_COLLECTION_NAME,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE),
            )
    points = []
    for index, row in enumerate(rows):
        point_id = row.get("id") or index + 1
        points.append(
            PointStruct(
                id=point_id,
                vector=row["embedding"],
                payload={
                    "text": row.get("text", ""),
                    "metadata": row.get("metadata", {}),
                },
            )
        )
    batch_size = 100
    for index in range(0, len(points), batch_size):
        client.upsert(
            collection_name=QDRANT_COLLECTION_NAME,
            points=points[index : index + batch_size],
        )


def main() -> int:
    args = parse_args()
    snapshot = Path(args.snapshot).resolve()
    if not snapshot.exists():
        print(f"文件不存在: {snapshot}")
        return 1

    mongo_rows, vector_rows = read_snapshot(snapshot)
    client = MongoClient(MONGODB_URL)
    database = client[MONGODB_DATABASE]
    database.command("ping")

    import_mongo(database, mongo_rows, args.reset_mongo)
    import_qdrant(vector_rows, args.recreate_qdrant)

    print(f"MongoDB 集合: {', '.join(sorted(mongo_rows.keys()))}")
    print(f"Qdrant 向量: {len(vector_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
