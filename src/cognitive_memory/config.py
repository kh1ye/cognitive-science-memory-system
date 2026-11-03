from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryConfig:
    write_threshold: float = 0.42
    cpe_low_threshold: float = 0.55
    cpe_commit_threshold: float = 0.70
    evidence_consistency_threshold: float = 0.60
    minimum_evidence_count: int = 2
    retention_threshold: float = 0.30
    retention_decay: float = 0.04
    retrieval_lambda_bias: float = 0.65
    retrieval_delta_context: float = 0.45
    retrieval_retention_weight: float = 0.15  # Maximum fraction discounted by decay.
    retention_importance_threshold: float = 0.80  # Protect important untagged facts.
