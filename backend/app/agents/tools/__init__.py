"""Read-only tools exposed to agents over narrow query ports.

Examples: ``get_account_profile``, ``get_flow_metrics``, ``get_counterparties``.
Tools never receive a raw database handle and can never read ``ground_truth``.
Bound to agents by graph nodes. Populated from M4 onward.
"""
