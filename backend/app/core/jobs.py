import logging
from concurrent.futures import ThreadPoolExecutor

from app.core.exceptions import BusinessError
from app.shared.models import FileRecord, Job, RunRow, WeeklyValue, now
from sqlalchemy import select

logger = logging.getLogger(__name__)


class JobExecutor:
    def __init__(self, settings, sessions, services):
        self.settings, self.sessions, self.services = settings, sessions, services
        self.pool = ThreadPoolExecutor(max_workers=settings.workers, thread_name_prefix="kanzler")

    def recover(self):
        with self.sessions.begin() as db:
            for job in db.scalars(select(Job).where(Job.status.in_(["queued", "running"]))):
                job.status, job.message = (
                    "failed",
                    "Выполнение прервано перезапуском. Запустите обработку повторно.",
                )
                job.error = {"message": job.message}
                job.finished_at = now()

    def submit(self, module, files, options):
        with self.sessions.begin() as db:
            job = Job(
                module=module,
                title="Классификация ТН ВЭД" if module == "tnved" else "Анализ коллекции",
                file_ids=files,
                options=options,
            )
            db.add(job)
            db.flush()
            identifier = job.id
        self.pool.submit(self.execute, identifier)
        return identifier

    def progress(self, identifier, percent, message):
        with self.sessions.begin() as db:
            job = db.get(Job, identifier)
            job.progress, job.message = percent, message

    def execute(self, identifier):
        try:
            with self.sessions.begin() as db:
                job = db.get(Job, identifier)
                job.status = "running"
                files = [db.get(FileRecord, fid) for fid in job.file_ids]
                module, options = job.module, job.options
            result, sections, output, output_name, weekly = self.services[module](
                files,
                options,
                self.settings.data_dir / "results" / identifier,
                lambda p, m: self.progress(identifier, p, m),
                self.sessions,
            )
            with self.sessions.begin() as db:
                for section, rows in sections.items():
                    for i, row in enumerate(rows):
                        db.add(
                            RunRow(
                                job_id=identifier,
                                section=section,
                                item_key=str(row.get("article", row.get("id", i))),
                                data=row,
                            )
                        )
                for row in weekly:
                    db.add(WeeklyValue(job_id=identifier, **row))
                job = db.get(Job, identifier)
                job.result, job.output_path, job.output_name = result, str(output), output_name
                job.status, job.progress, job.message, job.finished_at = "completed", 100, "Готово", now()
                job.title = result.get("title", job.title)
        except Exception as exc:
            logger.exception("Job %s failed", identifier)
            error = (
                {"message": exc.message, "details": exc.details}
                if isinstance(exc, BusinessError)
                else {
                    "message": "Не удалось выполнить обработку. Подробности сохранены в журнале приложения."
                }
            )
            with self.sessions.begin() as db:
                job = db.get(Job, identifier)
                job.status, job.error, job.message, job.finished_at = "failed", error, error["message"], now()

    def close(self):
        self.pool.shutdown(wait=True)
