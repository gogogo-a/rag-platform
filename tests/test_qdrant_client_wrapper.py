import unittest
import uuid
from unittest.mock import patch

from internal.db.qdrant import QdrantVectorClient
from internal.rag.dedup import deduplicate_results


class FakeCollections:
    def __init__(self, names):
        self.collections = [type("CollectionInfo", (), {"name": name}) for name in names]


class FakeQdrantClient:
    def __init__(self):
        self.created = []
        self.upserts = []
        self.deleted = []
        self.collections = set()

    def get_collections(self):
        return FakeCollections(self.collections)

    def create_collection(self, collection_name, vectors_config):
        self.created.append((collection_name, vectors_config))
        self.collections.add(collection_name)

    def upsert(self, collection_name, points):
        self.upserts.append((collection_name, points))

    def delete(self, collection_name, points_selector):
        self.deleted.append((collection_name, points_selector))

    def scroll(self, collection_name, scroll_filter=None, limit=100, with_payload=True, with_vectors=False):
        return [], None


class QdrantVectorClientTest(unittest.TestCase):
    def test_upsert_documents_creates_collection_and_payloads(self):
        fake = FakeQdrantClient()
        wrapper = QdrantVectorClient(client=fake, collection_name="docs", dimension=3)

        ids = wrapper.upsert_documents(
            embeddings=[[0.1, 0.2, 0.3]],
            texts=["hello"],
            metadata=[{"document_uuid": "doc-1", "permission": 0}],
        )

        expected_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "document:doc-1:0"))
        self.assertEqual(ids, [expected_id])
        self.assertEqual(fake.created[0][0], "docs")
        self.assertEqual(fake.upserts[0][0], "docs")
        point = fake.upserts[0][1][0]
        self.assertEqual(point.id, expected_id)
        self.assertEqual(point.payload["text"], "hello")
        self.assertEqual(point.payload["metadata"]["document_uuid"], "doc-1")

    def test_delete_by_document_uuid_uses_metadata_filter(self):
        fake = FakeQdrantClient()
        wrapper = QdrantVectorClient(client=fake, collection_name="docs", dimension=3)

        wrapper.delete_by_document_uuid("doc-1")

        selector = fake.deleted[0][1]
        condition = selector.must[0]
        self.assertEqual(condition.key, "metadata.document_uuid")
        self.assertEqual(condition.match.value, "doc-1")


class RagResultDeduplicationTest(unittest.TestCase):
    def test_text_similar_chunks_are_deduplicated_even_when_scores_differ(self):
        results = [
            {
                "text": "企业级 RAG 平台需要完成权限隔离、检索质量评估、工具调用链保存。 1001. 验收标准是回答可追溯。",
                "metadata": {"document_uuid": "doc-1", "chunk_index": 1},
                "vector_score": 0.91,
            },
            {
                "text": "企业级 RAG 平台需要完成权限隔离、检索质量评估、工具调用链保存。 2048. 验收标准是回答可追溯。",
                "metadata": {"document_uuid": "doc-1", "chunk_index": 2},
                "vector_score": 0.86,
            },
            {
                "text": "系统还需要提供用户登录、角色权限、会话管理和文档上传能力。",
                "metadata": {"document_uuid": "doc-2", "chunk_index": 1},
                "vector_score": 0.84,
            },
        ]

        deduplicated = deduplicate_results(results, target_count=3)

        self.assertEqual(len(deduplicated), 2)
        self.assertEqual(deduplicated[0]["metadata"]["chunk_index"], 1)
        self.assertEqual(deduplicated[1]["metadata"]["document_uuid"], "doc-2")

    def test_mcp_search_uses_rag_deduplication_path(self):
        from pkg.agent_tools_mcp import knowledge_search_mcp

        deduplicated_results = [
            {
                "text": "去重后的文本块",
                "metadata": {"filename": "方案.docx", "document_uuid": "doc-1"},
                "vector_score": 0.9,
            }
        ]

        def fake_search(query, top_k, use_reranker, user_permission):
            return deduplicated_results

        with patch.object(knowledge_search_mcp, "_get_rag_search", return_value=fake_search):
            payload = knowledge_search_mcp._search_knowledge_base("RAG", 5, True, 0)

        self.assertEqual(payload, deduplicated_results)

    def test_same_score_different_text_chunks_are_kept(self):
        results = [
            {
                "text": "企业级 RAG 平台需要权限隔离和检索质量评估。",
                "metadata": {"document_uuid": "doc-1"},
                "vector_score": 0.91,
            },
            {
                "text": "系统还需要支持账号登录、角色管理和会话保存。",
                "metadata": {"document_uuid": "doc-2"},
                "vector_score": 0.90,
            },
        ]

        deduplicated = deduplicate_results(results, target_count=2)

        self.assertEqual(len(deduplicated), 2)

    def test_rag_search_falls_back_to_vector_results_when_reranker_fails(self):
        from internal.rag.rag_service import RAGService

        vector_results = [
            {
                "text": "耿浩 实习经历：参与 AI 产品后台管理系统及官网建设。",
                "metadata": {"filename": "耿浩-全栈开发工程师.pdf", "document_uuid": "doc-1"},
                "vector_score": 0.91,
            }
        ]

        class FailingReranker:
            def rerank(self, **kwargs):
                raise RuntimeError("reranker missing")

        service = RAGService(use_reranker=True)
        service.reranker = FailingReranker()

        with patch("internal.rag.rag_service.embedding_service") as fake_embedding, \
             patch("internal.rag.rag_service.qdrant_client") as fake_qdrant:
            fake_embedding.encode_query.return_value = [0.1, 0.2]
            fake_qdrant.search_documents.return_value = vector_results

            results = service.search("耿浩的实习经历有什么", top_k=5, user_permission=1)

        self.assertEqual(results, vector_results)

    def test_rag_search_fuses_vector_and_keyword_results_with_rrf(self):
        from internal.rag.rag_service import RAGService

        vector_results = [
            {
                "text": "vector only",
                "metadata": {"document_uuid": "doc-vector", "chunk_index": 0},
                "vector_score": 0.91,
                "score": 0.91,
            },
            {
                "text": "shared result",
                "metadata": {"document_uuid": "doc-shared", "chunk_index": 0},
                "vector_score": 0.82,
                "score": 0.82,
            },
        ]
        keyword_results = [
            {
                "text": "shared result",
                "metadata": {"document_uuid": "doc-shared", "chunk_index": 0},
                "bm25_score": 3.0,
            },
            {
                "text": "keyword only",
                "metadata": {"document_uuid": "doc-keyword", "chunk_index": 0},
                "bm25_score": 2.0,
            },
        ]

        service = RAGService(use_reranker=False)

        with patch("internal.rag.rag_service.embedding_service") as fake_embedding, \
             patch("internal.rag.rag_service.qdrant_client") as fake_qdrant, \
             patch.object(service, "_keyword_search", return_value=keyword_results):
            fake_embedding.encode_query.return_value = [0.1, 0.2]
            fake_qdrant.search_documents.return_value = vector_results

            results = service.search("shared", top_k=3, user_permission=1)

        self.assertEqual(results[0]["metadata"]["document_uuid"], "doc-shared")
        self.assertAlmostEqual(results[0]["rrf_score"], 1 / 62 + 1 / 61)
        self.assertEqual(results[1]["metadata"]["document_uuid"], "doc-vector")
        self.assertEqual(results[2]["metadata"]["document_uuid"], "doc-keyword")


if __name__ == "__main__":
    unittest.main()
