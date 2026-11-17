"""Service layer: business use cases (system, detection, case runner, decision, report, evals).

Services receive repository ports and providers through their constructors.
Built by ``core.container`` and called by API routers and graph nodes. May
import the domain layer and repository interfaces only.
"""
