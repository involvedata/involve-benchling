# Security Policy

Report vulnerabilities to security@involvedata.com. Do not open public
issues for security problems.

Notes for users:

- Cached API responses are stored as JSON on disk (never pickle). The
  cache directory may still contain sensitive scientific data — treat it
  with the same care as the data itself, and point `CachePolicy.directory`
  somewhere appropriately protected.
- Credentials are only ever read from explicit configuration or
  `BENCHLING_*` environment variables and are never written to disk by
  this library.
