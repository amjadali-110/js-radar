# Contributing to JS Radar

Thank you for your interest in contributing to **JS Radar**! Contributions of all kinds are welcome — bug fixes, new features, documentation improvements, and more.

---

## Table of Contents

- [Getting Started](#getting-started)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Commit Messages](#commit-messages)
- [Pull Request Process](#pull-request-process)
- [Reporting Bugs](#reporting-bugs)
- [Feature Requests](#feature-requests)
- [Code of Conduct](#code-of-conduct)

---

## Getting Started

1. **Fork** this repository.
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/your-username/js-radar.git
   cd js-radar
   ```
3. **Create a branch** for your work:
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## How to Contribute

### Bug Fixes
- Open an Issue first (if one doesn't exist) describing the bug.
- Reference the Issue in your Pull Request.

### New Features
- Open an Issue or Discussion to propose the feature before starting work.
- This avoids duplication and ensures alignment with the project direction.

### Documentation
- Improvements to `README.md`, inline comments, or any docs are always welcome.
- No Issue required for minor doc fixes.

### Scanner / Detection Rules
- If you want to add new secret patterns, endpoint detectors, or intelligence extractors, explain the rationale and provide test samples.

---

## Development Setup

```bash
# Start all services
docker-compose up --build

# Or use the helper scripts
./run.sh          # Linux / macOS
.\run.ps1         # Windows PowerShell
```

Refer to the `README.md` for full setup instructions including environment variables and configuration.

---

## Code Style

- **Backend (Python)**: Follow [PEP 8](https://peps.python.org/pep-0008/). Use descriptive variable names. Keep functions focused and short.
- **Frontend**: Follow consistent formatting; prefer clarity over cleverness.
- **Scanner**: Keep detection logic modular — one pattern category per module where possible.
- Do not commit secrets, credentials, `.env` files, or large binary files.

---

## Commit Messages

Use clear, imperative commit messages:

```
feat: add GitHub token detection pattern
fix: resolve CORS issue on scan results endpoint
docs: update setup instructions for Docker
refactor: split scanner worker into smaller modules
```

Prefixes: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

---

## Pull Request Process

1. Ensure your branch is up to date with `master` before submitting.
2. Describe **what** your PR changes and **why**.
3. Link any related Issues using `Closes #123` in the PR description.
4. Keep PRs focused — one logical change per PR.
5. Be responsive to review feedback.

PRs will be reviewed by the maintainer. Approval and merge may take a few days depending on complexity.

---

## Reporting Bugs

Open a GitHub Issue with:

- A clear title
- Steps to reproduce
- Expected vs actual behavior
- Environment details (OS, Docker version, browser if frontend)
- Screenshots or logs if applicable

For **security vulnerabilities**, follow the process in [SECURITY.md](./SECURITY.md) instead.

---

## Feature Requests

Open a GitHub Issue with the label `enhancement` and describe:

- The problem you are trying to solve
- Your proposed solution
- Any alternatives you considered

---

## Code of Conduct

Be respectful and constructive. Harassment, discrimination, or toxic behavior of any kind will not be tolerated. This project follows a simple rule: **treat others as you want to be treated**.

---

Built with care by **Amjad Ali**. Thank you for making JS Radar better.
