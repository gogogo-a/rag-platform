import unittest
import uuid

from internal.db.qdrant import QdrantVectorClient


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


if __name__ == "__main__":
    unittest.main()
