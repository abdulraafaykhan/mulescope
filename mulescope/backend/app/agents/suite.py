"""The set of agents a run uses, and the factory that picks template or live.

In fallback mode every agent is its template. In live mode each agent whose
provider has an API key is the live LLM version (which itself falls back to
the template per call); an agent whose provider has no key stays template.
``prompt_versions`` / ``models`` are stamped on every ``case_runs`` row.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.agents.critic import PROMPT_VERSION as CRITIC_TEMPLATE
from backend.app.agents.critic import TemplateCritic
from backend.app.agents.flow_analyst import PROMPT_VERSION as FLOW_TEMPLATE
from backend.app.agents.flow_analyst import TemplateFlowAnalyst
from backend.app.agents.live_investigators import LiveFlowAnalyst, LiveProfiler
from backend.app.agents.live_writers import LiveCritic, LiveNarrativeWriter
from backend.app.agents.narrative import PROMPT_VERSION as NARRATIVE_TEMPLATE
from backend.app.agents.narrative import TemplateNarrativeWriter
from backend.app.agents.profiler import PROMPT_VERSION as PROFILER_TEMPLATE
from backend.app.agents.profiler import TemplateProfiler
from backend.app.core.config_files import LlmConfig
from backend.app.llm.client import LlmClient


@dataclass
class AgentSuite:
    """Profiler, Flow Analyst, Narrative Writer and Critic."""

    profiler: Any = field(default_factory=TemplateProfiler)
    flow_analyst: Any = field(default_factory=TemplateFlowAnalyst)
    narrative: Any = field(default_factory=TemplateNarrativeWriter)
    critic: Any = field(default_factory=TemplateCritic)
    prompt_versions: dict[str, str] = field(default_factory=lambda: {"profiler": PROFILER_TEMPLATE, "flow_analyst": FLOW_TEMPLATE, "narrative": NARRATIVE_TEMPLATE, "critic": CRITIC_TEMPLATE})
    models: dict[str, str] = field(default_factory=lambda: {"profiler": "template", "flow_analyst": "template", "narrative": "template", "critic": "template"})
    client: LlmClient | None = None

    async def aclose(self) -> None:
        """Close the provider HTTP clients (live mode)."""
        if self.client is not None:
            await self.client.aclose()


def build_live_suite(client: LlmClient, cfg: LlmConfig, str_sections: list[str], tipping_terms: list[str]) -> AgentSuite:
    """Live agents for every provider that is configured; template for the rest."""
    suite = AgentSuite(client=client)
    a = cfg.agents
    if client.has(a.profiler.provider.value):
        suite.profiler = LiveProfiler(client, a.profiler)
        suite.prompt_versions["profiler"], suite.models["profiler"] = suite.profiler.prompt_version, a.profiler.model
    if client.has(a.flow_analyst.provider.value):
        suite.flow_analyst = LiveFlowAnalyst(client, a.flow_analyst)
        suite.prompt_versions["flow_analyst"], suite.models["flow_analyst"] = suite.flow_analyst.prompt_version, a.flow_analyst.model
    if client.has(a.narrative_writer.provider.value):
        suite.narrative = LiveNarrativeWriter(client, a.narrative_writer, str_sections, tipping_terms)
        suite.prompt_versions["narrative"], suite.models["narrative"] = suite.narrative.prompt_version, a.narrative_writer.model
    if client.has(a.critic.provider.value):
        suite.critic = LiveCritic(client, a.critic)
        suite.prompt_versions["critic"], suite.models["critic"] = suite.critic.prompt_version, a.critic.model
    return suite
