"""Authentication endpoints for Polymarket UI.

This router issues a session token and stores session data via the
`api.middleware.session` store. It returns the session token on login so
the frontend can persist it (in `localStorage` or as a cookie) and include
it in subsequent requests using the `X-Session-Token` header.
"""
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
import os

from api.services.polymarket.logging_service import logging_service
from pathlib import Path
from api.middleware.session import set_session, get_session, delete_session

router = APIRouter()


# Pydantic models
class LoginRequest(BaseModel):
    api_key: str | None = None
    wallet_address: str | None = None
    polygon_private_key: str | None = None
    clob_api_key: str | None = None
    clob_secret: str | None = None
    clob_passphrase: str | None = None


class LoginResponse(BaseModel):
    status: str
    message: str
    is_authenticated: bool
    wallet_address: str | None = None
    session_token: str | None = None


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Authenticate user with API key and issue a session token."""
    try:
        api_key = (request.api_key or os.getenv("POLYMARKET_API_KEY") or "").strip()
        has_alt_creds = any(
            [
                request.polygon_private_key,
                request.clob_api_key,
                request.clob_secret,
                request.clob_passphrase,
                os.getenv("POLYGON_PRIVATE_KEY"),
                os.getenv("CLOB_API_KEY"),
                os.getenv("CLOB_SECRET"),
                os.getenv("CLOB_PASS_PHRASE"),
            ]
        )
        if not api_key and not has_alt_creds:
            raise ValueError("API key or CLOB credentials are required (set in .env or provide in the UI)")
        if api_key and len(api_key) < 10:
            raise ValueError("API key appears to be too short")

        updates = {}
        if request.api_key:
            updates["POLYMARKET_API_KEY"] = request.api_key.strip()
        if request.wallet_address:
            updates["POLYGON_ADDRESS"] = request.wallet_address.strip()
        if request.polygon_private_key:
            updates["POLYGON_PRIVATE_KEY"] = request.polygon_private_key.strip()
        if request.clob_api_key:
            updates["CLOB_API_KEY"] = request.clob_api_key.strip()
        if request.clob_secret:
            updates["CLOB_SECRET"] = request.clob_secret.strip()
        if request.clob_passphrase:
            updates["CLOB_PASS_PHRASE"] = request.clob_passphrase.strip()
        for key, value in updates.items():
            os.environ[key] = value
        if updates:
            _write_env_updates(updates)

        # Create a session token and persist session data
        session_id = os.urandom(16).hex()
        session_data = {
            "api_key": api_key,
            "wallet_address": request.wallet_address or os.getenv("POLYGON_ADDRESS"),
            "authenticated_at": str(__import__("datetime").datetime.now()),
        }
        try:
            set_session(session_id, session_data)
        except Exception:
            # If session store fails, still return token with in-memory fallback in middleware
            logging_service.log_event("WARN", "Session store set failed, falling back to memory", {})

        logging_service.log_event(
            "INFO",
            "User authenticated",
            {
                "api_key": api_key[:8] + "..." if api_key else "not provided",
                "wallet": request.wallet_address or os.getenv("POLYGON_ADDRESS") or "not provided",
            }
        )

        return LoginResponse(
            status="ok",
            message="Successfully authenticated",
            is_authenticated=True,
            wallet_address=request.wallet_address or os.getenv("POLYGON_ADDRESS"),
            session_token=session_id,
        )
    except ValueError as e:
        logging_service.log_event("WARN", "Authentication validation failed", {"error": str(e)})
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logging_service.log_event("ERROR", "Authentication failed", {"error": str(e)})
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}")


def _write_env_updates(updates: dict) -> None:
    """Update the local .env file with provided key/value pairs."""
    try:
        env_path = Path(__file__).resolve().parents[3] / ".env"
        lines = []
        if env_path.exists():
            lines = env_path.read_text().splitlines()
        existing = {}
        for line in lines:
            if "=" in line and not line.lstrip().startswith("#"):
                k = line.split("=", 1)[0].strip()
                existing[k] = line
        for key, value in updates.items():
            new_line = f"{key}={value}"
            if key in existing:
                idx = lines.index(existing[key])
                lines[idx] = new_line
            else:
                lines.append(new_line)
        env_path.write_text("\n".join(lines) + "\n")
    except Exception:
        logging_service.log_event("WARN", "Failed to update .env file", {})


@router.get("/auth/status")
async def get_auth_status(request: Request):
    """Get current authentication status using session token header/cookie."""
    try:
        token = request.headers.get("X-Session-Token") or request.cookies.get("session_token")
        env_key = os.getenv("POLYMARKET_API_KEY")
        env_wallet = os.getenv("POLYGON_ADDRESS")
        env_pk = os.getenv("POLYGON_PRIVATE_KEY")
        env_clob_key = os.getenv("CLOB_API_KEY")
        env_clob_secret = os.getenv("CLOB_SECRET")
        env_clob_pass = os.getenv("CLOB_PASS_PHRASE")
        env_ready = bool(env_key or env_pk or env_clob_key or env_clob_secret or env_clob_pass)
        env_trading_ready = bool(env_pk and (env_clob_key or env_key))
        if not token:
            return {
                "status": "ok",
                "is_authenticated": env_ready,
                "wallet_address": env_wallet,
                "env_configured": env_ready,
                "env_trading_ready": env_trading_ready,
                "source": "env" if env_ready else "none",
            }

        session = get_session(token)
        if not session:
            return {
                "status": "ok",
                "is_authenticated": env_ready,
                "wallet_address": env_wallet,
                "env_configured": env_ready,
                "env_trading_ready": env_trading_ready,
                "source": "env" if env_ready else "none",
            }

        return {
            "status": "ok",
            "is_authenticated": True,
            "wallet_address": session.get("wallet_address"),
            "env_configured": env_ready,
            "env_trading_ready": env_trading_ready,
            "source": "session",
        }
    except Exception as e:
        logging_service.log_event("ERROR", "Auth status check failed", {"error": str(e)})
        return {"status": "error", "is_authenticated": False, "wallet_address": None, "env_configured": False}


@router.post("/auth/logout")
async def logout(request: Request):
    """Logout and remove the session from the store if token provided."""
    try:
        token = request.headers.get("X-Session-Token") or request.cookies.get("session_token")
        if token:
            try:
                delete_session(token)
            except Exception:
                logging_service.log_event("WARN", "Failed to delete session (non-fatal)", {"token": token[:8] + "..."})

        logging_service.log_event("INFO", "User logged out", {})
        return {"status": "ok", "message": "Logged out successfully"}
    except Exception as e:
        logging_service.log_event("ERROR", "Logout failed", {"error": str(e)})
        raise HTTPException(status_code=500, detail=str(e))
