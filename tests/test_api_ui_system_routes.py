from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import ui_menu


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(ui_menu.router)
    return TestClient(app)


def test_ui_system_settings_route_renders():
    client = _build_client()
    response = client.get("/ui/dex/settings")
    assert response.status_code == 200
    assert "Configuration" in response.text


def test_ui_system_workforce_route_renders():
    client = _build_client()
    response = client.get("/ui/polymarket/workforce")
    assert response.status_code == 200
    assert "Workforce" in response.text


def test_ui_unknown_system_returns_404():
    client = _build_client()
    response = client.get("/ui/unknown/settings")
    assert response.status_code == 404
