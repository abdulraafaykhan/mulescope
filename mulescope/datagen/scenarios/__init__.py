"""Planted scenarios: five parametrised classes configured by ``config/scenarios.yaml``.

Importing this package registers every scenario class. Called by
``datagen.cli`` during seeding; ground truth goes only to the truth database.
"""

from datagen.scenarios import ambiguous, dormant, group, mule, seller  # noqa: F401  (registration)
