from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from ecom_insight.api.feedback import FeedbackStore
from ecom_insight.api.repository import AnalyticsRepository
from ecom_insight.api.schemas import (
    FeedbackCreate,
    FeedbackRecord,
    HealthResponse,
    OverviewResponse,
    PaginatedResponse,
)
from ecom_insight.api.settings import ApiSettings
from ecom_insight.api.validation import validate_database_data_mode


def _validate_date_range(date_from: date | None, date_to: date | None) -> None:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not exceed date_to")


def create_app(
    settings: ApiSettings | None = None, *, validate_database: bool = True
) -> FastAPI:
    active_settings = settings or ApiSettings()
    if validate_database:
        validate_database_data_mode(active_settings.database_path, active_settings.data_mode)
    repository = AnalyticsRepository(active_settings.database_path)
    feedback_store = FeedbackStore(active_settings.feedback_database_path)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        if not validate_database:
            validate_database_data_mode(
                active_settings.database_path, active_settings.data_mode
            )
        yield

    app = FastAPI(
        title="EcomInsight API",
        version="0.1.0",
        description="Read-only e-commerce analytics and auditable attribution feedback.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=active_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        exists = repository.exists()
        updated = repository.data_updated_at() if exists else None
        return HealthResponse(
            status="ok" if exists else "degraded",
            database_exists=exists,
            feedback_store_ready=feedback_store.ready(),
            data_updated_at=updated,
            data_mode=active_settings.data_mode,
            database_origin_valid=True,
        )

    @app.get("/api/overview", response_model=OverviewResponse)
    def overview(
        date_from: date | None = None,
        date_to: date | None = None,
        shop_id: str | None = None,
    ) -> OverviewResponse:
        _validate_date_range(date_from, date_to)
        return repository.overview(
            date_from=date_from,
            date_to=date_to,
            shop_id=shop_id,
        )

    @app.get("/api/shops")
    def shops() -> list[dict[str, object]]:
        return repository.shops()

    @app.get("/api/shops/{shop_id}")
    def shop_detail(
        shop_id: str,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> dict[str, object]:
        _validate_date_range(date_from, date_to)
        try:
            return repository.shop_detail(
                shop_id,
                date_from=date_from,
                date_to=date_to,
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Shop not found") from error

    @app.get("/api/products")
    def products(
        shop_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[dict[str, object]]:
        return repository.products(shop_id=shop_id, limit=limit)

    @app.get("/api/search")
    def search_terms(
        shop_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
    ) -> list[dict[str, object]]:
        return repository.search_terms(shop_id=shop_id, limit=limit)

    @app.get("/api/inventory")
    def inventory(
        status: str | None = None,
        limit: int = Query(default=100, ge=1, le=500),
    ) -> list[dict[str, object]]:
        return repository.inventory(status=status, limit=limit)

    @app.get("/api/finance")
    def finance() -> list[dict[str, object]]:
        return repository.finance()

    @app.get("/api/anomalies", response_model=PaginatedResponse)
    def anomalies(
        metric: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=30, ge=1, le=100),
    ) -> PaginatedResponse:
        items, total = repository.anomalies(
            metric=metric,
            severity=severity,
            status=status,
            page=page,
            page_size=page_size,
        )
        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    @app.get("/api/anomalies/{attribution_id}")
    def anomaly_detail(attribution_id: str) -> dict[str, object]:
        try:
            result = repository.anomaly_detail(attribution_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Anomaly not found") from error
        result["feedback"] = [
            item.model_dump(mode="json")
            for item in feedback_store.list_for_attribution(attribution_id)
        ]
        return result

    @app.get(
        "/api/anomalies/{attribution_id}/feedback",
        response_model=list[FeedbackRecord],
    )
    def list_feedback(attribution_id: str) -> list[FeedbackRecord]:
        if not repository.anomaly_exists(attribution_id):
            raise HTTPException(status_code=404, detail="Anomaly not found")
        return feedback_store.list_for_attribution(attribution_id)

    @app.post(
        "/api/anomalies/{attribution_id}/feedback",
        response_model=FeedbackRecord,
        status_code=201,
    )
    def create_feedback(
        attribution_id: str,
        payload: FeedbackCreate,
    ) -> FeedbackRecord:
        if not repository.anomaly_exists(attribution_id):
            raise HTTPException(status_code=404, detail="Anomaly not found")
        try:
            return feedback_store.create(
                attribution_id=attribution_id,
                payload=payload,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    return app


# Importing an ASGI module must not require a local warehouse. The lifespan guard
# still fails process startup before it can serve a request when lineage is invalid.
app = create_app(validate_database=False)
