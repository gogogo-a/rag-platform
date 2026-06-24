import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from internal.service.evaluation.rag_evaluation_service import RAGEvaluationService


class FakeBenchmarkQuery:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self):
        return self.rows


class FakeBenchmarkModel:
    is_active = object()
    rows = []

    @classmethod
    def find(cls, _condition):
        return FakeBenchmarkQuery(list(cls.rows))


class FakeEvaluationModel:
    created = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeEvaluationModel.created.append(self)
        self.insert = AsyncMock()


class FakeRAGService:
    def __init__(self, results_by_query):
        self.results_by_query = results_by_query

    def search(self, query, top_k=5, use_reranker=True, user_permission=1):
        return list(self.results_by_query.get(query, []))


class FakeRAGASEvaluator:
    async def evaluate(self, rows, include_faithfulness=False):
        scores = []
        for row in rows:
            if not row["contexts"]:
                scores.append({
                    "context_recall": 0.0,
                    "context_precision": 0.0,
                    "faithfulness": None,
                })
            else:
                scores.append({
                    "context_recall": 0.8,
                    "context_precision": 0.7,
                    "faithfulness": 0.9 if include_faithfulness else None,
                })
        return scores


class FailingRAGService:
    def search(self, query, top_k=5, use_reranker=True, user_permission=1):
        raise RuntimeError("search failed")


class RAGEvaluationServiceTest(unittest.TestCase):
    def setUp(self):
        FakeEvaluationModel.created = []
        FakeBenchmarkModel.rows = [
            SimpleNamespace(
                question="普通用户是否可以检索管理员文档？",
                ground_truth="不可以。检索阶段会根据用户角色过滤文档权限。",
                category="权限控制",
                difficulty=2,
            ),
            SimpleNamespace(
                question="没有检索结果的问题",
                ground_truth="应该返回低分结果。",
                category="异常场景",
                difficulty=1,
            ),
        ]

    def test_run_builds_report_and_saves_evaluations(self):
        rag_service = FakeRAGService({
            "普通用户是否可以检索管理员文档？": [
                {
                    "text": "普通用户无法检索管理员权限文档。",
                    "metadata": {
                        "document_uuid": "doc-rag-policy-002",
                        "filename": "权限说明.pdf",
                        "chunk_index": 3,
                    },
                    "vector_score": 0.91,
                    "rerank_score": 0.86,
                }
            ]
        })
        service = RAGEvaluationService(
            rag_service=rag_service,
            benchmark_model=FakeBenchmarkModel,
            evaluation_model=FakeEvaluationModel,
            ragas_evaluator=FakeRAGASEvaluator(),
        )

        report = asyncio.run(service.run(include_faithfulness=True))

        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual(report["summary"]["passed"], 1)
        self.assertEqual(report["summary"]["failed"], 1)
        self.assertAlmostEqual(report["summary"]["context_recall_avg"], 0.4)
        self.assertAlmostEqual(report["summary"]["context_precision_avg"], 0.35)
        self.assertAlmostEqual(report["summary"]["faithfulness_avg"], 0.45)

        first_item = report["items"][0]
        self.assertEqual(first_item["status"], "passed")
        self.assertEqual(first_item["retrieved_documents"][0]["document_uuid"], "doc-rag-policy-002")
        self.assertEqual(first_item["retrieved_documents"][0]["filename"], "权限说明.pdf")
        self.assertEqual(first_item["retrieved_documents"][0]["chunk_index"], 3)
        self.assertEqual(first_item["retrieved_documents"][0]["score"], 0.86)
        self.assertEqual(first_item["retrieved_documents"][0]["text"], "普通用户无法检索管理员权限文档。")

        second_item = report["items"][1]
        self.assertEqual(second_item["status"], "failed")
        self.assertEqual(second_item["context_recall"], 0.0)
        self.assertEqual(second_item["retrieved_documents"], [])

        self.assertEqual(len(FakeEvaluationModel.created), 2)
        self.assertEqual(FakeEvaluationModel.created[0].kwargs["evaluator"], "ragas")
        self.assertEqual(FakeEvaluationModel.created[0].kwargs["dataset_type"], "benchmark")
        FakeEvaluationModel.created[0].insert.assert_awaited_once()

    def test_build_ragas_rows_uses_ground_truth_and_contexts(self):
        rag_service = FakeRAGService({
            "普通用户是否可以检索管理员文档？": [
                {"text": "片段一", "metadata": {}, "vector_score": 0.8}
            ]
        })
        service = RAGEvaluationService(
            rag_service=rag_service,
            benchmark_model=FakeBenchmarkModel,
            evaluation_model=FakeEvaluationModel,
            ragas_evaluator=FakeRAGASEvaluator(),
        )

        rows, _items = asyncio.run(service.build_dataset(top_k=5, use_reranker=True))

        self.assertEqual(rows[0]["question"], "普通用户是否可以检索管理员文档？")
        self.assertEqual(rows[0]["ground_truth"], "不可以。检索阶段会根据用户角色过滤文档权限。")
        self.assertEqual(rows[0]["contexts"], ["片段一"])
        self.assertEqual(rows[1]["contexts"], [])

    def test_search_error_marks_item_failed_without_stopping_report(self):
        service = RAGEvaluationService(
            rag_service=FailingRAGService(),
            benchmark_model=FakeBenchmarkModel,
            evaluation_model=FakeEvaluationModel,
            ragas_evaluator=FakeRAGASEvaluator(),
        )

        report = asyncio.run(service.run(save_results=False))

        self.assertEqual(report["summary"]["total"], 2)
        self.assertEqual(report["summary"]["failed"], 2)
        self.assertEqual(report["items"][0]["status"], "failed")
        self.assertEqual(report["items"][0]["reason"], "检索失败")
        self.assertEqual(report["items"][0]["retrieved_documents"], [])


if __name__ == "__main__":
    unittest.main()
