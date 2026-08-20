---
description: Protocols for reading research from Hermes and saving development learnings in the Obsidian Vault
---

# Multi-Agent Memory & Obsidian Vault Protocol

This workspace is integrated with the Obsidian Knowledge Vault located at `C:\Users\prade\Documents\Obsidian Vault` via the `obsidian_vault` MCP filesystem server.

## 1. Directory Conventions in the Obsidian Vault

- `01_Research/`: Technical research, benchmark comparisons, and architectural options produced by research agents (e.g. Hermes).
- `02_Patterns/`: Established design patterns, prompt schemas, and reusable coding strategies.
- `03_Projects/Elone/`: Project-specific requirements, data schemas (OKF), and architecture specifications.
- `04_Learnings/`: Bug fixes, gotchas, optimizations, and post-mortems logged during development.
- `05_SOPs/`: Standard Operating Procedures consumed by the Elone ingestion pipeline.

## 2. Reading Memory (Before Starting Complex Tasks)

- Before designing or implementing new modules, search or query `01_Research/` and `02_Patterns/` via the `obsidian_vault` MCP tools for existing notes created by Hermes or previous agent sessions.
- Adhere to data models and ontology definitions documented in `03_Projects/Elone/`.

## 3. Writing Memory (After Solving Non-Trivial Problems)

- When a subtle bug, optimization trick, or architecture pattern is discovered during development:
  1. Create or append a Markdown note in `04_Learnings/<topic_name>.md`.
  2. Use YAML frontmatter:
     ```yaml
     ---
     title: "<Topic Title>"
     type: learning
     author: antigravity
     project: elone
     tags: [python, sop, mcp, ...]
     date: YYYY-MM-DD
     ---
     ```
  3. Include a concise Problem Statement, Root Cause, Solution Code Snippet, and `[[wikilinks]]` to related research or project files.
