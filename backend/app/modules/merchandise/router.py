import json
from datetime import date
from typing import Annotated

from app.core.exceptions import InputError
from app.shared.api import export_response, job_payload, require_job, rows_response
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, ConfigDict, ValidationError


class RunOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    season: str | None = None
    control_date: date | None = None
    season_start: date | None = None
    season_end: date | None = None


router = APIRouter(prefix="/api/merchandise", tags=["Коммерческая аналитика"])


@router.post("/runs", status_code=202)
async def create(
    request: Request, files: Annotated[list[UploadFile], File()], options: Annotated[str, Form()] = "{}"
):
    if len(files) != 3:
        raise InputError(
            "Загрузите три актуальных Excel: поартикульный план, категорийный план и анализ продаж."
        )
    try:
        settings = RunOptions.model_validate(json.loads(options)).model_dump(mode="json", exclude_none=True)
    except (ValueError, ValidationError) as exc:
        raise InputError("Некорректные уточнения сезона или контрольной даты.") from exc
    ids = [await request.app.state.files.upload(f, "merchandise") for f in files]
    return {"id": request.app.state.jobs.submit("merchandise", ids, settings)}


@router.get("/runs/{identifier}")
def get_run(identifier: str, request: Request):
    with request.app.state.sessions() as db:
        return job_payload(require_job(db, identifier, "merchandise"), db)


@router.get("/runs/{identifier}/export")
def export(identifier: str, request: Request):
    return export_response(request, identifier, "merchandise")


@router.get("/runs/{identifier}/summary")
def summary(identifier: str, request: Request):
    with request.app.state.sessions() as db:
        job = require_job(db, identifier, "merchandise")
        return job.result


@router.get("/runs/{identifier}/articles/{article:path}")
def article(identifier: str, article: str, request: Request):
    from app.shared.models import RunRow
    from sqlalchemy import select

    with request.app.state.sessions() as db:
        require_job(db, identifier, "merchandise")
        row = db.scalar(
            select(RunRow).where(
                RunRow.job_id == identifier, RunRow.section == "articles", RunRow.item_key == article
            )
        )
        if not row:
            raise HTTPException(404, "Артикул не найден.")
        return row.data


@router.get("/runs/{identifier}/{section}")
def section(
    identifier: str,
    section: str,
    request: Request,
    q: str = "",
    status: str = "",
    category: str = "",
    sort: str = "id",
    descending: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=5000),
):
    if section not in (
        "articles",
        "categories",
        "weekly-plan",
        "pricing",
        "second-wave",
        "actions",
        "data-quality",
    ):
        raise HTTPException(404, "Раздел не найден.")
    return rows_response(
        request, identifier, "merchandise", section, q, status, category, offset, limit, sort, descending
    )
