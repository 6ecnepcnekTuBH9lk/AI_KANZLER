from datetime import UTC

from app.shared.models import FileRecord, Job, RunRow
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import func, select

router = APIRouter(prefix="/api")


def job_payload(job, db):
    files = [db.get(FileRecord, fid) for fid in job.file_ids]
    return {
        "id": job.id,
        "module": job.module,
        "title": job.title,
        "status": job.status,
        "progress": job.progress,
        "message": job.message,
        "created_at": job.created_at.replace(tzinfo=job.created_at.tzinfo or UTC).isoformat(),
        "finished_at": job.finished_at.replace(tzinfo=job.finished_at.tzinfo or UTC).isoformat()
        if job.finished_at
        else None,
        "files": [
            {"id": f.id, "name": f.original_name, "size": f.size, "sha256": f.sha256} for f in files if f
        ],
        "result": job.result,
        "error": job.error,
        "output_name": job.output_name,
    }


def require_job(db, job_id, module=None):
    job = db.get(Job, job_id)
    if not job or (module and job.module != module):
        raise HTTPException(404, "Запуск не найден.")
    return job


@router.get("/history")
def history(request: Request, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500)):
    with request.app.state.sessions() as db:
        jobs = db.scalars(select(Job).order_by(Job.created_at.desc()).offset(offset).limit(limit)).all()
        return {
            "items": [job_payload(j, db) for j in jobs],
            "total": db.scalar(select(func.count()).select_from(Job)),
        }


@router.get("/jobs/{identifier}")
def get_job(identifier: str, request: Request):
    with request.app.state.sessions() as db:
        return job_payload(require_job(db, identifier), db)


def rows_response(
    request,
    identifier,
    module,
    section,
    q="",
    status="",
    category="",
    offset=0,
    limit=100,
    sort="id",
    descending=False,
):
    with request.app.state.sessions() as db:
        require_job(db, identifier, module)
        conditions = [RunRow.job_id == identifier, RunRow.section == section]
        if q:
            conditions.append(
                RunRow.item_key.contains(q, autoescape=True)
                | RunRow.data["name"].as_string().contains(q, autoescape=True)
            )
        if status:
            conditions.append(RunRow.data["status"].as_string() == status)
        if category:
            conditions.append(RunRow.data["category"].as_string() == category)
        count = db.scalar(select(func.count()).select_from(RunRow).where(*conditions))
        sortable = {
            "execution",
            "season_fact",
            "plan_units",
            "base",
            "forecast",
            "stock",
            "price",
            "age",
            "cover",
        }
        order = RunRow.data[sort].as_float() if sort in sortable else RunRow.id
        rows = db.scalars(
            select(RunRow)
            .where(*conditions)
            .order_by(order.desc() if descending else order)
            .offset(offset)
            .limit(limit)
        )
        return {"items": [r.data for r in rows], "total": count, "offset": offset, "limit": limit}


def export_response(request, identifier, module):
    with request.app.state.sessions() as db:
        job = require_job(db, identifier, module)
        if job.status != "completed" or not job.output_path:
            raise HTTPException(409, "Результат ещё не готов.")
        return FileResponse(
            job.output_path,
            filename=job.output_name,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
