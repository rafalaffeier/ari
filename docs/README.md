# Documentation

`architecture-reference.md` is the working architecture source for development.

`foundation-flow.md` contains the current Mermaid flow diagrams for the local-first memory foundation.

`foundation-closure.md` records what is accepted as complete in the foundation phase.

`escalation-plan.md` defines the controlled build phases from foundation to secure multi-device product.

`desktop-memory-contract.md` defines the Phase 2 contract for the desktop app to use the protected memory API.

`production-staging-runbook.md` defines the Phase 7 staging deployment, backup/restore, object storage, rate limiting, logs, and security checklist.

The Word document in `/Users/rafalaffeier/projects/asistente/documentos/` remains the formatted copy for human reading. When the Word file changes, regenerate this Markdown reference with:

```bash
/Users/rafalaffeier/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 scripts/docx_to_markdown.py
```
