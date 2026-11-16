"""Pure policy functions: risk scoring and disposition rules.

Holds ``scoring.py`` and ``disposition.py``, which take weights and thresholds
from ``config/scoring.yaml`` rather than literals. Called by the detection and
case-runner services and by graph nodes. Populated from M1 onward.
"""
