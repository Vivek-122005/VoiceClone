"""Personal voice fine-tune on Tinker (LoRA), with a before/after evaluation.

Trains a LoRA adapter on one creator's posts (topic -> post pairs), then writes
posts for held-out topics with the base model and with the tuned adapter, and
scores both with VoiceClone's Voice Match and Slop metrics.

    pip install tinker
    TINKER_API_KEY=... python -m finetune.tinker_sft --posts app/demo/indie_maker.txt

Gemma is not in Tinker's model list, so this uses an open Qwen model; the app
itself keeps using Gemma for generation.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
import statistics
from pathlib import Path

import tinker
from tinker import types

from app import slop
from app.main import split_posts
from app.stylometry import FUNCTION_WORDS, build_profile, voice_match, words

PROMPT = "Write a social media post in my voice.\nTopic: {topic}\nPost:\n"


def topic_of(post: str) -> str:
    """Cheap topic label: the post's most content-bearing words, in order."""
    ws = [w for w in words(post) if w not in FUNCTION_WORDS and len(w) > 3]
    return " ".join(list(dict.fromkeys(ws))[:6]) or post[:40]


def make_datum(tok, prompt: str, completion: str) -> types.Datum:
    p = tok.encode(prompt)
    c = tok.encode(completion) + [tok.eos_token_id]
    ids = p + c
    cut = len(p) - 1
    return types.Datum(
        model_input=types.ModelInput.from_ints(tokens=ids[:-1]),
        loss_fn_inputs=dict(weights=[0.0] * cut + [1.0] * len(c), target_tokens=ids[1:]),
    )


async def sample_all(sampler, tok, topics: list[str]) -> list[str]:
    params = types.SamplingParams(max_tokens=160, temperature=0.8, stop=["\nTopic:", "\n---"])

    async def one(t: str) -> str:
        prompt = types.ModelInput.from_ints(tok.encode(PROMPT.format(topic=t)))
        out = await sampler.sample_async(prompt=prompt, num_samples=1, sampling_params=params)
        text = tok.decode(out.sequences[0].tokens)
        return re.sub(r"<\|.*?\|>", "", text).strip()

    return await asyncio.gather(*(one(t) for t in topics))


def evaluate(texts: list[str], profile) -> dict:
    return {
        "voice_match": round(statistics.mean(voice_match(t, profile) for t in texts), 1),
        "slop": round(statistics.mean(slop.slop_score(t) for t in texts), 1),
    }


async def main(args):
    posts = split_posts(Path(args.posts).read_text())
    random.Random(0).shuffle(posts)
    held, train_posts = posts[: args.held_out], posts[args.held_out :]
    profile = build_profile(train_posts, "tinker-eval")
    held_topics = [topic_of(p) for p in held]

    service = tinker.ServiceClient()
    trainer = service.create_lora_training_client(base_model=args.model, rank=args.rank)
    tok = trainer.get_tokenizer()

    base_sampler = trainer.save_weights_and_get_sampling_client(name="voice-base")
    base_texts = await sample_all(base_sampler, tok, held_topics)

    data = [make_datum(tok, PROMPT.format(topic=topic_of(p)), p) for p in train_posts]
    for epoch in range(args.epochs):
        random.Random(epoch).shuffle(data)
        losses = []
        for i in range(0, len(data), args.batch):
            fwd = await trainer.forward_backward_async(data=data[i : i + args.batch], loss_fn="cross_entropy")
            opt = await trainer.optim_step_async(types.AdamParams(learning_rate=args.lr))
            res = await fwd.result_async()
            await opt.result_async()
            losses.append(res.loss)
        print(f"epoch {epoch + 1}: loss {statistics.mean(losses):.4f}")

    tuned_sampler = trainer.save_weights_and_get_sampling_client(name="voice-tuned")
    tuned_texts = await sample_all(tuned_sampler, tok, held_topics)

    result = {
        "model": args.model,
        "train_posts": len(train_posts),
        "held_out": len(held),
        "real_posts": evaluate(held, profile),
        "base": evaluate(base_texts, profile),
        "tuned": evaluate(tuned_texts, profile),
        "samples": [
            {"topic": t, "real": r, "base": b, "tuned": u}
            for t, r, b, u in zip(held_topics, held, base_texts, tuned_texts)
        ],
    }
    out = Path(__file__).parent / "results.json"
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print("| | Voice Match | Slop |\n|---|---|---|")
    for k, label in (("real_posts", "Real held-out posts"), ("base", f"{args.model} base"), ("tuned", f"{args.model} + LoRA")):
        print(f"| {label} | {result[k]['voice_match']} | {result[k]['slop']} |")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--posts", default="app/demo/indie_maker.txt")
    ap.add_argument("--model", default="Qwen/Qwen3-8B")
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--held-out", type=int, default=5)
    asyncio.run(main(ap.parse_args()))
