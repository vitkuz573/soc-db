# ADR 0001: Record Architecture Decisions

## Status
Accepted

## Context
We need a consistent way to document architectural decisions made for SOC-DB,
so that contributors and future maintainers can understand why certain choices
were made.

## Decision
We will use Architecture Decision Records (ADRs), as described by Michael Nygard.

Each ADR will contain:
- **Title**: A short description
- **Status**: Proposed, Accepted, Deprecated, Superseded
- **Context**: What motivated the decision
- **Decision**: What was decided
- **Consequences**: What trade-offs were accepted

## Consequences
- ADRs are stored in `docs/adr/`
- Each ADR is numbered sequentially
- New ADRs can supersede old ones
