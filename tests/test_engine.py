import asyncio
from pathlib import Path

from app import slop
from app.stylometry import build_profile, voice_match, VoiceProfile
from app.writer import generate, humanize

DEMO = Path(__file__).parent.parent / "app" / "demo"


def load(name):
    return [p.strip() for p in (DEMO / name).read_text().split("---") if p.strip()]


INDIE = load("indie_maker.txt")
CHATGPT = (DEMO / "chatgpt_sample.txt").read_text()

COACH = [
    "GOOD MORNING TEAM!! 🔥💪 Leg day is the best day and I will not be taking questions. Who's training with me today?! #fitfam #legday",
    "Your body can do it. It's your MIND you have to convince!! 🧠💪 Showed up at 5am today even though I wanted to sleep. Proud of that. #motivation",
    "Meal prep Sunday! 🥗🍗 Chicken, rice, broccoli, repeat. Is it exciting? No! Does it work? ABSOLUTELY!! #mealprep #gains",
    "Reminder: progress is NOT linear!! 📈 Some weeks the scale goes up. Keep showing up and trust the process 🙌 #fitnessjourney",
    "New PR on deadlift today!!! 🏋️‍♀️ 140kg!! Six months ago I couldn't lift 80. Consistency is EVERYTHING 💯 #strongwomen",
    "Water. Sleep. Protein. Movement. That's the secret!! 💧😴🍳🏃 Stop looking for shortcuts and nail the basics!! #healthtips",
    "Client win of the week!! 🎉 Sarah dropped 8kg and ran her first 10k!! SO proud of you girl 😭❤️ #clientwins",
    "Rest days are part of the plan!! 🛋️ Your muscles grow when you RECOVER, not when you train. Take the day!! #recovery",
]


def test_profile_traits():
    p = build_profile(INDIE, "indie")
    assert p.n_posts == len(INDIE)
    assert p.style_mean["lowercase_start_ratio"] > 0.5
    assert p.style_mean["emoji_per_100w"] < 0.2


def test_voice_match_separates_voices():
    p = build_profile(INDIE[:-4], "indie")
    own = [voice_match(t, p) for t in INDIE[-4:]]
    other = [voice_match(t, p) for t in COACH[:4]] + [voice_match(CHATGPT, p)]
    assert min(own) > max(other), (own, other)
    assert sum(own) / len(own) >= 60
    assert max(other) <= 40


def test_profile_roundtrip():
    p = build_profile(INDIE, "indie")
    q = VoiceProfile.from_dict(p.to_dict())
    assert voice_match(INDIE[0], q) == voice_match(INDIE[0], p)


def test_slop_flags_chatgpt_not_human():
    assert slop.slop_score(CHATGPT) >= 60
    labels = {f.label for f in slop.lint(CHATGPT)}
    assert any("fast-paced" in l for l in labels)
    assert sum(slop.slop_score(t) for t in INDIE) / len(INDIE) < 10


def test_generate_and_humanize_with_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    p = build_profile(INDIE, "indie")
    out = asyncio.run(generate(p, "pricing my product", "x_post"))
    assert out["drafts"]
    ranks = [d["rank_score"] for d in out["drafts"]]
    assert ranks == sorted(ranks, reverse=True)
    h = asyncio.run(humanize(p, CHATGPT))
    assert h["after"]["slop"] < h["before"]["slop"]
