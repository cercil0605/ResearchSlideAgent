# Repository working rules

## Keep documentation in sync

Human-facing docs are `README.md` and `docs/` (one question per page, diagrams first, plain Japanese).
When a change affects what a page says, update that page in the same change.

| If you change | Update |
|---|---|
| Tool names, inputs, outputs, local/remote availability | `docs/02-llm-contract.md`, `docs/03-implementation.md` |
| Call flow, jobs, previews, patching | `docs/01-flow.md` |
| Authentication, signed links, attachment hosts | `docs/04-auth.md` |
| Template, prototypes, slot handling, layout checks | `docs/05-design.md` |
| Authoring rules delivery, input limits, save-time feedback | `docs/06-content.md` |
| Database, job states, retries, retention | `docs/07-state.md` |
| Setup, Makefile, env vars, deployment, update | `docs/08-operate.md` |
| Error codes | `docs/09-troubleshoot.md` |
| What has been tested or confirmed | `docs/verified.md` |

- Write only what the code shows. Cite the file (and function) when it helps the reader find it.
- Keep authoring rules for the LLM in `plugins/research-slide-agent/skills/research-slides/references/`. The server loads them (`rules.py`); do not copy them into `docs/`.
- Machine contracts live in `schemas/` and `examples/`.

If a code change needs no documentation change, say why in the change summary.
