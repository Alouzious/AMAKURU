# ADR 0001: Modular monolith

## Status

Accepted - 12 November 2026

## Context

Amakuru needs clear boundaries (identity, tenancy, knowledge, retrieval, channels) but must run affordably on one small VPS for many universities.

## Decision

Ship a single FastAPI deployable with strict internal module boundaries and typed service interfaces. Extract services only when scale or tenancy demands it. Use one Postgres (with pgvector) and one Redis.

## Consequences

- Simpler operations and lower cost for early customers
- Requires discipline so modules never reach into each other's tables
- Vector store and LLM sit behind interfaces so they can be swapped later
