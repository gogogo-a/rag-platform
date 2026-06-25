"""Persist reusable expert workflow experience."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from log import logger
from internal.db.qdrant import qa_qdrant_client
from internal.embedding.embedding_service import embedding_service
from internal.model.expert_experience import ExpertExperienceModel


class ExpertExperienceStore:
    async def save_experience(
        self,
        question_id: str,
        question: str,
        answer: str,
        expert_results: List[Dict[str, Any]],
        failed_tasks: Optional[List[Dict[str, Any]]] = None,
        should_cache: bool = True,
    ) -> Optional[str]:
        try:
            lesson = self._build_lesson(expert_results, failed_tasks or [])
            model = ExpertExperienceModel(
                question_id=question_id,
                question=question,
                answer=answer,
                expert_results=expert_results,
                failed_tasks=failed_tasks or [],
                lesson=lesson,
            )
            await model.insert()

            if should_cache and lesson:
                vector_id = await self._save_to_vector_store(model.uuid, question, lesson)
                if vector_id:
                    model.vector_id = vector_id
                    await model.save()

            return model.uuid
        except Exception as exc:
            logger.warning(f"专家经验保存失败: {exc}")
            return None

    def _build_lesson(self, expert_results: List[Dict[str, Any]], failed_tasks: List[Dict[str, Any]]) -> str:
        useful = [
            f"{item.get('expert_key', '')}: {item.get('answer', '')}".strip()
            for item in expert_results
            if item.get("success") and item.get("answer")
        ]
        failures = [
            f"{item.get('expert_key', '')}: {item.get('error', '')}".strip()
            for item in failed_tasks
            if item.get("error")
        ]
        parts = []
        if useful:
            parts.append("可复用结论：" + "；".join(useful)[:800])
        if failures:
            parts.append("需避免的问题：" + "；".join(failures)[:500])
        return "\n".join(parts)

    async def _save_to_vector_store(self, experience_id: str, question: str, lesson: str) -> Optional[str]:
        try:
            embedding = embedding_service.encode_query(question)
            return qa_qdrant_client.upsert_qa_cache(
                embedding=embedding,
                question=question,
                metadata={
                    "thought_chain_id": experience_id,
                    "experience_type": "expert_workflow",
                    "answer_preview": lesson[:200],
                },
            )
        except Exception as exc:
            logger.warning(f"专家经验入库失败: {exc}")
            return None


expert_experience_store = ExpertExperienceStore()
