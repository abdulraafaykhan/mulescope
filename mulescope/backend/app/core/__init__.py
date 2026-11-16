"""Cross-cutting infrastructure: settings, composition root, logging, errors, clock.

``container.py`` is the composition root and may import every layer. The other
modules are imported by ``main.py``, the API layer, services and the ``datagen``
and ``evals`` CLIs for configuration, structured logging, the ``DomainError``
hierarchy and the single time source.
"""
