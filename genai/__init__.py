"""GenAI layer (OpenRouter LLM) on top of the traffic pipeline and ML forecasts."""
import sys

# Windows consoles default to cp1252; LLM output often contains arrows, dashes, etc.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
