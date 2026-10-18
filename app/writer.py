"""Draft generation: retrieve the creator's closest posts, ask Gemma for several
drafts, then keep the ones that score closest to the creator's voice."""

from __future__ import annotations

import re

from . import llm, slop
from .stylometry import VoiceProfile, describe, nearest_posts, voice_match

FORMATS = {
    "x_post": ("a single X (Twitter) post", 280),
    "thread": ("an X thread of 4-6 numbered posts", 1400),
    "linkedin": ("a LinkedIn post", 1300),
    "caption": ("an Instagram caption", 600),
    "newsletter": ("a newsletter intro paragraph", 900),
}

TEMPERATURES = [0.7, 0.85, 1.0, 1.1]


def build_prompt(profile: VoiceProfile, topic: str, fmt: str, notes: str = "") -> str:
    fmt_desc, max_chars = FORMATS.get(fmt, FORMATS["x_post"])
    examples = nearest_posts(topic + " " + notes, profile, k=5)
    traits = "\n".join(f"- {t}" for t in describe(profile))
    phrases = ", ".join(f'"{p}"' for p in profile.signature_phrases[:8]) or "none detected"
    ex_block = "\n\n".join(f"<post>\n{e}\n</post>" for e in examples)
    banned = "delve, tapestry, testament, realm, landscape, unlock, elevate, game-changer, seamless, leverage, pivotal, embark, moreover, furthermore, 'in today's fast-paced world', 'it's not X, it's Y', 'let that sink in'"
    return f"""You are ghostwriting for one specific person. Your only job is to sound exactly like them, not like an AI assistant.

Here are real posts they wrote. Study the rhythm, sentence length, punctuation, casing, emoji, and how they open and close:

{ex_block}

Measured traits of their writing:
{traits}

Phrases they actually use (use one only if it fits naturally): {phrases}

Never use these, they make text read as AI-written: {banned}. Do not use em-dashes unless their posts do. Do not add hashtags or emoji unless their posts do.

Write {fmt_desc} (under {max_chars} characters) in their voice.
TOPIC: {topic}
{f"THEIR NOTES: {notes}" if notes else ""}

Output only the post text. No preamble, no quotes, no explanation."""


def _clean(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^(here'?s|sure)[^\n]*:\s*\n", "", text, flags=re.I)
    if len(text) > 1 and text[0] == text[-1] and text[0] in "\"'":
        text = text[1:-1]
    return text.strip()


def score(text: str, profile: VoiceProfile) -> dict:
    rep = slop.report(text)
    vm = voice_match(text, profile)
    return {
        "voice_match": vm,
        "slop": rep["slop"],
        "flags": rep["flags"],
        # Rank: voice match, penalised by slop.
        "rank_score": vm - 0.6 * rep["slop"],
    }


async def generate(profile: VoiceProfile, topic: str, fmt: str = "x_post", notes: str = "", n: int = 4) -> dict:
    prompt = build_prompt(profile, topic, fmt, notes)
    raw = await llm.complete_many(prompt, TEMPERATURES[:n])
    drafts = []
    for text in {_clean(t) for t in raw}:
        drafts.append({"text": text, **score(text, profile)})
    drafts.sort(key=lambda d: d["rank_score"], reverse=True)
    return {"model": llm.model_name(), "provider": llm.provider(), "drafts": drafts}


async def humanize(profile: VoiceProfile, text: str) -> dict:
    """Rewrite flagged parts of any text (e.g. a ChatGPT draft) into the creator's voice."""
    before = score(text, profile)
    labels = sorted({f["label"] for f in before["flags"]})
    examples = "\n\n".join(f"<post>\n{e}\n</post>" for e in nearest_posts(text, profile, k=4))
    traits = "\n".join(f"- {t}" for t in describe(profile))
    prompt = f"""Rewrite the draft below so it sounds like the person who wrote these posts:

{examples}

Their traits:
{traits}

Problems found in the draft: {"; ".join(labels) if labels else "it does not sound like them"}.

Keep the meaning and facts. Fix the problems. Match their length, rhythm, punctuation and casing.

DRAFT:
{text}

TOPIC: rewrite of the draft
Output only the rewritten post."""
    candidates = await llm.complete_many(prompt, [0.6, 0.85, 1.0])
    scored = [{"text": _clean(c), **score(_clean(c), profile)} for c in candidates]
    best = max(scored, key=lambda d: d["rank_score"])
    return {"before": {"text": text, **before}, "after": best, "model": llm.model_name()}
