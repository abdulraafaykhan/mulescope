"""Risk signals and mitigators. Importing this package registers all of them.

Used by ``domain/policy/scoring.py``; add a signal by creating a function with
``@register_signal`` and a matching entry in ``config/scoring.yaml``.
"""

from backend.app.domain.signals import mitigators, risk_signals  # noqa: F401  (registration)
