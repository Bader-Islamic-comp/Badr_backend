"""Local Hugging Face models for offline evaluation only (never used by the server).

Loaded from the local cache (`local_files_only`), in bfloat16 to fit a small machine, one at a time.
"""
from hashlib import sha256
import json
from pathlib import Path
import sys
from typing import Sequence

from ..rag.embeddings import l2_normalize


class HFEmbedder:
    """Mean-pooled sentence embeddings (multilingual-e5 style, with its query/passage prefixes)."""

    def __init__(self, repo: str, *, doc_prefix: str = "passage: ", query_prefix: str = "query: ",
                 max_length: int = 512, batch_size: int = 16, pooling: str = "mean"):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(repo, local_files_only=True)
        self.model = AutoModel.from_pretrained(repo, local_files_only=True, torch_dtype=torch.bfloat16).eval()
        self.doc_prefix, self.query_prefix = doc_prefix, query_prefix
        self.max_length, self.batch_size, self.pooling = max_length, batch_size, pooling

    def _encode(self, texts: Sequence[str]) -> list[list[float]]:
        torch = self.torch
        out = []
        with torch.inference_mode():
            for start in range(0, len(texts), self.batch_size):
                batch = self.tokenizer(list(texts[start:start + self.batch_size]), padding=True, truncation=True,
                                       max_length=self.max_length, return_tensors="pt")
                hidden = self.model(**batch).last_hidden_state.float()
                if self.pooling == "cls":
                    pooled = hidden[:, 0]
                else:
                    mask = batch["attention_mask"].unsqueeze(-1).float()
                    pooled = (hidden * mask).sum(1) / mask.sum(1)
                out += [l2_normalize(row.tolist()) for row in pooled]
                if start and start % (self.batch_size * 20) == 0:
                    print(f"    ... encoded {start}/{len(texts)}", file=sys.stderr, flush=True)
        return out

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode([self.doc_prefix + text for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([self.query_prefix + text])[0]


class HFReranker:
    """Cross-encoder relevance scores, cached on disk per (question, passage) pair."""

    def __init__(self, repo: str, cache: Path, *, max_length: int = 384, batch_size: int = 16):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(repo, local_files_only=True)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            repo, local_files_only=True, torch_dtype=torch.bfloat16).eval()
        self.max_length, self.batch_size = max_length, batch_size
        self.path = cache
        self.scores = json.loads(cache.read_text()) if cache.is_file() else {}
        self.fresh = 0

    @staticmethod
    def key(question: str, passage: str) -> str:
        return sha256((question + "\x1f" + passage).encode("utf-8")).hexdigest()[:24]

    def score(self, question: str, passages: Sequence[str]) -> list[float]:
        todo = [p for p in dict.fromkeys(passages) if self.key(question, p) not in self.scores]
        torch = self.torch
        with torch.inference_mode():
            for start in range(0, len(todo), self.batch_size):
                batch = todo[start:start + self.batch_size]
                encoded = self.tokenizer([question] * len(batch), batch, padding=True, truncation=True,
                                         max_length=self.max_length, return_tensors="pt")
                logits = self.model(**encoded).logits.float().view(-1).tolist()
                for passage, value in zip(batch, logits):
                    self.scores[self.key(question, passage)] = value
                self.fresh += len(batch)
        if self.fresh >= 500:
            self.save()
        return [self.scores[self.key(question, p)] for p in passages]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.scores))
        self.fresh = 0


class LazyReranker:
    """An HFReranker that loads its model on first use, so embedders can be freed before it takes memory."""

    def __init__(self, repo: str, cache: Path):
        self.repo, self.cache, self._model = repo, cache, None

    def score(self, question: str, passages: Sequence[str]) -> list[float]:
        if self._model is None:
            print(f"loading reranker {self.repo}", file=sys.stderr, flush=True)
            self._model = HFReranker(self.repo, self.cache)
        return self._model.score(question, passages)

    def save(self) -> None:
        if self._model is not None:
            self._model.save()
