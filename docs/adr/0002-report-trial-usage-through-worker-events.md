# Report provider usage through worker events

Development trial JSONL results should receive provider usage through bounded worker protocol events. A dedicated `usage.snapshot` event keeps terminal events focused on run lifecycle, preserves protocol validation as the safety boundary, and works across direct worker and internal HTTP experiment targets. The event carries cumulative totals plus a model usage breakdown grouped by provider, model, graph id, and node name so trials can attribute usage across LangGraph nodes.
