"""Unit tests for ``backend.app.core.config_files``.

Loads the real ``config/llm.yaml`` and uses ``tmp_path`` for missing and
invalid files.

**Validates: Requirements 3.6, 3.7**
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.config_files import (
    LLM_CONFIG_FILENAME,
    LlmConfig,
    LlmProvider,
    load_llm_config,
)
from backend.app.core.errors import DependencyUnavailable
from backend.app.core.settings import CONFIG_DIR

pytestmark = pytest.mark.unit


def test_loads_placeholder_llm_yaml() -> None:
    config = load_llm_config(CONFIG_DIR)
    assert isinstance(config, LlmConfig)
    assert config.version
    assert config.agents.narrative_writer.provider is LlmProvider.GEMINI
    assert config.agents.profiler.provider is LlmProvider.GROQ
    assert config.cache_ttl_seconds == config.cache.ttl_days * 86400


def test_missing_file_raises_dependency_unavailable(tmp_path: Path) -> None:
    with pytest.raises(DependencyUnavailable) as info:
        load_llm_config(tmp_path)
    assert LLM_CONFIG_FILENAME in info.value.message
    assert info.value.detail == {"path": str(tmp_path / LLM_CONFIG_FILENAME)}


@pytest.mark.parametrize(
    "content",
    [
        "version: [unclosed",  # invalid YAML
        "- just\n- a list\n",  # not a mapping
        'version: "0.1.0"\n',  # missing required sections
    ],
    ids=["bad-yaml", "not-mapping", "schema-mismatch"],
)
def test_invalid_file_raises_dependency_unavailable(tmp_path: Path, content: str) -> None:
    (tmp_path / LLM_CONFIG_FILENAME).write_text(content, encoding="utf-8")
    with pytest.raises(DependencyUnavailable):
        load_llm_config(tmp_path)


def test_unknown_key_rejected(tmp_path: Path) -> None:
    text = (CONFIG_DIR / LLM_CONFIG_FILENAME).read_text(encoding="utf-8")
    (tmp_path / LLM_CONFIG_FILENAME).write_text(text + "\nunexpected: 1\n", encoding="utf-8")
    with pytest.raises(DependencyUnavailable):
        load_llm_config(tmp_path)
