"""LLM providers: provider interface, Groq, Gemini, template fallback, cache and rate limiter.

Every provider is substitutable behind the ``LLMProvider`` interface. Built by
``core.container`` and used by agents. Populated from M4 onward.
"""
