from __future__ import annotations

import csv
import io
import os
import re
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import llm, slop, writer
from .stylometry import VoiceProfile, build_profile, describe

ROOT = Path(__file__).parent
STATIC = ROOT / "static"
DEMO = ROOT / "demo"

app = FastAPI(title="VoiceClone Writer")

# Simple per-IP limit on model calls so a public demo can't drain the API quota.
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_HOUR", "40"))
_calls: dict[str, deque] = defaultdict(deque)


def _check_rate(request: Request) -> None:
    ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0]
    now = time.time()
    q = _calls[ip]
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Hourly limit reached for the free demo. Try again later.")
    q.append(now)


def split_posts(text: str) -> list[str]:
    """Posts separated by a line with --- or by two or more blank lines.
    A CSV with a text/content/post column is also accepted."""
    t = text.strip()
    first = t.splitlines()[0].lower() if t else ""
    if "," in first and any(k in first for k in ("text", "content", "post", "caption", "body")):
        rows = list(csv.DictReader(io.StringIO(t)))
        col = next(c for c in rows[0] if c and c.lower() in ("text", "content", "post", "caption", "body", "full_text"))
        return [r[col] for r in rows if r.get(col)]
    if "\n---" in t:
        return [p.strip() for p in t.split("---") if p.strip()]
    return [p.strip() for p in re.split(r"\n\s*\n\s*\n", t) if p.strip()]


def _profile_payload(p: VoiceProfile) -> dict:
    return {"profile": p.to_dict(), "traits": describe(p), "signature_phrases": p.signature_phrases}


class ProfileIn(BaseModel):
    text: str = Field(..., description="Posts separated by --- lines or blank lines, or a CSV")
    name: str = "My voice"


class GenerateIn(BaseModel):
    profile: dict
    topic: str = Field(..., min_length=2, max_length=500)
    format: str = "x_post"
    notes: str = Field("", max_length=2000)


class TextIn(BaseModel):
    profile: dict
    text: str = Field(..., min_length=1, max_length=6000)


def _load(d: dict) -> VoiceProfile:
    try:
        return VoiceProfile.from_dict(d)
    except TypeError as e:
        raise HTTPException(400, f"Invalid voice profile: {e}")


@app.get("/api/health")
def health():
    return {"ok": True, "provider": llm.provider(), "model": llm.model_name()}


@app.get("/api/demo")
def demo():
    posts = split_posts((DEMO / "indie_maker.txt").read_text())
    p = build_profile(posts, "Demo: indie maker")
    return {**_profile_payload(p), "sample_ai_text": (DEMO / "chatgpt_sample.txt").read_text()}


@app.post("/api/profile")
def profile(body: ProfileIn):
    posts = split_posts(body.text)
    try:
        p = build_profile(posts[:200], body.name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return _profile_payload(p)


@app.post("/api/score")
def score(body: TextIn):
    return writer.score(body.text, _load(body.profile))


@app.post("/api/lint")
def lint(body: TextIn):
    return slop.report(body.text)


@app.post("/api/generate")
async def generate(body: GenerateIn, request: Request):
    _check_rate(request)
    try:
        return await writer.generate(_load(body.profile), body.topic, body.format, body.notes)
    except llm.LLMError as e:
        raise HTTPException(502, str(e))


@app.post("/api/humanize")
async def humanize(body: TextIn, request: Request):
    _check_rate(request)
    try:
        return await writer.humanize(_load(body.profile), body.text)
    except llm.LLMError as e:
        raise HTTPException(502, str(e))


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")
