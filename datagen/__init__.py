"""Synthetic data generation package.

Run through ``uv run seed`` (``datagen.cli:main``). It is the only process
that writes the truth database and the only caller of
``ensure_truth_collections``. Never imported by the API.
"""
