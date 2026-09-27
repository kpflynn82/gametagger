@AGENTS.md

## Working across sessions

Several Claude sessions (cloud, desktop, terminal) work on this repository. GitHub is the
shared record.

- Start from the latest `main`, and work on your own branch. Never push to another session's
  branch.
- Read [docs/EXECUTION_STATUS.md](docs/EXECUTION_STATUS.md) first. Before you finish, add what
  you did, what you measured and what is left, so the next session can pick it up.
- The plan of record is [docs/NEXT_IMPROVEMENTS_PLAN.md](docs/NEXT_IMPROVEMENTS_PLAN.md). Mark
  steps done there rather than starting a parallel plan.
- The spending ledger (`benchmark-runs/`) is git-ignored and local to each machine. Other
  sessions' spend is not visible to you. Pass a `--budget-usd` no higher than the owner
  authorized for your task, and record every paid run's cost in EXECUTION_STATUS.
- `benchmark-runs/` also holds downloaded store media and dossiers. These are third-party
  content and are never committed. Rebuild them with `gametagger-compare dossiers` when needed.
- Keys live in each machine's own environment or `.env` file. Never commit them, print them or
  paste them into chat.
