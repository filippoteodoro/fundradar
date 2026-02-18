import math
import pickle
from collections import Counter


class NaiveBayesModel:
    def __init__(self, alpha=1.0):
        self.alpha = alpha
        self.class_counts = Counter()
        self.token_counts = {}
        self.total_tokens = {}
        self.vocab = set()
        self.classes_ = []

    def fit(self, docs, labels):
        for tokens, label in zip(docs, labels):
            self.class_counts[label] += 1
            if label not in self.token_counts:
                self.token_counts[label] = Counter()
                self.total_tokens[label] = 0
            self.token_counts[label].update(tokens)
            self.total_tokens[label] += len(tokens)
            self.vocab.update(tokens)

        self.classes_ = sorted(self.class_counts.keys())
        return self

    def predict_proba(self, tokens):
        vocab_size = max(1, len(self.vocab))
        total_docs = sum(self.class_counts.values()) or 1
        log_probs = {}
        for label in self.classes_:
            prior = self.class_counts[label] / total_docs
            log_prob = math.log(prior + 1e-12)
            total_tokens = self.total_tokens[label]
            denom = total_tokens + self.alpha * vocab_size
            for token in tokens:
                count = self.token_counts[label].get(token, 0)
                log_prob += math.log((count + self.alpha) / denom)
            log_probs[label] = log_prob

        max_log = max(log_probs.values()) if log_probs else 0.0
        exp_sum = 0.0
        probs = {}
        for label, log_prob in log_probs.items():
            prob = math.exp(log_prob - max_log)
            probs[label] = prob
            exp_sum += prob
        if exp_sum == 0.0:
            return {label: 1.0 / len(self.classes_) for label in self.classes_}
        return {label: prob / exp_sum for label, prob in probs.items()}

    def predict(self, tokens):
        probs = self.predict_proba(tokens)
        return max(probs, key=probs.get), probs

    def dump(self, path):
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return pickle.load(f)
