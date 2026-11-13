"""Buyer view (spec 006, ADR-014): logic that combines several domains.

Domains must not import each other (ADR-012). This layer sits between the entry points
(app, cli) and the domains: it may combine trade, shipping, markets and model results,
e.g. "which share of Europe's imports passes a disrupted chokepoint".
"""
