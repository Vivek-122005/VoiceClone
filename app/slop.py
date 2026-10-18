"""Slop linter: flags the phrases and patterns that make text read as AI-written."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# (pattern, label, weight). Weights roughly track how strongly readers
# associate the pattern with LLM output.
RULES: list[tuple[str, str, int]] = [
    (r"\bdelv(e|es|ing)\b", "AI-favourite word: delve", 3),
    (r"\btapestry\b", "AI-favourite word: tapestry", 3),
    (r"\btestament to\b", "Cliché: a testament to", 2),
    (r"\b(realm|landscape) of\b", "Vague framing: the realm/landscape of", 2),
    (r"\bin today'?s ((fast-paced|digital|ever-changing|modern|competitive) ){1,2}(world|age|landscape|era)\b", "Generic opener: in today's fast-paced world", 3),
    (r"\bever-(evolving|changing)\b", "Cliché: ever-evolving", 2),
    (r"\b(unlock|unleash|elevate|supercharge|harness) (the|your)\b", "Hype verb: unlock/unleash/elevate", 2),
    (r"\bgame[- ]changer\b", "Cliché: game-changer", 2),
    (r"\bseamless(ly)?\b", "Corporate word: seamless", 1),
    (r"\brobust\b", "Corporate word: robust", 1),
    (r"\bleverag(e|ing)\b", "Corporate word: leverage", 1),
    (r"\bpivotal\b", "AI-favourite word: pivotal", 2),
    (r"\bmeticulous(ly)?\b", "AI-favourite word: meticulous", 2),
    (r"\bembark(ing)? on\b", "Cliché: embark on", 2),
    (r"\bnavigat(e|ing) the (complexities|world|challenges)\b", "Cliché: navigate the complexities", 2),
    (r"\bit'?s (important|worth|crucial) to (note|remember|mention)\b", "Hedge: it's important to note", 2),
    (r"\bin conclusion\b", "Essay wrap-up: in conclusion", 2),
    (r"\b(moreover|furthermore|additionally)\b", "Formal connector: moreover/furthermore", 1),
    (r"\bnot just [^.?!\n]{1,40}, (but|it'?s)\b", "Pattern: not just X, but Y", 2),
    (r"\bit'?s not (about )?[^.?!\n]{1,30}[,.;—-]+ it'?s\b", "Pattern: it's not X, it's Y", 3),
    (r"\bhere'?s the (thing|kicker|truth)\b", "Hook cliché: here's the thing", 1),
    (r"\b(let that sink in|read that again)\b", "Hook cliché: let that sink in", 2),
    (r"\bwhat do you think\?\s*$", "Generic CTA: what do you think?", 1),
    (r"\b(thoughts|agree)\?\s*$", "Generic CTA: thoughts?", 1),
    (r"\bi hope this (helps|finds you)\b", "Assistant voice: I hope this helps", 3),
    (r"\b(certainly|absolutely)!", "Assistant voice: Certainly!", 3),
    (r"\bas an ai\b", "Assistant voice: as an AI", 5),
    (r"^\s*[\U0001F300-\U0001FAFF✅✨]\s", "Emoji bullet list", 1),
    (r"\b(\w+), (\w+),? and (\w+)\b[^.?!\n]{0,20}\.", "Rule-of-three list", 1),
]

_COMPILED = [(re.compile(p, re.IGNORECASE | re.MULTILINE), label, w) for p, label, w in RULES]


@dataclass
class Flag:
    start: int
    end: int
    text: str
    label: str
    weight: int


def lint(text: str) -> list[Flag]:
    flags: list[Flag] = []
    for rx, label, w in _COMPILED:
        for m in rx.finditer(text):
            flags.append(Flag(m.start(), m.end(), m.group(0), label, w))
    em = text.count("—")
    words = max(len(text.split()), 1)
    if em and em * 100 / words > 1.0:
        for m in re.finditer("—", text):
            flags.append(Flag(m.start(), m.end(), "—", "Em-dash overuse", 1))
    flags.sort(key=lambda f: f.start)
    return flags


def slop_score(text: str, flags: list[Flag] | None = None) -> int:
    """0 = clean, 100 = unmistakably AI. Weighted hits per 100 words."""
    flags = lint(text) if flags is None else flags
    words = max(len(text.split()), 1)
    density = sum(f.weight for f in flags) * 100 / words
    return int(min(100, round(density * 12)))


def report(text: str) -> dict:
    flags = lint(text)
    return {"slop": slop_score(text, flags), "flags": [asdict(f) for f in flags]}
