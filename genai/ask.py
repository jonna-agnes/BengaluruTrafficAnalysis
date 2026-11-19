"""Ask questions about the traffic data in plain English.

    python -m genai.ask "Which area is worst during the evening peak?"
    python -m genai.ask            # interactive chat (type 'exit' to quit)

Answers are grounded in the aggregates from genai.context (plus the latest
ML forecast), not in the model's general knowledge.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from genai.context import build_context
from genai.llm import LLMError, chat
from ml.features import REPO_ROOT

SYSTEM = """You are a helpful assistant for the Bengaluru Smart City traffic platform.
Answer ONLY using the data context below. Quote the relevant numbers. If the context
does not contain the answer, say so and suggest which data would be needed.
Keep answers short (under 150 words) unless asked for detail.

DATA CONTEXT:
{context}"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("question", nargs="*")
    p.add_argument("--data", type=Path, default=REPO_ROOT / "output" / "events")
    p.add_argument("--model", help="OpenRouter model id (overrides OPENROUTER_MODEL)")
    args = p.parse_args()

    messages = [{"role": "system", "content": SYSTEM.format(context=build_context(args.data))}]

    def ask(q: str) -> None:
        messages.append({"role": "user", "content": q})
        answer = chat(messages, model=args.model, max_tokens=2000)
        messages.append({"role": "assistant", "content": answer})
        print(f"\n{answer}\n")

    if args.question:
        ask(" ".join(args.question))
        return 0

    print("Bengaluru traffic assistant - ask a question ('exit' to quit).")
    while True:
        try:
            q = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if q.lower() in {"exit", "quit"}:
            break
        if q:
            try:
                ask(q)
            except LLMError as e:
                print(f"[error] {e}")
                messages.pop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
