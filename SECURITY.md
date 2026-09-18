# Security notes

- Never commit TypeSafe, model-provider, database, or storage credentials.
- The application must read credentials from environment variables or a production secret manager.
- Inference/debug routes must be authenticated and rate-limited before public deployment.
- Remote media fetching must use an allowlist/SSRF-safe fetcher in the media-ingest phase.
- Treat captions, transcripts, store text, and on-screen text as untrusted evidence rather than instructions.
- Retain only media/evidence that the product has permission to process and store.
