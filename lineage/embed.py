"""SPECTER2 embedding for the lineage module.

Copied from src/ranking/embed.py (model load, CLS-token embed) and the input
contract from src/ranking/score.py (title + sep_token + abstract), deliberately
not imported, to keep the lineage module independent of the digest. If the
digest's embedding contract changes, this copy must be updated in lockstep;
that cost is accepted for zero coupling.
"""
import logging

import numpy as np
import torch
from transformers import AutoModel, AutoTokenizer

logger = logging.getLogger(__name__)


def load_model(model_name: str) -> tuple[AutoTokenizer, AutoModel]:
    """Load specter2_base tokenizer and model. Accepts a model name or local path."""
    logger.info("Loading SPECTER2 from %s", model_name)
    tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    model = AutoModel.from_pretrained(model_name, local_files_only=True)
    model.eval()
    return tokenizer, model


def build_input(title: str, abstract: str | None, tokenizer: AutoTokenizer) -> str:
    """Join title and abstract with the tokenizer's separator, matching the digest.

    A node with no abstract degrades to title-only (empty trailing segment).
    """
    return (title or "") + tokenizer.sep_token + (abstract or "")


def embed(
    texts: list[str],
    tokenizer: AutoTokenizer,
    model: AutoModel,
    batch_size: int = 16,
) -> np.ndarray:
    """Return CLS-token embeddings, shape (N, hidden_size), dtype float32."""
    if not texts:
        return np.empty((0, model.config.hidden_size), dtype=np.float32)

    all_embeddings: list[np.ndarray] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        inputs = tokenizer(
            batch,
            padding=True,
            truncation=True,
            return_tensors="pt",
            return_token_type_ids=False,
            max_length=512,
        )
        with torch.no_grad():
            output = model(**inputs)
        cls = output.last_hidden_state[:, 0, :].cpu().numpy().astype(np.float32)
        all_embeddings.append(cls)
    return np.vstack(all_embeddings)
