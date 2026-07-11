import pandas as pd
import torch

from app.core import data_loader


def test_cuda_embeddings_use_half_precision(monkeypatch):
    captured = {}
    monkeypatch.setattr(data_loader.Config, "EMBEDDING_DEVICE", "cuda")
    monkeypatch.setattr(torch.cuda, "is_available", lambda: True)
    monkeypatch.setattr(
        data_loader,
        "HuggingFaceEmbeddings",
        lambda **kwargs: captured.update(kwargs) or object(),
    )

    data_loader.create_embeddings()

    assert captured["model_kwargs"]["device"] == "cuda"
    assert captured["model_kwargs"]["model_kwargs"]["torch_dtype"] is torch.float16
    assert captured["encode_kwargs"]["batch_size"] == 8


def test_document_conversion_stays_in_process():
    docs = data_loader.convert_to_documents(
        pd.DataFrame([{"name": "RTX 4060", "category": "GPU", "search_text": "ignored"}])
    )

    assert [doc.page_content for doc in docs] == ["Name: RTX 4060 | Category: GPU"]
