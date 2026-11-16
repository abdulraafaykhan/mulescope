"""Detection signals: one module per signal plus the signal registry.

Signals are pure functions over typed inputs, registered with
``@register_signal`` so new signals are added without editing existing code.
Called by the detection service. Populated from M1 onward.
"""
