"""
Create interview-ready demo data for the RAG platform.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from pymongo import MongoClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pkg.constants.constants import MONGODB_DATABASE, MONGODB_URL
from pkg.utils.password_utils import hash_password


UPLOADS_DIR = PROJECT_ROOT / "uploads"
MONITOR_DIR = PROJECT_ROOT / "json_monitor"
LOG_DIR = PROJECT_ROOT / "json_log"

ADMIN_ID = "demo-admin-001"
USER_ID = "demo-user-001"


def utc_now() -> datetime:
    return datetime.now()


def iso(dt: datetime) -> str:
    return dt.isoformat()


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_users(now: datetime) -> list[dict[str, Any]]:
    password = hash_password("Demo@123456")
    return [
        {
            "uuid": ADMIN_ID,
            "nickname": "演示管理员",
            "email": "admin@rag-demo.local",
            "avatar": "https://cube.elemecdn.com/0/88/03b0d39583f48206768a7534e55bcpng.png",
            "gender": 0,
            "password": password,
            "birthday": "1998-05-12",
            "created_at": now - timedelta(days=42),
            "deleted_at": None,
            "is_admin": 1,
            "status": 0,
        },
        {
            "uuid": USER_ID,
            "nickname": "业务咨询用户",
            "email": "user@rag-demo.local",
            "avatar": "https://cube.elemecdn.com/e/fd/0fc7d20532fdaf769a25683617711png.png",
            "gender": 1,
            "password": password,
            "birthday": "2000-11-03",
            "created_at": now - timedelta(days=28),
            "deleted_at": None,
            "is_admin": 0,
            "status": 0,
        },
        {
            "uuid": "demo-user-002",
            "nickname": "知识库维护员",
            "email": "editor@rag-demo.local",
            "avatar": "https://cube.elemecdn.com/3/7c/3ea6beec64369c2642b92c6726f1epng.png",
            "gender": 0,
            "password": password,
            "birthday": "1997-08-24",
            "created_at": now - timedelta(days=19),
            "deleted_at": None,
            "is_admin": 1,
            "status": 0,
        },
        {
            "uuid": "demo-user-003",
            "nickname": "一线客服",
            "email": "support@rag-demo.local",
            "avatar": "https://cube.elemecdn.com/8/51/4592123592dbc6a99d6b303281067png.png",
            "gender": 1,
            "password": password,
            "birthday": "2001-02-16",
            "created_at": now - timedelta(days=12),
            "deleted_at": None,
            "is_admin": 0,
            "status": 0,
        },
    ]


def build_documents(now: datetime) -> list[dict[str, Any]]:
    docs = [
        (
            "doc-medical-guide-001",
            "企业智能问答平台建设方案.md",
            "本文档说明企业内部知识问答平台的建设背景、权限模型、检索流程、响应质量评估与持续运营方式。平台通过文档解析、文本分块、向量检索、重排序和答案评估，把分散知识转化为可追溯的问答服务。",
            8,
            172_032,
            0,
            "演示管理员",
        ),
        (
            "doc-rag-policy-002",
            "RAG 知识库运营规范.pdf",
            "知识库运营规范覆盖文档上传、权限分级、数据审核、问答缓存复核、错误回答回收和版本更新流程。管理员可以查看处理状态、文本分块数量和问答缓存命中情况。",
            15,
            1_248_512,
            1,
            "知识库维护员",
        ),
        (
            "doc-support-faq-003",
            "客服常见问题与标准话术.docx",
            "本文档沉淀售前咨询、售后服务、账号问题、文档上传失败、系统响应慢等高频问题，并给出标准回答口径。普通用户可以在聊天页上传文件并让 AI 结合知识库回答。",
            22,
            884_736,
            0,
            "知识库维护员",
        ),
        (
            "doc-benchmark-004",
            "RAG 评估样例集.xlsx",
            "样例集包含标准问题、标准答案、期望命中文档、难度等级和业务分类。平台可以基于这些样例观察回答忠实度、上下文召回率和答案相关度。",
            4,
            96_256,
            1,
            "演示管理员",
        ),
    ]

    result = []
    for index, (doc_id, name, content, page, size, permission, uploader) in enumerate(docs):
        created = now - timedelta(days=9 - index * 2, hours=index)
        upload_name = f"{doc_id}{Path(name).suffix or '.txt'}"
        file_path = UPLOADS_DIR / upload_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content + "\n\n" + "这是用于系统演示的知识库文档内容。\n", encoding="utf-8")
        result.append(
            {
                "uuid": doc_id,
                "name": name,
                "content": content,
                "page": page,
                "url": f"/uploads/{upload_name}",
                "size": size,
                "status": 2,
                "permission": permission,
                "extra_data": {
                    "uploader_id": ADMIN_ID if uploader == "演示管理员" else "demo-user-002",
                    "uploader_name": uploader,
                    "upload_time": iso(created),
                    "file_extension": Path(name).suffix or ".txt",
                    "source": "demo_seed",
                    "processing_result": "已解析文本并完成知识库入库",
                },
                "create_at": created,
                "update_at": created + timedelta(minutes=8 + index),
            }
        )
    return result


def build_chunks(documents: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    rows = []
    vector_id = 10_000
    for doc in documents:
        for index in range(1, 4):
            chunk_id = f"{doc['uuid']}-chunk-{index}"
            rows.append(
                {
                    "uuid": chunk_id,
                    "document_uuid": doc["uuid"],
                    "parent_chunk_uuid": None,
                    "content": f"{doc['name']} 第 {index} 个知识片段：{doc['content']}",
                    "full_content": doc["content"],
                    "index": index,
                    "page_number": index,
                    "vector_id": vector_id,
                    "embedding_model": "bge-large-zh-v1.5",
                    "metadata": {
                        "document_name": doc["name"],
                        "permission": doc["permission"],
                        "chunk_strategy": "small-to-big",
                    },
                    "create_at": now - timedelta(days=5, minutes=index),
                    "update_at": now - timedelta(days=5, minutes=index - 1),
                }
            )
            vector_id += 1
    return rows


def build_sessions_and_messages(now: datetime) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    sessions = [
        {
            "uuid": "session-demo-001",
            "user_id": ADMIN_ID,
            "name": "平台建设方案问答",
            "last_message": "可以，系统会根据权限过滤管理员文档，并返回引用来源。",
            "create_at": now - timedelta(days=3, hours=2),
            "update_at": now - timedelta(hours=3, minutes=18),
        },
        {
            "uuid": "session-demo-002",
            "user_id": ADMIN_ID,
            "name": "知识库运营流程",
            "last_message": "运营闭环包含上传、解析、检索、缓存、人工复核和监控巡检。",
            "create_at": now - timedelta(days=2, hours=5),
            "update_at": now - timedelta(hours=8, minutes=4),
        },
        {
            "uuid": "session-demo-003",
            "user_id": USER_ID,
            "name": "普通用户咨询",
            "last_message": "普通用户可以访问公开文档，管理员文档不会进入回答上下文。",
            "create_at": now - timedelta(days=1, hours=1),
            "update_at": now - timedelta(hours=1, minutes=12),
        },
    ]

    messages = []
    thoughts = []

    conversations = [
        (
            "session-demo-001",
            ADMIN_ID,
            "演示管理员",
            "这个平台如何把企业文档变成可追溯问答？",
            "平台先解析上传文档，再按语义分块生成向量。用户提问时，系统会检索相关片段，结合权限过滤和重排序结果生成答案，并在回复中展示引用文档，方便回看来源。",
            ["doc-medical-guide-001", "doc-rag-policy-002"],
            6,
            1,
        ),
        (
            "session-demo-001",
            ADMIN_ID,
            "演示管理员",
            "管理员文档会不会被普通用户看到？",
            "不会。文档记录带有权限级别，检索阶段会按用户角色过滤。普通用户只能命中公开文档，管理员登录后才能检索管理员文档。",
            ["doc-rag-policy-002"],
            4,
            0,
        ),
        (
            "session-demo-002",
            ADMIN_ID,
            "演示管理员",
            "问答缓存有什么价值？",
            "问答缓存会沉淀高质量回答。相似问题再次出现时，平台可以复用经过评估和反馈的答案，缩短响应时间，也让管理员能集中复核高频问题。",
            ["doc-benchmark-004", "doc-support-faq-003"],
            11,
            1,
        ),
        (
            "session-demo-003",
            USER_ID,
            "业务咨询用户",
            "上传文档后为什么有处理状态？",
            "文档上传后需要完成保存、文本解析、分块、向量化和入库。处理状态可以让用户知道文档是否已经可以参与问答。",
            ["doc-support-faq-003"],
            3,
            0,
        ),
    ]

    for index, (session_id, user_id, user_name, question, answer, doc_ids, likes, dislikes) in enumerate(conversations):
        question_time = now - timedelta(hours=12 - index * 2, minutes=17)
        user_msg_id = f"msg-user-{index + 1:03d}"
        ai_msg_id = f"msg-ai-{index + 1:03d}"
        chain_id = f"thought-chain-{index + 1:03d}"
        refs = [{"uuid": doc_id, "name": doc_name(doc_id)} for doc_id in doc_ids]
        messages.append(
            {
                "uuid": user_msg_id,
                "session_id": session_id,
                "content": question,
                "extra_data": None,
                "send_id": user_id,
                "send_name": user_name,
                "send_avatar": "",
                "send_type": 0,
                "receive_id": "assistant",
                "file_type": None,
                "file_name": None,
                "file_size": None,
                "status": 1,
                "created_at": question_time,
                "send_at": question_time,
            }
        )
        messages.append(
            {
                "uuid": ai_msg_id,
                "session_id": session_id,
                "content": answer,
                "extra_data": {
                    "thoughts": ["识别问题意图", "检索知识库并过滤权限", "组织带来源的回答"],
                    "actions": ["knowledge_search"],
                    "observations": [f"命中 {len(doc_ids)} 份相关文档"],
                    "documents": refs,
                    "thought_chain_id": chain_id,
                    "like_count": likes,
                    "dislike_count": dislikes,
                },
                "send_id": "assistant",
                "send_name": "AI 助手",
                "send_avatar": "",
                "send_type": 1,
                "receive_id": user_id,
                "file_type": None,
                "file_name": None,
                "file_size": None,
                "status": 1,
                "created_at": question_time + timedelta(seconds=14),
                "send_at": question_time + timedelta(seconds=14),
            }
        )
        thoughts.append(
            {
                "uuid": chain_id,
                "session_id": session_id,
                "message_id": ai_msg_id,
                "question": question,
                "answer": answer,
                "thought_chain": [
                    {"step": 1, "type": "thought", "content": "判断用户问题属于知识库问答。"},
                    {"step": 2, "type": "action", "content": "调用知识库检索工具并应用权限过滤。"},
                    {"step": 3, "type": "observation", "content": f"返回 {len(refs)} 个引用文档。"},
                    {"step": 4, "type": "answer", "content": answer},
                ],
                "documents_used": refs,
                "user_id": user_id,
                "model_name": "deepseek-chat",
                "total_steps": 4,
                "like_count": likes,
                "dislike_count": dislikes,
                "is_cached": True,
                "milvus_id": 20_000 + index,
                "user_feedbacks": {ADMIN_ID: "like"} if likes else {},
                "created_at": question_time + timedelta(seconds=16),
            }
        )
    return sessions, messages, thoughts


def doc_name(doc_id: str) -> str:
    mapping = {
        "doc-medical-guide-001": "企业智能问答平台建设方案.md",
        "doc-rag-policy-002": "RAG 知识库运营规范.pdf",
        "doc-support-faq-003": "客服常见问题与标准话术.docx",
        "doc-benchmark-004": "RAG 评估样例集.xlsx",
    }
    return mapping[doc_id]


def build_qa_caches(thoughts: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "uuid": f"qa-cache-{index + 1:03d}",
            "question": item["question"],
            "answer": item["answer"],
            "is_ai_verified": True,
            "ai_evaluation_score": 0.88 + index * 0.02,
            "is_human_verified": index % 2 == 0,
            "human_auditor_id": ADMIN_ID if index % 2 == 0 else None,
            "hit_count": 18 - index * 3,
            "like_count": item["like_count"],
            "dislike_count": item["dislike_count"],
            "source_doc_uuids": [doc["uuid"] for doc in item["documents_used"]],
            "is_active": True,
            "category": "平台能力",
            "metadata": {
                "thought_chain_id": item["uuid"],
                "answer_preview": item["answer"][:120],
                "created_at": iso(item["created_at"]),
            },
            "create_at": item["created_at"],
            "update_at": now - timedelta(minutes=index * 9),
        }
        for index, item in enumerate(thoughts)
    ]


def build_evaluations(thoughts: list[dict[str, Any]], now: datetime) -> list[dict[str, Any]]:
    rows = []
    for index, item in enumerate(thoughts):
        rows.append(
            {
                "target_id": item["message_id"],
                "target_type": "message",
                "faithfulness": round(0.89 + index * 0.01, 2),
                "answer_relevance": round(0.91 + index * 0.01, 2),
                "context_precision": round(0.86 + index * 0.02, 2),
                "context_recall": round(0.84 + index * 0.015, 2),
                "overall_score": round(0.88 + index * 0.015, 2),
                "evaluator": "llm",
                "comment": "回答紧扣检索内容，引用文档与问题匹配。",
                "dataset_type": "production",
                "created_at": now - timedelta(hours=5, minutes=index * 6),
            }
        )
    return rows


def build_benchmarks(now: datetime) -> list[dict[str, Any]]:
    return [
        {
            "question": "普通用户是否可以检索管理员文档？",
            "ground_truth": "不可以。检索阶段会根据用户角色过滤文档权限。",
            "expected_doc_uuids": ["doc-rag-policy-002"],
            "category": "权限控制",
            "difficulty": 2,
            "is_active": True,
            "created_at": now - timedelta(days=4),
            "update_at": now - timedelta(days=1),
        },
        {
            "question": "文档上传后为什么需要处理状态？",
            "ground_truth": "上传后还需要解析、分块、向量化和入库，状态用于显示文档是否已可用于问答。",
            "expected_doc_uuids": ["doc-support-faq-003"],
            "category": "文档管理",
            "difficulty": 1,
            "is_active": True,
            "created_at": now - timedelta(days=4),
            "update_at": now - timedelta(days=1),
        },
        {
            "question": "问答缓存如何提升体验？",
            "ground_truth": "缓存可复用高质量回答，减少重复问题响应时间，并支持管理员复核。",
            "expected_doc_uuids": ["doc-benchmark-004"],
            "category": "质量评估",
            "difficulty": 3,
            "is_active": True,
            "created_at": now - timedelta(days=4),
            "update_at": now - timedelta(days=1),
        },
    ]


def seed_monitor_and_logs(now: datetime) -> None:
    date_dir = now.strftime("%y_%m_%d_monitor")
    monitor_path = MONITOR_DIR / date_dir

    resource_rows = []
    for i in range(12):
        ts = now - timedelta(minutes=(11 - i) * 5)
        resource_rows.append(
            {
                "timestamp": iso(ts),
                "system": {
                    "cpu_percent": 28.5 + i * 1.7,
                    "memory_percent": 52.4 + i * 0.8,
                    "disk_percent": 41.2,
                    "disk_total_gb": 460.0,
                    "gpu": {"utilization": 0},
                },
                "mongodb": {
                    "status": "healthy",
                    "connections_current": 12 + i,
                    "connections_available": 838_848,
                    "db_collections": 9,
                    "db_documents": 51,
                    "db_size_mb": 18.73,
                    "opcounters_query": 240 + i * 7,
                },
                "milvus": {
                    "status": "healthy",
                    "collections": 2,
                    "collection_name": "documents",
                    "total_entities": 12,
                    "total_rows": 12,
                    "num_segments": 3,
                },
                "app_stats": {
                    "active_sessions": 3,
                    "daily_questions": 42 + i,
                    "cache_hit_rate": 37.5,
                },
            }
        )
    write_jsonl(monitor_path / "resource.json", resource_rows)

    perf_specs = {
        "embedding": ("批量向量化", 126.4),
        "milvus_search": ("知识库召回", 42.7),
        "llm_think": ("意图分析", 310.8),
        "llm_action": ("工具调用", 188.2),
        "llm_answer": ("答案生成", 1380.5),
        "llm_total": ("完整回复", 2140.3),
        "agent_total": ("Agent 推理", 2388.6),
    }
    for name, (operation, base_ms) in perf_specs.items():
        rows = []
        for i in range(10):
            duration = base_ms + i * 11.3
            rows.append(
                {
                    "timestamp": iso(now - timedelta(minutes=(9 - i) * 6)),
                    "operation": operation,
                    "duration_ms": round(duration, 2),
                    "duration_s": round(duration / 1000, 4),
                    "metadata": {
                        "model": "deepseek-chat" if name.startswith("llm") or name == "agent_total" else "bge-large-zh-v1.5",
                        "sample": i + 1,
                        "source": "demo_seed",
                    },
                }
            )
        write_jsonl(monitor_path / f"{name}.json", rows)

    log_path = LOG_DIR / now.strftime("%y_%m_%d_log") / "error.json"
    log_rows = [
        {
            "timestamp": iso(now - timedelta(hours=2, minutes=13)),
            "level": "ERROR",
            "text": "文档处理队列曾出现短暂重试，已自动恢复。",
            "record": {
                "level": {"name": "ERROR"},
                "time": {"repr": iso(now - timedelta(hours=2, minutes=13))},
                "message": "文档处理队列曾出现短暂重试，已自动恢复。",
                "file": {"path": "internal/document_client/document_processor.py", "name": "document_processor.py"},
                "line": 218,
                "function": "process_task",
                "module": "document_processor",
                "exception": None,
            },
        },
        {
            "timestamp": iso(now - timedelta(hours=1, minutes=7)),
            "level": "WARNING",
            "text": "相似问答缓存命中率低于阈值，建议管理员复核高频问题。",
            "record": {
                "level": {"name": "WARNING"},
                "time": {"repr": iso(now - timedelta(hours=1, minutes=7))},
                "message": "相似问答缓存命中率低于阈值，建议管理员复核高频问题。",
                "file": {"path": "internal/service/ai/similar_qa_cache.py", "name": "similar_qa_cache.py"},
                "line": 126,
                "function": "search_similar",
                "module": "similar_qa_cache",
                "exception": None,
            },
        },
    ]
    write_jsonl(log_path, log_rows)


def seed_mongodb(reset: bool) -> None:
    now = utc_now()
    client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    database = client[MONGODB_DATABASE]

    if reset:
        client.drop_database(MONGODB_DATABASE)
        database = client[MONGODB_DATABASE]

    users = build_users(now)
    documents = build_documents(now)
    chunks = build_chunks(documents, now)
    sessions, messages, thoughts = build_sessions_and_messages(now)
    qa_caches = build_qa_caches(thoughts, now)
    evaluations = build_evaluations(thoughts, now)
    benchmarks = build_benchmarks(now)

    collections = {
        "user_info": users,
        "documents": documents,
        "chunks": chunks,
        "session": sessions,
        "message": messages,
        "thought_chains": thoughts,
        "qa_caches": qa_caches,
        "evaluations": evaluations,
        "benchmarks": benchmarks,
    }

    for name, rows in collections.items():
        database[name].delete_many({})
        if rows:
            database[name].insert_many(rows)

    database.user_info.create_index("uuid")
    database.documents.create_index("uuid")
    database.session.create_index("uuid", unique=True)
    database.message.create_index("session_id")
    database.thought_chains.create_index("uuid")
    database.qa_caches.create_index("uuid")
    database.chunks.create_index("document_uuid")

    seed_monitor_and_logs(now)
    client.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed demo data for the RAG platform.")
    parser.add_argument("--reset", action="store_true", help="Drop and rebuild the configured MongoDB database.")
    args = parser.parse_args()

    seed_mongodb(reset=args.reset)
    print("演示数据已导入")
    print("登录账号：演示管理员 / Demo@123456")
    print("普通账号：业务咨询用户 / Demo@123456")


if __name__ == "__main__":
    os.chdir(PROJECT_ROOT)
    main()
