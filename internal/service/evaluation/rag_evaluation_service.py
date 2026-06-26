"""RAG 检索评估服务。"""
from __future__ import annotations

import asyncio
from datetime import datetime
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple
import json
import os
import random
import re


EVALUATION_TYPES = ("rag", "normal_reply", "long_context", "tool_call", "multi_agent")
EVALUATION_TYPE_LABELS = {
    "rag": "RAG 评估",
    "normal_reply": "正常回复评估",
    "long_context": "长上下文评估",
    "tool_call": "工具调用评估",
    "multi_agent": "多 Agent 评估",
}
LLM_SCORE_WEIGHT = 0.8
RULE_SCORE_WEIGHT = 0.2
RERANK_SCORE_CENTER = 0.0
RERANK_SCORE_SCALE = 2.0


class RAGASEvaluator:
    """RAGAS 指标执行器。"""

    def __init__(self, llm: Any = None, embeddings: Any = None):
        self.llm = llm
        self.embeddings = embeddings

    async def evaluate_production(self, question: str, answer: str, contexts: Sequence[str]) -> Dict[str, Optional[float]]:
        if not contexts:
            return {
                "faithfulness": 0.0,
                "answer_relevance": 0.0,
                "context_precision": 0.0,
            }
        return await asyncio.to_thread(self._evaluate_production_sync, question, answer, contexts)

    def _evaluate_production_sync(self, question: str, answer: str, contexts: Sequence[str]) -> Dict[str, Optional[float]]:
        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.metrics import context_precision, faithfulness
            try:
                from ragas.metrics import answer_relevancy
            except ImportError:
                from ragas.metrics import answer_relevance as answer_relevancy
        except ImportError as exc:
            raise RuntimeError("评估依赖未安装，请先安装 ragas 和 datasets。") from exc

        data = {
            "question": [question],
            "answer": [answer],
            "contexts": [list(contexts)],
            "ground_truth": [answer],
        }
        try:
            result = evaluate(
                Dataset.from_dict(data),
                metrics=[faithfulness, answer_relevancy, context_precision],
                llm=self._get_llm(),
                embeddings=self._get_embeddings(),
                raise_exceptions=False,
                show_progress=False,
            )
        except TypeError:
            result = evaluate(
                Dataset.from_dict(data),
                metrics=[faithfulness, answer_relevancy, context_precision],
                llm=self._get_llm(),
                embeddings=self._get_embeddings(),
            )

        row = result.to_pandas().iloc[0]
        return {
            "faithfulness": _clean_score(row.get("faithfulness")) or 0.0,
            "answer_relevance": _clean_score(row.get("answer_relevancy")) or _clean_score(row.get("answer_relevance")) or 0.0,
            "context_precision": _clean_score(row.get("context_precision")) or 0.0,
        }

    async def evaluate(self, rows: Sequence[Dict[str, Any]], include_faithfulness: bool = False) -> List[Dict[str, Optional[float]]]:
        if not rows:
            return []

        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.metrics import context_precision, context_recall, faithfulness
        except ImportError as exc:
            raise RuntimeError("评估依赖未安装，请先安装 ragas 和 datasets。") from exc

        data = {
            "question": [row["question"] for row in rows],
            "contexts": [row["contexts"] for row in rows],
            "ground_truth": [row["ground_truth"] for row in rows],
        }
        metrics = [context_recall, context_precision]

        if include_faithfulness:
            data["answer"] = [row.get("answer") or row["ground_truth"] for row in rows]
            metrics.append(faithfulness)

        try:
            result = evaluate(Dataset.from_dict(data), metrics=metrics, raise_exceptions=False, show_progress=False)
        except TypeError:
            result = evaluate(Dataset.from_dict(data), metrics=metrics)
        frame = result.to_pandas()

        scores: List[Dict[str, Optional[float]]] = []
        for _, row in frame.iterrows():
            scores.append({
                "context_recall": _clean_score(row.get("context_recall")),
                "context_precision": _clean_score(row.get("context_precision")),
                "faithfulness": _clean_score(row.get("faithfulness")) if include_faithfulness else None,
            })
        return scores

    def _get_llm(self) -> Any:
        if self.llm is not None:
            return self.llm
        try:
            from pkg.constants.constants import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
            if not DEEPSEEK_API_KEY:
                raise RuntimeError("RAGAS 评估模型未配置")
            from langchain_openai import ChatOpenAI
            self.llm = ChatOpenAI(
                model=os.getenv("RAGAS_LLM_MODEL", "deepseek-chat"),
                openai_api_key=DEEPSEEK_API_KEY,
                openai_api_base=DEEPSEEK_BASE_URL,
                temperature=0,
                request_timeout=60,
            )
            return self.llm
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("RAGAS 评估模型初始化失败") from exc

    def _get_embeddings(self) -> Any:
        if self.embeddings is not None:
            return self.embeddings
        try:
            from ragas.embeddings import LangchainEmbeddingsWrapper
            self.embeddings = LangchainEmbeddingsWrapper(_ProjectEmbeddings())
            return self.embeddings
        except Exception as exc:
            raise RuntimeError("RAGAS 向量模型初始化失败") from exc


class LLMQualityEvaluator:
    """使用模型给回答质量打分。"""

    async def evaluate(
        self,
        question: str,
        answer: str,
        contexts: Sequence[str],
        evaluation_type: str = "rag",
    ) -> Dict[str, Any]:
        return await asyncio.to_thread(self._evaluate_sync, question, answer, contexts, evaluation_type)

    def _evaluate_sync(
        self,
        question: str,
        answer: str,
        contexts: Sequence[str],
        evaluation_type: str,
    ) -> Dict[str, Any]:
        try:
            from langchain_core.messages import HumanMessage, SystemMessage
            from pkg.constants.constants import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL
            if not DEEPSEEK_API_KEY:
                raise RuntimeError("评估模型未配置")
            from langchain_openai import ChatOpenAI
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError("评估模型初始化失败") from exc

        llm = ChatOpenAI(
            model=os.getenv("EVALUATION_LLM_MODEL", os.getenv("RAGAS_LLM_MODEL", "deepseek-chat")),
            openai_api_key=DEEPSEEK_API_KEY,
            openai_api_base=DEEPSEEK_BASE_URL,
            temperature=0,
            request_timeout=60,
        )
        context_text = "\n\n".join([text for text in contexts if text])[:8000]
        messages = [
            SystemMessage(content=(
                "你负责评估 AI 回答质量。请只返回 JSON，字段为 score 和 reason。"
                "score 必须是 0 到 1 的数字，1 表示质量最高。"
                "reason 用中文说明评分原因，不要提及接口、代码、调试或系统实现。"
            )),
            HumanMessage(content=(
                f"评估类型：{EVALUATION_TYPE_LABELS.get(evaluation_type, evaluation_type)}\n"
                f"用户问题：{question}\n"
                f"AI 回答：{answer}\n"
                f"参考内容：{context_text or '无'}"
            )),
        ]
        response = llm.invoke(messages)
        content = getattr(response, "content", str(response))
        return _parse_llm_quality_result(content)


class RAGEvaluationService:
    """批量评估当前 RAG 检索结果。"""

    def __init__(
        self,
        rag_service: Any = None,
        benchmark_model: Any = None,
        evaluation_model: Any = None,
        config_model: Any = None,
        queue_producer: Any = None,
        ragas_evaluator: Optional[RAGASEvaluator] = None,
        llm_quality_evaluator: Optional[LLMQualityEvaluator] = None,
        context_recall_threshold: float = 0.75,
        context_precision_threshold: float = 0.60,
    ):
        if rag_service is None:
            from internal.rag.rag_service import rag_service as default_rag_service
            rag_service = default_rag_service
        if benchmark_model is None:
            from internal.model.benchmark import BenchmarkModel
            benchmark_model = BenchmarkModel
        if evaluation_model is None:
            from internal.model.evaluation import EvaluationModel
            evaluation_model = EvaluationModel
        if config_model is None:
            from internal.model.evaluation_config import EvaluationConfigModel
            config_model = EvaluationConfigModel
        if queue_producer is None:
            from internal.service.evaluation.rag_evaluation_queue import queue_producer as default_queue_producer
            queue_producer = default_queue_producer

        self.rag_service = rag_service
        self.benchmark_model = benchmark_model
        self.evaluation_model = evaluation_model
        self.config_model = config_model
        self.queue_producer = queue_producer
        self.ragas_evaluator = ragas_evaluator or RAGASEvaluator()
        self.llm_quality_evaluator = llm_quality_evaluator or LLMQualityEvaluator()
        self.context_recall_threshold = context_recall_threshold
        self.context_precision_threshold = context_precision_threshold
        self._config = {
            "ragas_enabled": True,
            "ragas_queue_enabled": True,
            "ragas_sample_rate": 1.0,
            "ragas_max_chunks_per_question": 3,
            "ragas_min_retrieval_score": 0.05,
        }

    def update_config(self, values: Dict[str, Any]) -> Dict[str, Any]:
        self._config.update({key: value for key, value in values.items() if key in self._config})
        return dict(self._config)

    async def get_config(self) -> Dict[str, Any]:
        try:
            config = await self.config_model.find_one(self.config_model.key == "ragas")
            if config:
                return {
                    "ragas_enabled": config.ragas_enabled,
                    "ragas_queue_enabled": config.ragas_queue_enabled,
                    "ragas_sample_rate": config.ragas_sample_rate,
                    "ragas_max_chunks_per_question": config.ragas_max_chunks_per_question,
                    "ragas_min_retrieval_score": config.ragas_min_retrieval_score,
                }
        except Exception:
            pass
        return dict(self._config)

    async def save_config(self, values: Dict[str, Any]) -> Dict[str, Any]:
        config_values = self.update_config(values)
        try:
            config = await self.config_model.find_one(self.config_model.key == "ragas")
            if not config:
                config = self.config_model(key="ragas")
            for key, value in config_values.items():
                setattr(config, key, value)
            config.updated_at = datetime.now()
            await config.save()
        except Exception:
            pass
        return config_values

    async def build_dataset(
        self,
        top_k: int = 5,
        use_reranker: bool = True,
        user_permission: int = 1,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        benchmarks = await self.benchmark_model.find(self.benchmark_model.is_active == True).to_list()  # noqa: E712

        rows: List[Dict[str, Any]] = []
        items: List[Dict[str, Any]] = []

        for benchmark in benchmarks:
            search_error = ""
            try:
                search_results = self.rag_service.search(
                    query=benchmark.question,
                    top_k=top_k,
                    use_reranker=use_reranker,
                    user_permission=user_permission,
                )
            except Exception:
                search_results = []
                search_error = "检索失败"
            contexts = [result.get("text", "") for result in search_results if result.get("text")]
            documents = [_format_document(result) for result in search_results]

            rows.append({
                "question": benchmark.question,
                "ground_truth": benchmark.ground_truth,
                "contexts": contexts,
            })
            items.append({
                "question": benchmark.question,
                "ground_truth": benchmark.ground_truth,
                "category": getattr(benchmark, "category", "general"),
                "difficulty": getattr(benchmark, "difficulty", 1),
                "retrieved_documents": documents,
                "error": search_error,
            })

        return rows, items

    async def run(
        self,
        top_k: int = 5,
        use_reranker: bool = True,
        user_permission: int = 1,
        include_faithfulness: bool = False,
        save_results: bool = True,
    ) -> Dict[str, Any]:
        rows, items = await self.build_dataset(
            top_k=top_k,
            use_reranker=use_reranker,
            user_permission=user_permission,
        )
        scores = await self.ragas_evaluator.evaluate(rows, include_faithfulness=include_faithfulness)

        report_items = []
        if len(scores) < len(items):
            scores = list(scores) + [
                {"context_recall": 0.0, "context_precision": 0.0, "faithfulness": None}
                for _ in range(len(items) - len(scores))
            ]

        for item, score in zip(items, scores):
            context_recall = score.get("context_recall") or 0.0
            context_precision = score.get("context_precision") or 0.0
            faithfulness_score = score.get("faithfulness")
            passed = (
                context_recall >= self.context_recall_threshold
                and context_precision >= self.context_precision_threshold
            )
            report_item = {
                **item,
                "context_recall": context_recall,
                "context_precision": context_precision,
                "faithfulness": faithfulness_score,
                "status": "passed" if passed else "failed",
                "reason": item.get("error") or ("评估通过" if passed else "检索结果未达到评估阈值"),
            }
            report_items.append(report_item)
            if save_results:
                await self._save_evaluation(report_item)

        return {
            "summary": _build_summary(report_items),
            "items": report_items,
        }

    async def save_rag_call_records(
        self,
        question: str,
        answer: str,
        session_id: str,
        user_id: str,
        message_id: str,
        rag_results: Sequence[Dict[str, Any]],
        tool_name: str = "knowledge_search",
        start_ragas: bool = True,
    ) -> List[Any]:
        records = []
        config = await self.get_config()
        eligible_count = 0
        for result in rag_results:
            text = result.get("text", "")
            if not text:
                continue

            document = _format_document(result)
            vector_score = float(result.get("vector_score", result.get("score", 0.0)) or 0.0)
            raw_rerank_score = result.get("rerank_score")
            rerank_score = float(raw_rerank_score or 0.0)
            rule_calibration = _calibrate_rule_score(
                rerank_score=rerank_score,
                vector_score=vector_score,
                has_rerank=raw_rerank_score is not None,
            )
            rule_score = rule_calibration["rule_score"]
            should_queue = start_ragas and self._should_queue(rule_score, eligible_count, config)
            if should_queue:
                eligible_count += 1
            queue_status = "queued" if should_queue else "skipped"
            now = datetime.now()
            record = self.evaluation_model(
                target_id=message_id,
                target_type="rag_chunk",
                question=question,
                answer=answer,
                session_id=session_id,
                user_id=user_id,
                message_id=message_id,
                tool_name=tool_name,
                document_uuid=document["document_uuid"],
                filename=document["filename"],
                chunk_index=document["chunk_index"],
                retrieved_text=text,
                vector_score=vector_score,
                rerank_score=rerank_score,
                evaluation_type="rag",
                llm_score=0.0,
                rule_score=rule_score,
                score_reason="",
                score_breakdown=_build_score_breakdown(0.0, rule_score, rule_calibration),
                faithfulness=0.0,
                answer_relevance=0.0,
                context_precision=0.0,
                context_recall=0.0,
                overall_score=rule_score,
                evaluator="ragas",
                comment="",
                dataset_type="production",
                ragas_status=queue_status,
                ragas_error="",
                queue_status=queue_status,
                queued_at=now if should_queue else None,
                started_at=None,
                completed_at=None,
                retry_count=0,
                created_at=now,
            )
            await record.insert()
            if should_queue:
                if not self.queue_producer.enqueue(record):
                    record.queue_status = "failed"
                    record.ragas_status = "failed"
                    record.ragas_error = "评估任务入队失败"
                    await record.save()
            records.append(record)

        return records

    def _should_queue(self, score: float, eligible_count: int, config: Dict[str, Any]) -> bool:
        if not config.get("ragas_enabled", True):
            return False
        if not config.get("ragas_queue_enabled", True):
            return False
        if score < float(config.get("ragas_min_retrieval_score", 0.0) or 0.0):
            return False
        if eligible_count >= int(config.get("ragas_max_chunks_per_question", 3) or 0):
            return False
        sample_rate = float(config.get("ragas_sample_rate", 1.0) or 0.0)
        if sample_rate <= 0:
            return False
        if sample_rate < 1.0 and random.random() > sample_rate:
            return False
        return True

    async def run_ragas_for_records(self, records: Sequence[Any]) -> None:
        for record in records:
            try:
                record.queue_status = "running"
                record.ragas_status = "running"
                record.started_at = datetime.now()
                await record.save()
                scores = await self.ragas_evaluator.evaluate_production(
                    question=record.question or "",
                    answer=record.answer or "",
                    contexts=[record.retrieved_text or ""],
                )
                record.faithfulness = scores.get("faithfulness") or 0.0
                record.answer_relevance = scores.get("answer_relevance") or 0.0
                record.context_precision = scores.get("context_precision") or 0.0
                record.context_recall = 0.0
                evaluation_type = _record_evaluation_type(record)
                rule_calibration = _record_rule_calibration(record)
                rule_score = rule_calibration["rule_score"]
                quality = await self.llm_quality_evaluator.evaluate(
                    question=record.question or "",
                    answer=record.answer or "",
                    contexts=[record.retrieved_text or ""],
                    evaluation_type=evaluation_type,
                )
                llm_score = _clamp_score(quality.get("score", 0.0))
                score_reason = str(quality.get("reason") or "").strip()
                record.evaluation_type = evaluation_type
                record.llm_score = llm_score
                record.rule_score = rule_score
                record.overall_score = _combine_scores(llm_score, rule_score)
                record.score_reason = score_reason
                record.score_breakdown = _build_score_breakdown(llm_score, rule_score, rule_calibration)
                record.comment = score_reason
                record.queue_status = "completed"
                record.ragas_status = "completed"
                record.ragas_error = ""
                record.completed_at = datetime.now()
            except Exception as exc:
                from log import logger
                logger.error(f"RAGAS 评估执行失败: {exc}", exc_info=True)
                record.evaluation_type = _record_evaluation_type(record)
                record.llm_score = getattr(record, "llm_score", 0.0) or 0.0
                rule_calibration = _record_rule_calibration(record)
                record.rule_score = rule_calibration["rule_score"]
                record.overall_score = getattr(record, "overall_score", record.rule_score) or record.rule_score
                record.score_reason = getattr(record, "score_reason", "") or ""
                record.score_breakdown = getattr(record, "score_breakdown", {}) or _build_score_breakdown(record.llm_score, record.rule_score, rule_calibration)
                record.queue_status = "failed"
                record.ragas_status = "failed"
                record.ragas_error = _format_ragas_error(exc)
                record.completed_at = datetime.now()
            await record.save()

    async def consume_queue_record(self, record: Any) -> None:
        await self.run_ragas_for_records([record])

    async def recover_pending_queue_records(self, limit: int = 100) -> int:
        records = await self.evaluation_model.find().to_list()
        pending = [
            record for record in records
            if getattr(record, "target_type", "") == "rag_chunk"
            and getattr(record, "queue_status", getattr(record, "ragas_status", "")) in {"queued", "running"}
        ][:limit]
        await self.run_ragas_for_records(pending)
        return len(pending)

    async def requeue_record(self, record: Any) -> bool:
        record.queue_status = "queued"
        record.ragas_status = "queued"
        record.ragas_error = ""
        record.retry_count = (getattr(record, "retry_count", 0) or 0) + 1
        record.queued_at = datetime.now()
        record.started_at = None
        record.completed_at = None
        await record.save()
        success = self.queue_producer.enqueue(record)
        if not success:
            record.queue_status = "failed"
            record.ragas_status = "failed"
            record.ragas_error = "评估任务入队失败"
            await record.save()
        return success

    async def get_rag_evaluation_list(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        ragas_status: Optional[str] = None,
        evaluation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        return await self.get_evaluation_management_list(
            page=page,
            page_size=page_size,
            keyword=keyword,
            ragas_status=ragas_status,
            evaluation_id=evaluation_id,
            evaluation_type="rag",
        )

    async def get_evaluation_management_list(
        self,
        page: int = 1,
        page_size: int = 20,
        keyword: Optional[str] = None,
        ragas_status: Optional[str] = None,
        evaluation_id: Optional[str] = None,
        evaluation_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        query = self.evaluation_model.find()
        try:
            query = query.sort("-created_at")
        except Exception:
            try:
                query = query.sort(self.evaluation_model.created_at)
            except Exception:
                pass
        records = await query.to_list()
        records = sorted(records, key=lambda item: getattr(item, "created_at", datetime.min), reverse=True)
        filtered = list(records)
        if evaluation_id:
            filtered = [
                record for record in filtered
                if str(getattr(record, "id", "") or "") == evaluation_id
            ]
        if evaluation_type:
            filtered = [
                record for record in filtered
                if _record_evaluation_type(record) == evaluation_type
            ]
        if keyword:
            filtered = [
                record for record in filtered
                if keyword in (getattr(record, "question", "") or "")
                or keyword in (getattr(record, "retrieved_text", "") or "")
                or keyword in (getattr(record, "filename", "") or "")
            ]
        if ragas_status:
            filtered = [
                record for record in filtered
                if getattr(record, "ragas_status", "") == ragas_status
                or getattr(record, "queue_status", "") == ragas_status
            ]

        total = len(filtered)
        start = (max(page, 1) - 1) * page_size
        end = start + page_size
        page_records = filtered[start:end]
        completed = [item for item in filtered if getattr(item, "ragas_status", "") == "completed"]
        queued = [item for item in filtered if getattr(item, "queue_status", getattr(item, "ragas_status", "")) == "queued"]
        running = [item for item in filtered if getattr(item, "queue_status", getattr(item, "ragas_status", "")) == "running"]
        skipped = [item for item in filtered if getattr(item, "queue_status", getattr(item, "ragas_status", "")) == "skipped"]
        failed = [item for item in filtered if getattr(item, "queue_status", getattr(item, "ragas_status", "")) == "failed"]
        type_counts = {
            item_type: sum(1 for record in records if _record_evaluation_type(record) == item_type)
            for item_type in EVALUATION_TYPES
        }

        return {
            "total": total,
            "items": [_serialize_rag_record(record) for record in page_records],
            "completed_count": len(completed),
            "pending_count": len(queued),
            "queued_count": len(queued),
            "running_count": len(running),
            "failed_count": len(failed),
            "skipped_count": len(skipped),
            "type_counts": type_counts,
            "avg_overall_score": _average([_record_overall_score(item) for item in filtered]),
            "avg_retrieval_score": _average([_record_rule_score(item) for item in filtered]),
            "avg_ragas_score": _average([
                (
                    (getattr(item, "faithfulness", 0.0) or 0.0)
                    + (getattr(item, "answer_relevance", 0.0) or 0.0)
                    + (getattr(item, "context_precision", 0.0) or 0.0)
                ) / 3
                for item in completed
            ]),
        }

    async def _save_evaluation(self, item: Dict[str, Any]) -> None:
        scores = [
            item["context_recall"],
            item["context_precision"],
        ]
        if item.get("faithfulness") is not None:
            scores.append(item["faithfulness"])
        overall_score = round(sum(scores) / len(scores), 4) if scores else 0.0

        evaluation = self.evaluation_model(
            target_id=item["question"],
            target_type="benchmark",
            faithfulness=item.get("faithfulness") or 0.0,
            answer_relevance=0.0,
            context_precision=item["context_precision"],
            context_recall=item["context_recall"],
            overall_score=overall_score,
            evaluation_type="rag",
            llm_score=0.0,
            rule_score=overall_score,
            score_reason=item["reason"],
            score_breakdown=_build_score_breakdown(0.0, overall_score),
            evaluator="ragas",
            comment=item["reason"],
            dataset_type="benchmark",
            created_at=datetime.now(),
        )
        await evaluation.insert()


def write_report(report: Dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _format_document(result: Dict[str, Any]) -> Dict[str, Any]:
    metadata = result.get("metadata") or {}
    score = result.get("rerank_score", result.get("vector_score", result.get("score", 0.0)))
    return {
        "document_uuid": metadata.get("document_uuid", ""),
        "filename": metadata.get("filename", "未知文档"),
        "chunk_index": metadata.get("chunk_index", 0),
        "score": float(score or 0.0),
        "text": result.get("text", ""),
    }


def _serialize_rag_record(record: Any) -> Dict[str, Any]:
    created_at = getattr(record, "created_at", None)
    evaluation_type = _record_evaluation_type(record)
    rule_calibration = _record_rule_calibration(record)
    rule_score = rule_calibration["rule_score"]
    llm_score = _clamp_score(getattr(record, "llm_score", 0.0) or 0.0)
    score_reason = getattr(record, "score_reason", None) or getattr(record, "comment", "") or ""
    return {
        "id": str(getattr(record, "id", "") or ""),
        "evaluation_type": evaluation_type,
        "evaluation_type_label": EVALUATION_TYPE_LABELS.get(evaluation_type, "评估"),
        "question": getattr(record, "question", "") or "",
        "answer": getattr(record, "answer", "") or "",
        "retrieved_text": getattr(record, "retrieved_text", "") or "",
        "filename": getattr(record, "filename", "") or "",
        "document_uuid": getattr(record, "document_uuid", "") or "",
        "chunk_index": getattr(record, "chunk_index", 0) or 0,
        "vector_score": getattr(record, "vector_score", 0.0) or 0.0,
        "rerank_score": getattr(record, "rerank_score", 0.0) or 0.0,
        "overall_score": _record_overall_score(record),
        "llm_score": llm_score,
        "rule_score": rule_score,
        "score_reason": score_reason,
        "score_breakdown": _record_score_breakdown(record, llm_score, rule_score, rule_calibration),
        "faithfulness": getattr(record, "faithfulness", 0.0) or 0.0,
        "answer_relevance": getattr(record, "answer_relevance", 0.0) or 0.0,
        "context_precision": getattr(record, "context_precision", 0.0) or 0.0,
        "context_recall": getattr(record, "context_recall", 0.0) or 0.0,
        "ragas_status": getattr(record, "ragas_status", "") or "",
        "ragas_error": getattr(record, "ragas_error", "") or "",
        "queue_status": getattr(record, "queue_status", "") or "",
        "queued_at": _format_datetime(getattr(record, "queued_at", None)),
        "started_at": _format_datetime(getattr(record, "started_at", None)),
        "completed_at": _format_datetime(getattr(record, "completed_at", None)),
        "retry_count": getattr(record, "retry_count", 0) or 0,
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else "",
    }


def _format_datetime(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else ""


def _record_evaluation_type(record: Any) -> str:
    value = getattr(record, "evaluation_type", "") or ""
    if value in EVALUATION_TYPES:
        return value
    if (
        getattr(record, "target_type", "") == "rag_chunk"
        or getattr(record, "retrieved_text", "")
        or getattr(record, "rerank_score", 0.0)
        or getattr(record, "vector_score", 0.0)
    ):
        return "rag"
    return "normal_reply"


def _record_rule_score(record: Any) -> float:
    return _record_rule_calibration(record)["rule_score"]


def _record_rule_calibration(record: Any) -> Dict[str, Any]:
    value = getattr(record, "rule_score", None)
    if value is not None:
        breakdown = getattr(record, "score_breakdown", {}) or {}
        return {
            "rule_score": _clamp_score(value),
            "rule_score_source": breakdown.get("rule_score_source", "stored"),
            "rule_score_raw": _safe_float(breakdown.get("rule_score_raw", value)),
            "rule_score_mapping": breakdown.get("rule_score_mapping", "stored"),
            "rule_score_center": _safe_float(breakdown.get("rule_score_center", RERANK_SCORE_CENTER)),
            "rule_score_scale": _safe_float(breakdown.get("rule_score_scale", RERANK_SCORE_SCALE)),
        }
    rerank_score = getattr(record, "rerank_score", 0.0) or 0.0
    vector_score = getattr(record, "vector_score", 0.0) or 0.0
    return _calibrate_rule_score(rerank_score=rerank_score, vector_score=vector_score)


def _record_overall_score(record: Any) -> float:
    llm_score = _clamp_score(getattr(record, "llm_score", 0.0) or 0.0)
    rule_score = _record_rule_score(record)
    if llm_score or getattr(record, "score_breakdown", None):
        return _combine_scores(llm_score, rule_score)
    stored_overall = _safe_float(getattr(record, "overall_score", 0.0))
    if stored_overall < 0:
        return rule_score
    return _clamp_score(stored_overall or rule_score)


def _calibrate_rule_score(rerank_score: Any = None, vector_score: Any = None, has_rerank: Optional[bool] = None) -> Dict[str, Any]:
    rerank_value = _safe_float(rerank_score)
    if has_rerank is None:
        has_rerank = rerank_score is not None and rerank_value != 0.0
    if has_rerank:
        calibrated = 1.0 / (1.0 + math.exp(-((rerank_value - RERANK_SCORE_CENTER) / RERANK_SCORE_SCALE)))
        return {
            "rule_score": round(_clamp_score(calibrated), 4),
            "rule_score_source": "rerank_score",
            "rule_score_raw": rerank_value,
            "rule_score_mapping": "sigmoid",
            "rule_score_center": RERANK_SCORE_CENTER,
            "rule_score_scale": RERANK_SCORE_SCALE,
        }

    vector_value = _safe_float(vector_score)
    return {
        "rule_score": _clamp_score(vector_value),
        "rule_score_source": "vector_score",
        "rule_score_raw": vector_value,
        "rule_score_mapping": "clamp",
        "rule_score_center": RERANK_SCORE_CENTER,
        "rule_score_scale": RERANK_SCORE_SCALE,
    }


def _combine_scores(llm_score: Any, rule_score: Any) -> float:
    combined = _clamp_score(llm_score) * LLM_SCORE_WEIGHT + _clamp_score(rule_score) * RULE_SCORE_WEIGHT
    return round(combined, 4)


def _record_score_breakdown(record: Any, llm_score: Any, rule_score: Any, rule_calibration: Dict[str, Any]) -> Dict[str, Any]:
    breakdown = dict(getattr(record, "score_breakdown", {}) or {})
    if not breakdown.get("rule_score_mapping"):
        breakdown.update(_build_score_breakdown(llm_score, rule_score, rule_calibration))
    return breakdown


def _build_score_breakdown(llm_score: Any, rule_score: Any, rule_calibration: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    rule_calibration = rule_calibration or {
        "rule_score_source": "",
        "rule_score_raw": _safe_float(rule_score),
        "rule_score_mapping": "stored",
        "rule_score_center": RERANK_SCORE_CENTER,
        "rule_score_scale": RERANK_SCORE_SCALE,
    }
    return {
        "llm_score": _clamp_score(llm_score),
        "rule_score": _clamp_score(rule_score),
        "rule_score_source": rule_calibration.get("rule_score_source", ""),
        "rule_score_raw": _safe_float(rule_calibration.get("rule_score_raw", rule_score)),
        "rule_score_mapping": rule_calibration.get("rule_score_mapping", ""),
        "rule_score_center": _safe_float(rule_calibration.get("rule_score_center", RERANK_SCORE_CENTER)),
        "rule_score_scale": _safe_float(rule_calibration.get("rule_score_scale", RERANK_SCORE_SCALE)),
        "weights": {
            "llm": LLM_SCORE_WEIGHT,
            "rule": RULE_SCORE_WEIGHT,
        },
    }


def _parse_llm_quality_result(content: str) -> Dict[str, Any]:
    text = (content or "").strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise RuntimeError("评估结果格式无效")
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise RuntimeError("评估结果格式无效") from exc
    score = _clamp_score(data.get("score", 0.0))
    reason = str(data.get("reason") or "").strip()
    if not reason:
        raise RuntimeError("评估结果缺少原因")
    return {"score": score, "reason": reason}


def _clamp_score(value: Any) -> float:
    score = _safe_float(value)
    if score < 0:
        return 0.0
    if score > 1:
        return 1.0
    return round(score, 4)


def _safe_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _build_summary(items: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(items)
    passed = sum(1 for item in items if item["status"] == "passed")
    failed = total - passed
    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "context_recall_avg": _average([item["context_recall"] for item in items]),
        "context_precision_avg": _average([item["context_precision"] for item in items]),
        "faithfulness_avg": _average([
            item["faithfulness"] if item["faithfulness"] is not None else 0.0
            for item in items
        ]),
    }


def _average(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 4)


def _clean_score(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if value != value:
            return None
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _format_ragas_error(exc: Exception) -> str:
    message = str(exc) or ""
    if "评估依赖未安装" in message:
        return message
    if "RAGAS 评估模型" in message or "RAGAS 向量模型" in message:
        return message
    return "评估失败"


class _ProjectEmbeddings:
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        from internal.embedding.embedding_service import embedding_service

        return embedding_service.encode(texts).tolist()

    def embed_query(self, text: str) -> List[float]:
        from internal.embedding.embedding_service import embedding_service

        return embedding_service.encode_query(text).tolist()
