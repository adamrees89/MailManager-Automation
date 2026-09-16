# Contributing

Thanks for your interest in contributing to MailManager-Automation! We welcome bug reports, improvements, and documentation updates.

- Fork the repository and create a feature branch: `git checkout -b feat/your-change`
- Write tests for new features or bug fixes where appropriate
- Run linters and tests locally before opening a PR
- Open a Pull Request describing the change, motivation, and any compatibility concerns

Code style:
- Follow idiomatic Python 3 style (PEP 8)
- Keep functions small and focused

Testing:
- Add unit tests for core logic (scanner, DB writer, XML parser, reconciliation)
- Prefer small, deterministic tests that don't depend on external state

Review process:
- PRs will be reviewed by maintainers; expect iterative review comments
- Squash or rebase commits as requested

Roadmap contributions:
- If you'd like to add a larger feature, open an issue first to discuss the design.
