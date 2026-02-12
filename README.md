# Agentic Trading System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An autonomous trading system for Polymarket that uses a workforce of AI agents to make trading decisions based on real-time data and market signals.

## About The Project

This project is an agentic trading system designed to automate trading on the Polymarket platform. It uses a combination of traditional trading indicators, real-time data from sources like RSS feeds, and a workforce of AI agents powered by Large Language Models (LLMs) to analyze market conditions and execute trades.

The system is designed to be highly modular and extensible, allowing for the addition of new signal sources, trading strategies, and exchange integrations.

## Key Features

*   **Agentic Workforce**: A team of AI agents that collaborate to analyze markets, propose trades, and execute them.
*   **RSS Feed Integration**: Ingests and analyzes news from RSS feeds to generate trading signals.
*   **Modular Architecture**: Easily extend the system with new signal sources, trading strategies, and exchange integrations.
*   **Real-time Monitoring**: A FastAPI backend provides an API for real-time monitoring of trading activity.
*   **Comprehensive Testing**: A suite of unit and integration tests to ensure the reliability of the system.
*   **Trigger Modes**: Manual and Interval triggers for RSS flux with configurable cadence and limits.
*   **MCP Server**: Expose the workforce as an MCP server (default `localhost:8001`).

## Getting Started

To get a local copy up and running, please follow the steps in the [QUICKSTART.md](QUICKSTART.md) file.

## Trigger Modes

*   **Manual**: Runs immediately on the latest feed and bypasses RSS cache thresholds and trade limit checks.
*   **Interval**: Runs on a schedule (hours/days) and enforces RSS cache thresholds, verification, and limits.

You can switch modes and set interval hours directly in the Workforce UI.

## UI Defaults

The UI uses `.env` values by default. If you leave the login API key blank, the backend falls back to `POLYMARKET_API_KEY` from `.env`.

## Project Status

This project is currently in active development. The immediate focus is on completing the RSS feed integration and the workforce management system. See the [TODO.md](TODO.md) file for a more detailed roadmap.

## Contributing

Contributions are what make the open-source community such an amazing place to learn, inspire, and create. Any contributions you make are **greatly appreciated**.

Please read our [CONTRIBUTING.md](CONTRIBUTING.md) for details on our code of conduct, and the process for submitting pull requests to us.

## License

Distributed under the MIT License. See `LICENSE` for more information.
