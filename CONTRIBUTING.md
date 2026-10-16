# Contributing

(Private alpha — this document will be expanded before the public release.)

## Ground rules

- **Pass through SDK models** — never introduce wrapper dataclasses for
  Benchling resources.
- **Generic over bespoke** — prefer helpers that work on any resource to
  per-resource code.
- **Every public function is typed and documented.** CI runs mypy
  `--strict` and ruff.
- **Unit tests must run with zero credentials.** Anything touching a real
  tenant is `@pytest.mark.integration`.

## Workflow

```bash
make install     # editable install with dev extras
make lint type test
```

PRs need: passing CI, a test for every behaviour change, and a changelog
entry under `docs/CHANGELOG.md`.
