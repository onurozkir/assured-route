# Contributing to Assured Route

Thank you for your interest in contributing to **Assured Route**! This repository is an open source companion to the article on quality-aware LLM routing for invoice extraction. We welcome contributions, whether they are bug reports, documentation enhancements, additional validators, test scenarios, or new provider adapters.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute?](#how-can-i-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Features & Enhancements](#suggesting-features--enhancements)
  - [Contributing Code](#contributing-code)
- [Development Setup](#development-setup)
  - [Prerequisites](#prerequisites)
  - [Installation](#installation)
  - [Environment Configuration](#environment-configuration)
  - [Running the Local Service](#running-the-local-service)
- [Quality Standards & Tooling](#quality-standards--tooling)
  - [Running Tests](#running-tests)
  - [Linting and Formatting](#linting-and-formatting)
  - [Type Checking](#type-checking)
  - [Packaging](#packaging)
- [Design Principles](#design-principles)
- [Submitting a Pull Request](#submitting-a-pull-request)

---

## Code of Conduct

All contributors and maintainers are expected to adhere to our [Code of Conduct](CODE_OF_CONDUCT.md). Please read it to ensure a welcoming and productive environment for everyone.

---

## How Can I Contribute?

### Reporting Bugs

Before creating a bug report, please verify that the issue has not already been reported by checking existing [GitHub Issues](https://github.com/onurozkir/assured-route/issues).

When submitting a bug report, please include:
- A clear, descriptive title.
- Steps to reproduce the behavior.
- Expected vs. actual behavior.
- Relevant environment details (Python version, OS, provider mode: mock or live).
- Error traces or audit log outputs (ensure no private API keys or proprietary invoice data are included).

### Suggesting Features & Enhancements

Feature requests are tracked as GitHub Issues. Please explain:
- The problem or use case you are addressing.
- Why existing routing/validation policies do not suffice.
- A proposed solution or design sketch.

### Contributing Code

1. Fork the repository and create your branch from `main`.
2. Keep changes focused and atomic.
3. Add unit or contract tests covering new logic or bug fixes.
4. Ensure all linters, type checks, and tests pass.

---

## Development Setup

### Prerequisites

- **Python**: 3.12 or newer.
- **uv**: Modern, fast Python package and environment manager ([installation guide](https://docs.astral.sh/uv/)).
- **Git**

### Installation

Clone the repository and set up the locked development environment:

```bash
git clone https://github.com/onurozkir/assured-route.git
cd assured-route
uv sync --locked
```

### Environment Configuration

Copy the example environment configuration:

```bash
# On Linux / macOS:
cp .env.example .env

# On Windows (PowerShell):
Copy-Item .env.example .env
```

By default, `AR_PROVIDER_MODE=mock` is active. This mode requires no API credentials and relies on deterministic mock providers and synthetic OCR payloads.

If working with real models:
```bash
# On Linux / macOS:
cp .env.llm.example .env

# On Windows (PowerShell):
Copy-Item .env.llm.example .env
```
And provide valid endpoints and API keys in `.env`.

### Running the Local Service

Start the FastAPI application with auto-reload:

```bash
uv run uvicorn assured_route.api:app --reload --host 127.0.0.1 --port 8000
```

- API Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- Health Check: [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz)

---

## Quality Standards & Tooling

Assured Route maintains strict quality, typing, and formatting standards enforced in CI.

### Running Tests

Execute the full test suite with `pytest`:

```bash
uv run pytest
```

Run specific test modules:

```bash
uv run pytest tests/test_routing.py
uv run pytest tests/test_validation.py
```

### Linting and Formatting

The project uses [Ruff](https://docs.astral.sh/ruff/) with strict rule sets (`E`, `F`, `I`, `UP`, `B`, `ASYNC`) and a 100-character line length limit.

Check for lint issues:
```bash
uv run ruff check .
```

Automatically fix lint issues:
```bash
uv run ruff check . --fix
```

Verify formatting:
```bash
uv run ruff format --check .
```

Reformat code:
```bash
uv run ruff format .
```

### Type Checking

Type annotations are strictly checked using `mypy` with Pydantic plugin integration:

```bash
uv run mypy
```

Code must produce **zero** type errors under strict mode.

### Packaging

Verify that the project packages cleanly:

```bash
uv run uv build
```

---

## Design Principles

When modifying or expanding Assured Route, please keep the following core design principles in mind:

1. **Pure & Deterministic Validators**: Validation rules (`schema_validator`, `grounding_validator`, `business_rules`) must be pure functions or classes without external side effects, network calls, or hidden state.
2. **Strict Defense in Depth**: An LLM (even an expensive or fine-tuned model) should never bypass validation gates or override deterministic sanity checks.
3. **Bounded Latency & Deadlines**: Routing decisions, retries, and escalations must check remaining time budgets against deadlines (`DeadlineManager`).
4. **Structured & Safe Audit Trails**: Audit logging should document decisions, risk scores, and routing transitions without leaking unvetted raw secrets or credential tokens.
5. **Separation of Concerns**: Provider adapters (`OpenAICompatibleProvider`, `MockProvider`) must implement clear abstract interfaces (`LLMProviderInterface`) allowing easy substitution.

---

## Submitting a Pull Request

1. **Branch Naming**: Use informative branch names:
   - `feat/add-anthropic-adapter`
   - `fix/tax-rounding-validation`
   - `docs/clarify-postman-simulation`
2. **Commit Messages**: Write concise, imperative commit messages (e.g., `feat: implement tax tolerance check in business rules`).
3. **PR Checklist**:
   - [ ] Branch is rebased or up to date with `main`.
   - [ ] Tests covering new logic or regressions have been added.
   - [ ] `uv run pytest` passes without errors.
   - [ ] `uv run ruff check .` and `uv run ruff format --check .` report no issues.
   - [ ] `uv run mypy` reports no issues.
   - [ ] Relevant documentation or examples have been updated.
4. Open the Pull Request on GitHub and describe the changes, motivation, and test verification performed.

