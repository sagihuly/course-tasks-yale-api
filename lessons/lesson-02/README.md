# Lesson 02 · Lease Intelligence Dashboard

This lesson extracts structured lease abstracts from the PDFs in
`sample_leases/`, writes them to `leases.json`, and displays the portfolio in
a futuristic black-and-blue Dash dashboard.

## Run locally

From this directory:

```bash
source .venv/bin/activate
python extract_leases.py
python app.py
```

Then open <http://127.0.0.1:8050>.

The extractor uses the OpenAI Python SDK with `gpt-5.6-luna` and Structured
Outputs. It reads `OPENAI_API_KEY` or the existing `PORTKEY_API_KEY` from the
project-root `.env`; the key is never committed. `leases.json` is the local
structured output consumed by the dashboard.
