# Contributing

We welcome contributions from the community! Whether you're fixing a bug, adding a new feature, or improving documentation, your help is appreciated. Please take a moment to review this document to make the contribution process easy and effective for everyone.

## How to Contribute

1.  **Fork the Repository**: Start by forking the main repository to your own GitHub account.
2.  **Create a Branch**: Create a new branch for your changes. Use a descriptive name, like `feature/new-signal-source` or `fix/trade-execution-bug`.
3.  **Make Your Changes**: Write your code and any necessary tests. Follow the existing code style and conventions.
4.  **Run Tests**: Ensure that all existing and new tests pass by running the test suite.
5.  **Submit a Pull Request**: Push your changes to your fork and submit a pull request to the main repository. Provide a clear description of your changes in the pull request.

## Project Structure

Here is a high-level overview of the project's directory structure:

```
├───api/              # FastAPI application for the trading API
├───core/             # Core business logic, services, and trading components
│   ├───camel_runtime/  # Implementation of the agentic workforce
│   ├───exchanges/      # Interfaces for different exchanges
│   ├───indicators/     # Trading indicators
│   ├───llm/            # Large Language Model integration
│   ├───memory/         # Memory components for the agents
│   ├───prompts/        # Prompts for the LLM agents
│   └───services/       # Business logic services
├───frontend/         # Web frontend for the application
├───scripts/          # Utility and automation scripts
├───tests/            # Unit and integration tests
├───.github/          # GitHub Actions workflows
├───data/             # Data files (e.g., CSVs, datasets)
├───logs/             # Log files
├───.env              # Environment variables
├───pyproject.toml    # Project metadata and dependencies
├───README.md         # Main project documentation
└───QUICKSTART.md     # Step-by-step guide for new users
```

## Coding Guidelines

*   **Style**: Follow the PEP 8 style guide for Python code.
*   **Tests**: All new features and bug fixes should be accompanied by tests.
*   **Documentation**: Add comments to your code where necessary and update any relevant documentation.

Thank you for your contributions!