"""Local lexical vectors for Co-STORM placement/ranking; no embedding API."""
import hashlib
import re
import numpy as np


class LocalEncoder:
    dimensions = 512

    def encode(self, texts, max_workers=None):
        single = isinstance(texts, str)
        texts = [texts] if single else list(texts)
        output = np.zeros((len(texts), self.dimensions), dtype=float)
        for row, text in enumerate(texts):
            words = re.findall(r'\w+', str(text).casefold())
            # Character trigrams also distinguish unsegmented Korean compound words.
            terms = words + [word[i:i+3] for word in words for i in range(max(0, len(word)-2))]
            for word in terms:
                index = int.from_bytes(hashlib.sha256(word.encode()).digest()[:4], 'big') % self.dimensions
                output[row, index] += 1
            norm = np.linalg.norm(output[row])
            if norm:
                output[row] /= norm
        return output[0] if single else output

    def get_total_token_usage(self, reset=False):
        return 0  # No remote embedding model/token usage.


def cosine_similarity(a, b):
    a, b = np.atleast_2d(a), np.atleast_2d(b)
    denominator = np.linalg.norm(a, axis=1)[:, None] * np.linalg.norm(b, axis=1)[None, :]
    return np.divide(a @ b.T, denominator, out=np.zeros((len(a), len(b))), where=denominator != 0)
