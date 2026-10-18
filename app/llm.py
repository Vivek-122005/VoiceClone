"""Gemma clients. One interface, three backends:

- gemini: Gemma 4 hosted on the Gemini API (GEMINI_API_KEY)
- ollama: Gemma running locally through Ollama (fully offline, private)
- mock:   deterministic stand-in so the app runs with no key (dev, tests, demo)
"""

from __future__ import annotations

import asyncio
import os
import random
import re

import httpx

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class LLMError(RuntimeError):
    pass


def provider() -> str:
    explicit = os.getenv("LLM_PROVIDER")
    if explicit:
        return explicit
    return "gemini" if os.getenv("GEMINI_API_KEY") else "mock"


def model_name() -> str:
    p = provider()
    if p == "gemini":
        return os.getenv("GEMMA_MODEL", "gemma-4-31b-it")
    if p == "ollama":
        return os.getenv("OLLAMA_MODEL", "gemma3:4b")
    return "mock-gemma"


async def complete(prompt: str, temperature: float = 0.9, max_tokens: int = 800) -> str:
    p = provider()
    if p == "gemini":
        return await _gemini(prompt, temperature, max_tokens)
    if p == "ollama":
        return await _ollama(prompt, temperature, max_tokens)
    return _mock(prompt, temperature)


async def complete_many(prompt: str, temperatures: list[float], max_tokens: int = 800) -> list[str]:
    results = await asyncio.gather(
        *(complete(prompt, t, max_tokens) for t in temperatures), return_exceptions=True
    )
    texts = [r for r in results if isinstance(r, str) and r.strip()]
    if not texts:
        err = next((r for r in results if isinstance(r, Exception)), None)
        raise LLMError(f"Model returned no drafts: {err}")
    return texts


THINKING_HEADROOM = 2048


async def _gemini(prompt: str, temperature: float, max_tokens: int) -> str:
    key = os.environ["GEMINI_API_KEY"]
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        # Gemma 4 thinks before answering (~500 tokens) and that can't be switched off
        # on this API, so leave headroom on top of the answer budget.
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens + THINKING_HEADROOM,
            "topP": 0.95,
        },
    }
    # The hosted Gemma endpoint intermittently returns 500/503; retry with backoff.
    async with httpx.AsyncClient(timeout=90) as client:
        for attempt in range(4):
            r = await client.post(
                GEMINI_URL.format(model=model_name()), params={"key": key}, json=body
            )
            if r.status_code not in (429, 500, 502, 503, 504):
                break
            await asyncio.sleep(1.5 * 2**attempt + random.random())
    if r.status_code != 200:
        raise LLMError(f"Gemini API {r.status_code}: {r.text[:300]}")
    data = r.json()
    try:
        cand = data["candidates"][0]
        parts = cand["content"]["parts"]
    except (KeyError, IndexError) as e:
        raise LLMError(f"Unexpected Gemini response: {str(data)[:300]}") from e
    if cand.get("finishReason") == "MAX_TOKENS":
        raise LLMError("Gemini response was cut off (MAX_TOKENS)")
    # Gemma 4 may return a thinking part first; keep only the answer text.
    return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()


async def _ollama(prompt: str, temperature: float, max_tokens: int) -> str:
    base = os.getenv("OLLAMA_URL", "http://localhost:11434")
    body = {
        "model": model_name(),
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": temperature, "num_predict": max_tokens},
    }
    async with httpx.AsyncClient(timeout=180) as client:
        r = await client.post(f"{base}/api/generate", json=body)
    if r.status_code != 200:
        raise LLMError(f"Ollama {r.status_code}: {r.text[:300]}")
    return r.json().get("response", "").strip()


def _mock(prompt: str, temperature: float) -> str:
    """Stitches the creator's own example sentences around the topic, so the
    pipeline (scoring, reranking, UI) can be exercised without a model."""
    rng = random.Random(f"{prompt[-200:]}{temperature}")
    topic = re.search(r"TOPIC:\s*(.+)", prompt)
    topic_text = topic.group(1).strip() if topic else "this"
    examples = re.findall(r"<post>\n(.*?)\n</post>", prompt, re.S)
    sents = [s for e in examples for s in re.split(r"(?<=[.!?])\s+", e) if 3 < len(s.split()) < 30]
    rng.shuffle(sents)
    body = " ".join(sents[:4]) if sents else "Here is a draft."
    opener = rng.choice(["Quick one about", "Been thinking about", "Real talk on", "Notes on"])
    return f"{opener} {topic_text}.\n\n{body}"
