import importlib
import sys
import unittest
from unittest.mock import patch


class FakeEmbeddingModel:
    pass


class FakeRerankerModel:
    pass


class ModelPreloadTest(unittest.TestCase):
    def test_embedding_load_model_reuses_existing_model(self):
        from internal.embedding.embedding_service import EmbeddingService

        EmbeddingService._instance = None
        EmbeddingService._initialized = False
        service = EmbeddingService()

        with patch(
            "internal.embedding.embedding_service.ModelManager.select_embedding_model",
            return_value=FakeEmbeddingModel(),
        ) as select_model:
            service.load_model()
            service.load_model()

        self.assertEqual(1, select_model.call_count)
        self.assertIsInstance(service.model, FakeEmbeddingModel)

    def test_reranker_load_model_reuses_existing_model(self):
        from internal.reranker.reranker_service import RerankerService

        RerankerService._instance = None
        RerankerService._initialized = False
        service = RerankerService()

        with patch(
            "internal.reranker.reranker_service.ModelManager.select_reranker_model",
            return_value=FakeRerankerModel(),
        ) as select_model:
            service.load_model()
            service.load_model()

        self.assertEqual(1, select_model.call_count)
        self.assertIsInstance(service.model, FakeRerankerModel)

    def test_resource_monitor_import_does_not_create_instance(self):
        sys.modules.pop("internal.monitor", None)
        sys.modules.pop("internal.monitor.resource_monitor", None)
        module = importlib.import_module("internal.monitor.resource_monitor")

        self.assertIsNone(module._resource_monitor)

    def test_resource_monitor_still_starts_on_demand(self):
        module = importlib.import_module("internal.monitor.resource_monitor")

        module._resource_monitor = None
        module.start_resource_monitoring(interval=60)
        try:
            self.assertIsNotNone(module._resource_monitor)
            self.assertTrue(module._resource_monitor.monitoring)
        finally:
            module.stop_resource_monitoring()


if __name__ == "__main__":
    unittest.main()
