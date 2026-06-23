from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from internal.db.qdrant import qdrant_client
from pkg.constants.constants import QDRANT_COLLECTION_NAME, MONGODB_DATABASE, MONGODB_URL


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export knowledge data snapshot.")
    parser.add_argument("--output", default=str(PROJECT_ROOT / "exports" / "knowledge_snapshot.jsonl"))
    return parser.parse_args()


def clean_value(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: clean_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_value(item) for item in value]
    return value


def export_mongo(database: Any, output_file: Any) -> None:
    for collection_name in ["user_info", "documents"]:
        for document in database[collection_name].find({}):
            output_file.write(
                json.dumps(
                    {
                        "type": "mongo",
                        "collection": collection_name,
                        "document": clean_value(document),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def export_qdrant(output_file: Any) -> None:
    rows = qdrant_client.scroll_all(
        collection_name=QDRANT_COLLECTION_NAME,
        limit=16384,
        with_vectors=True,
    )
    for row in rows:
        payload = row.payload or {}
        output_file.write(
            json.dumps(
                {
                    "type": "qdrant",
                    "collection": QDRANT_COLLECTION_NAME,
                    "row": {
                        "id": str(row.id),
                        "embedding": row.vector,
                        "text": payload.get("text", ""),
                        "metadata": payload.get("metadata", {}),
                    },
                },
                ensure_ascii=False,
            )
            + "\n"
        )


def main() -> int:
    args = parse_args()
    output_path = Path(args.output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    client = MongoClient(MONGODB_URL)
    database = client[MONGODB_DATABASE]
    database.command("ping")

    with output_path.open("w", encoding="utf-8") as output_file:
        export_mongo(database, output_file)
        export_qdrant(output_file)

    print(f"已导出: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
