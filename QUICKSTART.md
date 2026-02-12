# Quickstart Guide

This guide will walk you through the steps to get the Agentic Trading System up and running on your local machine.

## Prerequisites

Before you begin, ensure you have the following installed:

*   **Python 3.11**
*   **Pip** (Python package installer)
*   **Docker** and **Docker Compose** (for the Docker-based setup)
*   **Git**

## Installation

You can either install the project locally or use the provided Docker setup.

### Option 1: Local Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/agentic-system-trading.git
    cd agentic-system-trading
    ```

2.  **Create a virtual environment:**

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install the dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

### Option 2: Docker Installation

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/your-username/agentic-system-trading.git
    cd agentic-system-trading
    ```

2.  **Build and start the Docker containers:**

    ```bash
    docker compose up --build
    ```

    This will build the `polymarket-bot` image and start all the services defined in the `docker-compose.yml` file, including Redis, Qdrant, Ollama, and Neo4j.

## Configuration

1.  **Create a `.env` file:**

    Copy the `env.example` file to a new file named `.env`:

    ```bash
    cp env.example .env
    ```

2.  **Edit the `.env` file:**

    Open the `.env` file and fill in the required environment variables. This includes API keys for various services, your Polygon private key and address, and other configuration options.

    **Important:** Do not commit your `.env` file to version control.

3.  **UI Defaults:**

    The UI uses `.env` values by default. If you leave the UI login API key blank, the backend falls back to `POLYMARKET_API_KEY`.

## Running the Application

### Local

If you installed the project locally, you can start the FastAPI server with the following command:

```bash
uvicorn api.main_polymarket:app --reload
```

### Docker

If you are using the Docker setup, the application will be started automatically when you run `docker compose up`.

## Accessing the API

Once the application is running, you can access the API at `http://localhost:8000`. The API documentation is available at `http://localhost:8000/docs`.

## Trigger Modes (UI)

*   **Manual**: Runs immediately on the latest feed and bypasses RSS cache thresholds and trade limit checks.
*   **Interval**: Runs on a schedule (hours/days) and enforces RSS cache thresholds, verification, and limits.

Configure trigger mode and interval hours in the Workforce UI.

## MCP Server

The workforce can be exposed as an MCP server (default `localhost:8001`). If you run via Docker, make sure port `8001` is published (already configured in `docker-compose.yml`).
