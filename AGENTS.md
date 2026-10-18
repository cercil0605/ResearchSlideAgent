# Repository working rules

## Keep documentation in sync

When changing user-visible behavior, supported inputs, limits, generated output, API or schema contracts, authentication, deployment, or verification claims, check the documentation map in [`docs/README.md`](docs/README.md) and update the affected documents in the same change.

- Update [`docs/CAPABILITIES.md`](docs/CAPABILITIES.md) when a capability or limit changes.
- Update [`docs/USER_USE_CASES.md`](docs/USER_USE_CASES.md) when a user workflow changes.
- Update [`API.md`](API.md), `schemas/`, or examples when a tool or data contract changes.
- Update `ARCHITECTURE.md`, `SECURITY.md`, `TESTING.md`, and `deploy/` guides when their respective implementation or operational behavior changes.
- Keep authoring rules in the Plugin Skill's `references/`; do not create a second editable copy in `docs/`.
- Treat documents marked as historical in `docs/README.md` as evidence of past decisions, not current requirements. Do not silently promote an old statement to current behavior.

If a code change does not require a documentation change, state the reason in the change summary. Do not leave user-facing documentation inconsistent with the code or tests.
