"""Stylometric voice fingerprinting.

A voice profile is the mean and spread of a fixed set of style features over a
creator's own posts, plus a character n-gram centroid. Voice Match scores how
far a new text sits from that profile.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

# Function words carry style independent of topic (Mosteller & Wallace, 1963).
FUNCTION_WORDS = [
    "the", "a", "an", "and", "but", "or", "so", "because", "if", "then",
    "i", "me", "my", "we", "our", "you", "your", "it", "this", "that",
    "is", "are", "was", "be", "been", "have", "has", "do", "did", "not",
    "of", "to", "in", "on", "for", "with", "at", "by", "from", "about",
    "just", "really", "very", "actually", "like", "what", "how", "why", "all", "more",
]

EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)
WORD_RE = re.compile(r"[A-Za-z']+")
SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+|\n+")

STYLE_FEATURES = [
    "chars",
    "words",
    "sent_len_mean",
    "sent_len_std",
    "word_len_mean",
    "type_token_ratio",
    "lines_per_100w",
    "exclaim_per_100w",
    "question_per_100w",
    "comma_per_100w",
    "dash_per_100w",
    "ellipsis_per_100w",
    "emoji_per_100w",
    "hashtag_per_100w",
    "mention_per_100w",
    "caps_word_ratio",
    "lowercase_start_ratio",
    "first_person_ratio",
    "second_person_ratio",
    "contraction_ratio",
]


def words(text: str) -> list[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in SENT_SPLIT_RE.split(text) if s and s.strip()]


def style_vector(text: str) -> dict[str, float]:
    ws = words(text)
    n = max(len(ws), 1)
    per100 = 100.0 / n
    sents = sentences(text) or [text]
    sent_lens = [len(words(s)) for s in sents]
    raw_tokens = WORD_RE.findall(text)
    return {
        "chars": float(len(text)),
        "words": float(len(ws)),
        "sent_len_mean": float(np.mean(sent_lens)),
        "sent_len_std": float(np.std(sent_lens)),
        "word_len_mean": float(np.mean([len(w) for w in ws])) if ws else 0.0,
        "type_token_ratio": len(set(ws)) / n,
        "lines_per_100w": text.count("\n") * per100,
        "exclaim_per_100w": text.count("!") * per100,
        "question_per_100w": text.count("?") * per100,
        "comma_per_100w": text.count(",") * per100,
        "dash_per_100w": (text.count("—") + text.count(" - ") + text.count("--")) * per100,
        "ellipsis_per_100w": (text.count("...") + text.count("…")) * per100,
        "emoji_per_100w": len(EMOJI_RE.findall(text)) * per100,
        "hashtag_per_100w": len(re.findall(r"#\w+", text)) * per100,
        "mention_per_100w": len(re.findall(r"@\w+", text)) * per100,
        "caps_word_ratio": sum(1 for t in raw_tokens if len(t) > 1 and t.isupper()) / n,
        "lowercase_start_ratio": sum(1 for s in sents if s[:1].islower()) / len(sents),
        "first_person_ratio": sum(1 for w in ws if w in {"i", "me", "my", "i'm", "i've", "mine"}) / n,
        "second_person_ratio": sum(1 for w in ws if w in {"you", "your", "you're", "yours"}) / n,
        "contraction_ratio": sum(1 for t in raw_tokens if "'" in t) / n,
    }


def function_word_vector(text: str) -> np.ndarray:
    ws = words(text)
    counts = Counter(ws)
    n = max(len(ws), 1)
    return np.array([counts[w] / n for w in FUNCTION_WORDS])


def char_ngrams(text: str, n: int = 3) -> Counter:
    t = re.sub(r"\s+", " ", text.lower())
    return Counter(t[i : i + n] for i in range(len(t) - n + 1))


def _cosine(a: dict, b: dict) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b.get(k, 0.0) for k, v in a.items())
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


@dataclass
class VoiceProfile:
    name: str
    n_posts: int
    style_mean: dict[str, float]
    style_std: dict[str, float]
    fw_mean: list[float]
    fw_std: list[float]
    ngram_centroid: dict[str, float]
    signature_phrases: list[str]
    top_emojis: list[str]
    posts: list[str] = field(default_factory=list)
    # Calibration: how far the creator's own posts sit from their profile.
    self_distance_mean: float = 1.0
    self_distance_std: float = 0.5

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, d: dict) -> "VoiceProfile":
        return cls(**d)


def _signature_phrases(posts: list[str], k: int = 12) -> list[str]:
    """Word bigrams/trigrams the creator repeats across different posts."""
    doc_freq: Counter = Counter()
    for p in posts:
        grams = set()
        for sent in sentences(p):
            ws = words(sent)
            for n in (2, 3):
                for i in range(len(ws) - n + 1):
                    g = ws[i : i + n]
                    if all(w in FUNCTION_WORDS for w in g):
                        continue
                    grams.add(" ".join(g))
        doc_freq.update(grams)
    min_df = 2 if len(posts) >= 4 else 1
    ranked = [g for g, c in doc_freq.most_common() if c >= min_df]
    # Drop phrases contained in a longer kept phrase.
    kept: list[str] = []
    for g in sorted(ranked, key=lambda g: (-doc_freq[g], -len(g))):
        if any(g in k_ for k_ in kept):
            continue
        kept.append(g)
        if len(kept) >= k:
            break
    return kept


def _tfidf_centroid(posts: list[str]) -> dict[str, float]:
    grams = [char_ngrams(p) for p in posts]
    df: Counter = Counter()
    for g in grams:
        df.update(g.keys())
    n = len(posts)
    centroid: Counter = Counter()
    for g in grams:
        total = sum(g.values()) or 1
        for k, v in g.items():
            centroid[k] += (v / total) * math.log((1 + n) / (1 + df[k]) + 1)
    # Keep the 3000 strongest n-grams so the profile stays small.
    return {k: v / n for k, v in centroid.most_common(3000)}


def _raw_distance(text: str, p: VoiceProfile) -> float:
    sv = style_vector(text)
    z = []
    for f in STYLE_FEATURES:
        if f in ("chars", "words"):
            continue  # length is judged against the requested format, not the voice
        sd = max(p.style_std[f], 0.05 * abs(p.style_mean[f]) + 1e-3)
        z.append(min(abs(sv[f] - p.style_mean[f]) / sd, 6.0))
    fw = function_word_vector(text)
    fw_sd = np.maximum(np.array(p.fw_std), 0.005)
    fw_z = np.minimum(np.abs(fw - np.array(p.fw_mean)) / fw_sd, 6.0)
    style_d = float(np.mean(z))
    fw_d = float(np.mean(fw_z))
    ngram_sim = _cosine(_tfidf_centroid([text]), p.ngram_centroid)
    return 0.45 * style_d + 0.35 * fw_d + 0.20 * (1 - ngram_sim) * 6


def _make_profile(posts: list[str], name: str) -> VoiceProfile:
    svs = [style_vector(p) for p in posts]
    fws = np.array([function_word_vector(p) for p in posts])
    emoji_counts: Counter = Counter()
    for p in posts:
        emoji_counts.update(EMOJI_RE.findall(p))
    return VoiceProfile(
        name=name,
        n_posts=len(posts),
        style_mean={f: float(np.mean([s[f] for s in svs])) for f in STYLE_FEATURES},
        style_std={f: float(np.std([s[f] for s in svs])) for f in STYLE_FEATURES},
        fw_mean=fws.mean(axis=0).tolist(),
        fw_std=fws.std(axis=0).tolist(),
        ngram_centroid=_tfidf_centroid(posts),
        signature_phrases=_signature_phrases(posts),
        top_emojis=[e for e, _ in emoji_counts.most_common(6)],
        posts=posts,
    )


def build_profile(posts: list[str], name: str = "My voice") -> VoiceProfile:
    posts = [p.strip() for p in posts if p and len(p.strip()) >= 20]
    if len(posts) < 3:
        raise ValueError("Need at least 3 posts of 20+ characters to learn a voice.")
    prof = _make_profile(posts, name)
    # Leave-one-out calibration: how far an unseen post by the same creator
    # sits from a profile built on their other posts.
    held_out = posts[:30]
    self_d = []
    for i, p in enumerate(held_out):
        rest = posts[:i] + posts[i + 1 :]
        self_d.append(_raw_distance(p, _make_profile(rest, name)))
    prof.self_distance_mean = float(np.mean(self_d))
    prof.self_distance_std = float(max(np.std(self_d), 0.15))
    return prof


def voice_match(text: str, p: VoiceProfile) -> int:
    """0-100. ~85+ means it reads like the creator's own posts."""
    d = _raw_distance(text, p)
    z = (d - p.self_distance_mean) / p.self_distance_std
    score = 100 / (1 + math.exp(z - 1.5))
    return int(round(max(0.0, min(100.0, score))))


def describe(p: VoiceProfile) -> list[str]:
    """Plain-language voice traits for the UI and the prompt."""
    m = p.style_mean
    traits = []
    sl = m["sent_len_mean"]
    traits.append(
        f"Sentences average {sl:.0f} words"
        + (" (short and punchy)" if sl < 11 else " (long and flowing)" if sl > 20 else "")
    )
    traits.append(
        "Rhythm is bursty: very short lines next to long ones"
        if m["sent_len_std"] > 0.6 * sl
        else "Rhythm is even: sentences are similar in length"
    )
    if m["lines_per_100w"] > 4:
        traits.append("Uses lots of line breaks")
    if m["lowercase_start_ratio"] > 0.3:
        traits.append("Often starts sentences in lowercase")
    if m["emoji_per_100w"] > 0.8:
        traits.append("Uses emoji: " + " ".join(p.top_emojis[:4]))
    elif m["emoji_per_100w"] < 0.1:
        traits.append("Almost never uses emoji")
    if m["exclaim_per_100w"] > 1.5:
        traits.append("Exclamation marks are part of the voice")
    if m["question_per_100w"] > 1.5:
        traits.append("Asks the reader questions")
    if m["dash_per_100w"] < 0.2:
        traits.append("Avoids dashes")
    if m["hashtag_per_100w"] > 1:
        traits.append("Uses hashtags")
    elif m["hashtag_per_100w"] < 0.1:
        traits.append("No hashtags")
    if m["first_person_ratio"] > 0.05:
        traits.append("Writes from personal experience (lots of I/my)")
    if m["second_person_ratio"] > 0.04:
        traits.append("Talks directly to the reader (you/your)")
    if m["contraction_ratio"] > 0.04:
        traits.append("Casual contractions (I'm, don't, it's)")
    elif m["contraction_ratio"] < 0.01:
        traits.append("Formal: rarely uses contractions")
    traits.append(f"Posts are usually around {m['words']:.0f} words")
    return traits


def nearest_posts(query: str, p: VoiceProfile, k: int = 4) -> list[str]:
    """The creator's posts closest to a topic, used as few-shot examples."""
    q_words = Counter(w for w in words(query) if w not in FUNCTION_WORDS)
    q = {w: float(c) for w, c in q_words.items()}
    scored = []
    for post in p.posts:
        pw = Counter(w for w in words(post) if w not in FUNCTION_WORDS)
        sim = _cosine(q, {w: float(c) for w, c in pw.items()})
        scored.append((sim, -abs(len(post) - p.style_mean["chars"]), post))
    scored.sort(reverse=True)
    return [s[2] for s in scored[:k]]
