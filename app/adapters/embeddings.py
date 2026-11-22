import hashlib
import importlib
import math
import struct
from pathlib import Path
from typing import Any, Protocol

from app.errors import Problem
from app.services.retrieval.chunker import words


class EmbeddingProvider(Protocol):
    model_id: str

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]: ...


class FakeEmbeddingProvider:
    """Hash vectors test plumbing only; they have no semantic accuracy claim."""

    model_id = "fake-hash-384-v1"

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:

        result = []
        for text in texts:
            vector = [0.0] * 384
            for word in words(text):
                digest = hashlib.sha256(word.encode()).digest()
                vector[int.from_bytes(digest[:4], "little") % 384] += 1
            norm = math.sqrt(sum(v * v for v in vector)) or 1
            result.append([v / norm for v in vector])
        return result


class E5Provider:
    model_id = "intfloat/multilingual-e5-small"

    def __init__(self, path: Path) -> None:
        try:
            module = importlib.import_module("sentence_transformers")
        except ImportError:
            raise Problem(
                503,
                "embeddings_unavailable",
                "Install the optional embeddings extra and local model first.",
            ) from None
        self.model: Any = module.SentenceTransformer(
            str(path.resolve()),
            device="cpu",
            local_files_only=True,
            trust_remote_code=False,
            prompts={"query": "", "document": ""},
        )
        self.model.max_seq_length = 512
        if self.model.get_sentence_embedding_dimension() != 384:
            raise Problem(
                503, "embedding_model_invalid", "The configured model must have 384 dimensions."
            )

    def encode(self, texts: list[str], *, query: bool = False) -> list[list[float]]:
        inputs = [("query: " if query else "passage: ") + text for text in texts]
        if any(
            len(self.model.tokenizer.encode(text, add_special_tokens=True)) > 512 for text in inputs
        ):
            raise Problem(
                422,
                "embedding_input_too_long",
                "This passage exceeds the local model input limit. Split it before indexing.",
            )
        result: list[list[float]] = self.model.encode(
            inputs, normalize_embeddings=True, show_progress_bar=False, convert_to_numpy=True
        ).tolist()
        return result


def pack(vector: list[float]) -> bytes:
    if len(vector) != 384 or not all(math.isfinite(v) for v in vector):
        raise Problem(
            502, "invalid_embedding", "The embedding output has an invalid dimension or value."
        )
    return struct.pack("<384f", *vector)


def unpack(blob: bytes) -> list[float]:
    if len(blob) != 1536:
        raise Problem(409, "invalid_embedding", "Rebuild this local embedding index.")
    return list(struct.unpack("<384f", blob))


def cosine(left: list[float], right: list[float], *, numpy: bool = False) -> float:
    if numpy:
        np = importlib.import_module("numpy")
        a, b = np.asarray(left, dtype=np.float32), np.asarray(right, dtype=np.float32)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) or 1))
    length = math.sqrt(sum(x * x for x in left) * sum(x * x for x in right)) or 1
    return sum(x * y for x, y in zip(left, right, strict=True)) / length
