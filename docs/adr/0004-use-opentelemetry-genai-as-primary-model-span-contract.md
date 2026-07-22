# Use OpenTelemetry GenAI as the primary model span contract

Model-call spans in development trial observability v1 use OpenTelemetry GenAI attributes as the primary contract. The runtime may keep existing OpenInference constants already used for stable attributes, but it should not emit a full duplicate OpenInference token mapping in v1 because that would create competing dashboard and test contracts.
