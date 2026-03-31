import unittest

from matching.models import (
    ALL_MINILM_L6_V2,
    AVAILABLE_EMBEDDING_MODELS,
    BGE_BASE_EN_V1_5,
)
from matching.ranking import EMBEDDING_MODEL_NAME, SELECTED_EMBEDDING_MODEL


class MatchingModelsTests(unittest.TestCase):
    def test_embedding_model_catalog_contains_expected_models(self):
        self.assertEqual(ALL_MINILM_L6_V2, AVAILABLE_EMBEDDING_MODELS["all_minilm_l6_v2"])
        self.assertEqual(BGE_BASE_EN_V1_5, AVAILABLE_EMBEDDING_MODELS["bge_base_en_v1_5"])

    def test_ranking_defaults_to_selected_embedding_model(self):
        self.assertEqual(ALL_MINILM_L6_V2, SELECTED_EMBEDDING_MODEL)
        self.assertEqual(ALL_MINILM_L6_V2.model_name, EMBEDDING_MODEL_NAME)


if __name__ == "__main__":
    unittest.main()
