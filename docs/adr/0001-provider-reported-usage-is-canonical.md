# Provider-reported usage is canonical

For development trial observability, provider-reported model usage is the source of truth for token and cache fields. We leave missing numeric fields unset instead of estimating them locally, because mixed measured and inferred telemetry would make trial comparisons and budget analysis misleading.
