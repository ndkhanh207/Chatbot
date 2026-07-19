import torch
import langchain_huggingface

from app.catalog import ProductRecord
from app.catalog import semantic


def test_cuda_embeddings_use_half_precision(monkeypatch):
    captured = {}
    from config.config import Config

    monkeypatch.setattr(Config, "EMBEDDING_DEVICE", "cuda")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(
        langchain_huggingface,
        "HuggingFaceEmbeddings",
        lambda **kwargs: captured.update(kwargs) or object(),
    )

    semantic.create_embeddings()

    assert captured["model_kwargs"]["device"] == "cuda"
    assert captured["model_kwargs"]["model_kwargs"]["torch_dtype"] is torch.float16
    assert captured["encode_kwargs"]["batch_size"] == 8


def test_canonical_product_preserves_legacy_facts():
    record = ProductRecord(
        product_id="product:gpu:rtx-4060",
        category="GPU",
        name="RTX 4060",
        brand="NVIDIA",
        price=8_000_000,
        attributes={"bộ nhớ": 8},
    )

    item = record.as_legacy_dict()
    assert item["tên"] == "RTX 4060"
    assert item["giá"] == 8_000_000
    assert item["bộ nhớ"] == 8
