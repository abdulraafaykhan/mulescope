"""Closed value sets shared across MuleScope layers.

Every closed set in the system is a ``StrEnum`` defined here, so values stored
in MongoDB, returned by the API and used in policy code come from one place.
This module is pure domain code: it imports only the standard library and is
safe to import from any layer (core, services, graph, api, datagen, evals).

Members are limited to values the build prompt names explicitly. Sets whose
members are not yet specified (``AlertStatus``, ``CaseStatus``) are declared
empty and are filled in by the milestone that implements the entity.
"""

from enum import StrEnum, unique


@unique
class LlmMode(StrEnum):
    """How agent nodes obtain LLM output.

    Attributes:
        LIVE: Call the configured free-tier providers (Groq, Gemini).
        FALLBACK: Use the deterministic template provider only, no network.
    """

    LIVE = "live"
    FALLBACK = "fallback"


@unique
class HealthState(StrEnum):
    """Health of the service or one of its dependencies.

    Attributes:
        OK: The component responded normally.
        UNAVAILABLE: The component could not be reached or failed its check.
    """

    OK = "ok"
    UNAVAILABLE = "unavailable"


@unique
class Disposition(StrEnum):
    """Outcome produced by the deterministic disposition policy.

    Attributes:
        CLOSE: No further action; the alert is closed with a recorded reason.
        ESCALATE: Needs human follow-up such as clarification or monitoring.
        STR_DRAFT: Draft a Suspicious Transaction Report for maker-checker review.
    """

    CLOSE = "close"
    ESCALATE = "escalate"
    STR_DRAFT = "str_draft"


@unique
class Channel(StrEnum):
    """Payment channel of a ledger entry.

    Attributes:
        UPI: Unified Payments Interface transfer.
        IMPS: Immediate Payment Service transfer.
        NEFT: National Electronic Funds Transfer.
        RTGS: Real Time Gross Settlement transfer.
        ATM: Cash withdrawal at an ATM.
        CARD_POS: Card payment at a point-of-sale terminal.
        WALLET_LOAD: Load of a prepaid wallet.
    """

    UPI = "upi"
    IMPS = "imps"
    NEFT = "neft"
    RTGS = "rtgs"
    ATM = "atm"
    CARD_POS = "card_pos"
    WALLET_LOAD = "wallet_load"
    CASH_DEPOSIT = "cash_deposit"


@unique
class ActionType(StrEnum):
    """Action types named by the action playbook (build prompt section 8.4).

    The playbook in ``config/playbook.yaml`` maps dispositions and signals to
    these types; execution is mocked by writing to the database.
    """

    RECORD_CLOSURE_REASON = "record_closure_reason"
    SUPPRESS_SIMILAR_ALERTS = "suppress_similar_alerts"
    STORE_FEEDBACK = "store_feedback"
    REQUEST_CUSTOMER_CLARIFICATION = "request_customer_clarification"
    ENHANCED_MONITORING = "enhanced_monitoring"
    SENIOR_REVIEW = "senior_review"
    REFRESH_KYC = "refresh_kyc"
    SOFT_LIMIT_REDUCTION = "soft_limit_reduction"
    TEMPORARY_DEBIT_HOLD = "temporary_debit_hold"
    CREATE_STR_DRAFT = "create_str_draft"
    PRESERVE_EVIDENCE = "preserve_evidence"
    RELATIONSHIP_REVIEW = "relationship_review"
    FLAG_LINKED_ACCOUNTS = "flag_linked_accounts"
    NOTIFY_FRAUD_OPS = "notify_fraud_ops"
    CHECK_LINKED_WALLETS = "check_linked_wallets"


@unique
class AlertStatus(StrEnum):
    """Lifecycle status of a detector alert."""

    OPEN = "open"
    IN_CASE = "in_case"
    CLOSED = "closed"


@unique
class CaseStatus(StrEnum):
    """Lifecycle status of an investigation case.

    ``returned`` means the analyst rejected the recommendation; the case needs
    a new run.
    """

    NEW = "new"
    INVESTIGATING = "investigating"
    AWAITING_DECISION = "awaiting_decision"
    CLOSED = "closed"
    ESCALATED = "escalated"
    STR_DRAFTED = "str_drafted"
    RETURNED = "returned"


@unique
class Direction(StrEnum):
    """Side of a ledger entry."""

    CREDIT = "credit"
    DEBIT = "debit"


@unique
class IdPrefix(StrEnum):
    """Prefixes of readable string ``_id`` values for business entities.

    High-volume append-only collections (transactions, audit logs, node
    executions) use ObjectId instead and have no prefix.

    Attributes:
        CUSTOMER: ``customers`` collection.
        ACCOUNT: ``accounts`` collection.
        COUNTERPARTY: ``counterparties`` collection.
        COMPLAINT: ``complaints`` collection.
        USER: ``users`` collection.
        ALERT: ``alerts`` collection.
        CASE: ``cases`` collection.
        CASE_RUN: ``case_runs`` collection.
        EVIDENCE: ``evidence`` collection.
        REPORT: ``reports`` collection.
        ACTION: ``actions`` collection.
        DECISION: ``decisions`` collection.
    """

    CUSTOMER = "CUS-"
    ACCOUNT = "ACC-"
    COUNTERPARTY = "CPY-"
    COMPLAINT = "CMP-"
    USER = "USR-"
    ALERT = "ALT-"
    CASE = "CASE-"
    CASE_RUN = "RUN-"
    EVIDENCE = "EVD-"
    REPORT = "RPT-"
    ACTION = "ACT-"
    DECISION = "DEC-"
