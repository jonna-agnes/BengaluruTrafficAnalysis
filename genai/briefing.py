"""Generate an LLM-written traffic operations briefing (Markdown).

    python -m genai.briefing --data output/events

Combines pipeline aggregates + ML forecasts (genai.context) and asks the LLM
for a concise briefing for a city traffic-control room.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from genai.context import build_context
from genai.llm import chat
from ml.features import REPO_ROOT

SYSTEM = """You are a senior traffic analyst for the Bengaluru Traffic Control Room.
Write ONLY from the facts in the provided context. Never invent numbers, roads or
events. If something is not in the context, say it is not available. Mention once
that the data is synthetic. Be concise and actionable."""

PROMPT = """Using the context below, write a Markdown traffic briefing with these sections:

## Executive summary
3-4 bullet points.
## Hotspots
Worst areas and road segments, with the supporting numbers.
## Peak hours
When congestion peaks on weekdays and which areas are hit hardest.
## Weather & incidents
How rain and incidents affect speed and congestion.
## Next 30 minutes (ML forecast)
Segments forecast to be High/Severe or worsening; mention model accuracy vs baseline.
## Recommended actions
4-6 concrete, prioritised actions (signal timing, diversions, deployment of
traffic police, commuter advisories), each tied to a finding above.

CONTEXT:
{context}"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--data", type=Path, default=REPO_ROOT / "output" / "events")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "output" / "reports" / "traffic_briefing.md")
    p.add_argument("--model", help="OpenRouter model id (overrides OPENROUTER_MODEL)")
    args = p.parse_args()

    context = build_context(args.data)
    report = chat([{"role": "system", "content": SYSTEM},
                   {"role": "user", "content": PROMPT.format(context=context)}],
                  model=args.model, max_tokens=6000)

    header = f"# Bengaluru Traffic Briefing\n_Generated {datetime.now():%Y-%m-%d %H:%M}_\n\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(header + report + "\n", encoding="utf-8")
    print(header + report)
    print(f"\nsaved -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
