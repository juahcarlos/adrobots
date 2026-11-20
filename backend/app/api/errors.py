import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.keitaro import KeitaroError
from app.schemas.campaign import ErrorResponse
from app.services.exceptions import (
    CampaignServiceError,
    CampaignStepError,
    DbError,
    NotFoundError,
    StreamGoogleError,
    StreamOfferError,
    ValidationError,
)

logger = logging.getLogger(__name__)

_PATH = __file__

_STATUS_BY_TYPE = {
    ValidationError: 422,
    NotFoundError: 404,
    CampaignStepError: 502,
    StreamGoogleError: 502,
    StreamOfferError: 502,
    DbError: 500,
}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(CampaignServiceError)
    async def handle_service_error(
        request: Request, exc: CampaignServiceError
    ) -> JSONResponse:
        status = _STATUS_BY_TYPE.get(type(exc), 500)
        return JSONResponse(
            status_code=status,
            content=ErrorResponse(
                step=exc.step,
                error=exc.error,
                campaign_id=exc.campaign_id,
            ).model_dump(),
        )

    @app.exception_handler(KeitaroError)
    async def handle_keitaro_error(
        request: Request, exc: KeitaroError
    ) -> JSONResponse:
        source = "offers" if request.url.path.endswith("/offers") else None
        return JSONResponse(
            status_code=502,
            content=ErrorResponse(
                source=source,
                error=str(exc),
                campaign_id=None,
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        text = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'][1:])}: {e['msg']}"
            for e in exc.errors()
        )
        return JSONResponse(
            status_code=422,
            content=ErrorResponse(
                step="validation", error=text, campaign_id=None
            ).model_dump(),
        )
