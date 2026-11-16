"""The set of agents a run uses. Phase 3 wires the template agents; the live
LLM agents (phase 4) are drop-in replacements with the same ``run`` methods.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.app.agents.critic import TemplateCritic
from backend.app.agents.flow_analyst import TemplateFlowAnalyst
from backend.app.agents.narrative import TemplateNarrativeWriter
from backend.app.agents.profiler import TemplateProfiler


@dataclass
class AgentSuite:
    """Profiler, Flow Analyst, Narrative Writer and Critic."""

    profiler: TemplateProfiler = field(default_factory=TemplateProfiler)
    flow_analyst: TemplateFlowAnalyst = field(default_factory=TemplateFlowAnalyst)
    narrative: TemplateNarrativeWriter = field(default_factory=TemplateNarrativeWriter)
    critic: TemplateCritic = field(default_factory=TemplateCritic)
