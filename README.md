# VoiceClone Writer

**Posts that sound like you, not like ChatGPT.**

Paste your old posts. VoiceClone learns your writing fingerprint, writes new drafts with open-source **Gemma**, and scores every draft on how much it sounds like you, highlighting the phrases that give AI away.

Built for the DEV Hacktoberfest 2026 Open-Source AI Challenge, Week 2 ("Side Hustle"), started Oct 17, 2026.

## How it works

1. **Voice fingerprint (stylometry).** ~70 features per post: function-word frequencies (the classic authorship-attribution signal), sentence length mean and variance ("burstiness"), word length, vocabulary richness, line breaks, punctuation, emoji, casing, contractions, plus a character 3-gram TF-IDF centroid. The profile stores the mean and spread across your posts.
2. **Voice Match score (0-100).** Distance of a text from your profile, calibrated with leave-one-out: each of your own posts is scored against a profile built from your other posts, so 85+ means "reads like an unseen post of yours".
3. **Retrieval.** Your posts closest to the new topic become the examples in the prompt.
4. **Generation with Gemma.** Four drafts at different temperatures (`gemma-4-31b-it` via the Gemini API, or local Gemma via Ollama).
5. **Best-of-N rerank.** Drafts are ranked by Voice Match minus a slop penalty.
6. **Slop linter.** ~30 rules for AI tells ("delve", "in today's fast-paced world", "it's not X, it's Y", emoji bullet lists, em-dash overuse, generic CTAs). "Fix flagged parts" rewrites in your voice.
7. **Personal fine-tune (Tinker).** `finetune/tinker_sft.py` LoRA-tunes an open model on one creator's posts and reports base vs tuned Voice Match.

Your posts stay in your browser (localStorage, exportable as JSON). The server is stateless.

## Run locally

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env               # then add GEMINI_API_KEY from https://aistudio.google.com/apikey
uvicorn app.main:app --reload        # http://localhost:8000
```

Without a key the app runs on a built-in mock model (`LLM_PROVIDER=mock`), so the UI and scoring work offline. For fully local Gemma: `ollama pull gemma3:4b` then `LLM_PROVIDER=ollama`.

Tests: `pytest -q`. Benchmark (plain Gemma prompt vs VoiceClone): `python -m eval.benchmark`.

## Deploy

One Render web service from `render.yaml`. Set `GEMINI_API_KEY` in the Render dashboard.

## API

| Method | Path | Body |
|---|---|---|
| POST | `/api/profile` | `{text, name}`: posts separated by `---` lines, blank lines, or a CSV with a `text` column |
| POST | `/api/generate` | `{profile, topic, format, notes}` with format `x_post`, `thread`, `linkedin`, `caption` or `newsletter` |
| POST | `/api/score` | `{profile, text}` |
| POST | `/api/humanize` | `{profile, text}` |
| GET | `/api/demo` | demo voice |

The demo voice in `app/demo/` is a set of sample posts written for this project, not a real person's.

## License

MIT
