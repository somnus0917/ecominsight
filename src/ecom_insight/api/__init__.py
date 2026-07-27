"""FastAPI application boundary and feedback workflow."""

from ecom_insight.api.app import app, create_app
from ecom_insight.api.settings import ApiSettings

__all__ = ["ApiSettings", "app", "create_app"]
