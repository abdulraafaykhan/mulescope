"""Versioned prompt files, one per agent (``<agent>.v<N>.md``).

The prompt version stored on runs, node executions and cache keys is the file
stem, for example ``profiler.v1``. Changing a prompt means adding a new file
and pointing ``PROMPTS`` at it, so old runs stay reproducible.
"""

from __future__ import annotations

from functools import cache
from pathlib import Path

PROMPT_DIR = Path(__file__).parent
PROMPTS = {
    "profiler": "profiler.v1",
    "flow_analyst": "flow_analyst.v1",
    "narrative_writer": "narrative.v1",
    "critic": "critic.v1",
}


@cache
def load_prompt(agent: str) -> tuple[str, str]:
    """Return ``(version, text)`` of the active prompt for ``agent``.

    Raises:
        KeyError: Unknown agent.
        FileNotFoundError: The prompt file is missing.
    """
    version = PROMPTS[agent]
    return version, (PROMPT_DIR / f"{version}.md").read_text(encoding="utf-8")
