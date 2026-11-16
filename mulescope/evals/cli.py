"""``uv run evals`` entry point. The full harness arrives in phase 6."""

from __future__ import annotations

from backend.app.core.logging import configure_logging, get_logger
from backend.app.core.settings import EvalsSettings


def main() -> None:
    """Load evals settings and report that the harness is not built yet."""
    configure_logging()
    settings = EvalsSettings()
    get_logger(__name__).info(
        "eval harness not implemented yet", extra={"truth_db": settings.mongo_truth_db_name}
    )
