---
description: Verification gate before calling work complete
---
Do not fix anything until I have read the results.

1. Run the fussion-reviewer subagent on the current diff.
2. cd backend && .venv/Scripts/ruff check app tests
3. cd backend && .venv/Scripts/pytest tests
4. cd frontend && pnpm test && pnpm build
5. If evals exist, run the eval suite.

Report: reviewer verdict and every finding, then each command's result.
Then list which conditional blocks of CLAUDE.md §9 apply to this change and
whether each item is met.
