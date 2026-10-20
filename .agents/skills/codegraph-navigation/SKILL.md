---
name: codegraph-navigation
description: Guidance on using CodeGraph MCP and repository indexing for rapid code exploration, symbol navigation, and dependency tracking in large codebases. Use when exploring architecture, locating callers, or analyzing dynamic-dispatch hops without manual grepping.
---

# CodeGraph Navigation Skill

## Purpose
Enables developers and AI agents to efficiently navigate symbol call paths, class hierarchies, and cross-module dependencies using CodeGraph without searching files blindly.

## Usage Guidelines
1. **Repository Indexing**:
   - In projects where CodeGraph is enabled, index the repository by running:
     ```bash
     codegraph init
     ```
     or creating the `.codegraph/` directory.
2. **Explore Symbols Before Grepping**:
   - Instead of running generic text search, ask CodeGraph directly:
     ```bash
     codegraph explore "Orchestrator select_model"
     ```
   - In AI tools supporting the MCP tool, call `codegraph_explore` with the symbol name.
3. **Cross-Module Verification**:
   - Before modifying interfaces in `backend/app/contracts/`:
     - Explore all downstream implementers in `optimizers/`, `memory/`, and `routing/`.
     - Ensure no breaking changes to function signatures without updating all consumers simultaneously.
