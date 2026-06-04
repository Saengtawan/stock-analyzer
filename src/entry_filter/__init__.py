"""Entry filter v1 — rule-based per-zone selection filter for ml_filter.

Applied AFTER ML threshold gate, BEFORE top-1 selection.
Spec: backtests/entry_filter_v1/spec.json

Public API: from src.entry_filter.rules import evaluate, zone_of_mfo
"""
