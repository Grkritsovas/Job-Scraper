from dataclasses import dataclass


@dataclass(frozen=True)
class EmbeddingModelSpec:
    key: str
    model_name: str
    label: str
    notes: str


ALL_MINILM_L6_V2 = EmbeddingModelSpec(
    key="all_minilm_l6_v2",
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    label="all-MiniLM-L6-v2",
    notes="Small and fast general-purpose sentence-transformer baseline.",
)

BGE_BASE_EN_V1_5 = EmbeddingModelSpec(
    key="bge_base_en_v1_5",
    model_name="BAAI/bge-base-en-v1.5",
    label="bge-base-en-v1.5",
    notes="Retrieval-oriented English embedding model worth comparing against MiniLM.",
)

AVAILABLE_EMBEDDING_MODELS = {
    model.key: model
    for model in [
        ALL_MINILM_L6_V2,
        BGE_BASE_EN_V1_5,
    ]
}
