# Security Policy

Report vulnerabilities to security@involvedata.com, or through GitHub's
private vulnerability reporting on this repository. Do not open public
issues for security problems.

Notes for users:

- Cached API responses are stored as JSON on disk, never pickle. The disk
  tier creates owner-only files, but the directory can still hold sensitive
  scientific data. Treat it with the same care as the data itself, and
  point `CachePolicy.directory` somewhere protected.
- The cache is keyed by tenant, not by credential. Don't share a cache
  directory between credentials with different access.
- Credentials are only ever read from explicit configuration or
  `BENCHLING_*` environment variables and are never written to disk by
  this library.
