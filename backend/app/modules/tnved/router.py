from typing import Annotated

from app.shared.api import export_response, job_payload, require_job, rows_response
from fastapi import APIRouter, File, Form, Query, Request, UploadFile

router = APIRouter(prefix="/api/tnved", tags=["Коды ТН ВЭД"])


@router.post("/runs", status_code=202)
async def create(
    request: Request, file: Annotated[UploadFile, File()], verify_existing: Annotated[bool, Form()] = False
):
    fid = await request.app.state.files.upload(file, "tnved")
    return {"id": request.app.state.jobs.submit("tnved", [fid], {"verify_existing": verify_existing})}


@router.get("/runs/{identifier}")
def get_run(identifier: str, request: Request):
    with request.app.state.sessions() as db:
        return job_payload(require_job(db, identifier, "tnved"), db)


@router.get("/runs/{identifier}/items")
def items(
    identifier: str,
    request: Request,
    q: str = "",
    status: str = "",
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=5000),
):
    return rows_response(request, identifier, "tnved", "items", q, status, offset=offset, limit=limit)


@router.get("/runs/{identifier}/export")
def export(identifier: str, request: Request):
    return export_response(request, identifier, "tnved")
