"""Benchmark: does VoiceClone beat plain prompting at sounding like the creator?

Holds out the creator's last posts, builds a voice from the rest, then writes a
post for each held-out topic two ways with the same Gemma model:
  baseline   - "Write an X post about <topic>"
  voiceclone - retrieval + voice traits + best-of-N rerank
and reports average Voice Match and Slop.

    GEMINI_API_KEY=... python -m eval.benchmark            # real Gemma
    LLM_PROVIDER=mock python -m eval.benchmark             # pipeline check
"""

import asyncio
import json
import statistics
import sys
from pathlib import Path

from app import llm, slop
from app.main import split_posts
from app.stylometry import build_profile, voice_match
from app.writer import generate

DEMO = Path(__file__).parent.parent / "app" / "demo" / "indie_maker.txt"
TOPICS = [
    "taking a weekend off from my startup",
    "why I stopped offering a free plan",
    "what my first 100 users taught me",
    "a feature I removed and nobody missed",
    "dealing with a nasty customer email",
    "why I answer support myself",
    "launching something nobody signed up for",
    "the tool I pay for that's worth every cent",
]


async def main(n_held_out: int = 5):
    posts = split_posts(DEMO.read_text())
    profile = build_profile(posts[:-n_held_out], "benchmark")
    rows = []
    for topic in TOPICS:
        base = (await llm.complete(f"Write an X (Twitter) post about: {topic}\nOutput only the post.", 0.9)).strip()
        vc = (await generate(profile, topic, "x_post"))["drafts"][0]["text"]
        rows.append({
            "topic": topic,
            "baseline": {"text": base, "voice": voice_match(base, profile), "slop": slop.slop_score(base)},
            "voiceclone": {"text": vc, "voice": voice_match(vc, profile), "slop": slop.slop_score(vc)},
        })
    held = [voice_match(p, profile) for p in posts[-n_held_out:]]
    summary = {
        "model": llm.model_name(),
        "real_posts_voice": round(statistics.mean(held), 1),
        "baseline_voice": round(statistics.mean(r["baseline"]["voice"] for r in rows), 1),
        "voiceclone_voice": round(statistics.mean(r["voiceclone"]["voice"] for r in rows), 1),
        "baseline_slop": round(statistics.mean(r["baseline"]["slop"] for r in rows), 1),
        "voiceclone_slop": round(statistics.mean(r["voiceclone"]["slop"] for r in rows), 1),
    }
    out = Path(__file__).parent / "results.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False))
    print("| | Voice Match (higher is better) | Slop (lower is better) |")
    print("|---|---|---|")
    print(f"| Creator's real held-out posts | {summary['real_posts_voice']} | - |")
    print(f"| Plain prompt ({summary['model']}) | {summary['baseline_voice']} | {summary['baseline_slop']} |")
    print(f"| VoiceClone ({summary['model']}) | {summary['voiceclone_voice']} | {summary['voiceclone_slop']} |")
    print(f"\nFull results: {out}", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
