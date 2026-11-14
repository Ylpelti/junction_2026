"""Deterministic test double. Its vectors are NOT model-quality benchmark results."""
import math


class FakeEmbedder:
    model_key = "SYNTHETIC-TEST-EMBEDDER-v1"
    max_tokens = 512
    def __init__(self):
        self.calls = 0
    def token_count(self, text):
        return len(text)
    def passages(self, texts):
        self.calls += len(texts)
        return [self.query(text) for text in texts]
    def query(self, text):
        vector = [0.01] * 384
        for position, words in enumerate((('pain', 'vatsa', 'abdominal'), ('fatigue', 'väsym', 'uupum'), ('normal', 'normaali', 'resolved'))):
            if any(word in text.casefold() for word in words):
                vector[position] += 1
        norm = math.sqrt(sum(value * value for value in vector))
        return [value / norm for value in vector]
