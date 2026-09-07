import hashlib
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from app.core.exceptions import InputError
from app.shared.models import FileRecord, uid


def validate_xlsx(path):
    try:
        with ZipFile(path) as z:
            names = z.namelist()
            if "xl/workbook.xml" not in names or any("vbaProject" in n for n in names):
                raise InputError("Файл не является корректным XLSX без макросов.")
            if sum(i.file_size for i in z.infolist()) > 700 * 1024 * 1024:
                raise InputError("Распакованный Excel превышает допустимый размер 700 МБ.")
    except (BadZipFile, OSError) as exc:
        raise InputError("Файл не является корректным XLSX.") from exc


class FileService:
    def __init__(self, settings, sessions):
        self.settings, self.sessions = settings, sessions
        for name in ("uploads", "results"):
            (settings.data_dir / name).mkdir(parents=True, exist_ok=True)

    async def upload(self, upload, module):
        name = Path((upload.filename or "").replace("\\", "/")).name
        if Path(name).suffix.lower() != ".xlsx":
            raise InputError("Поддерживаются файлы .xlsx.")
        identifier = uid()
        path = self.settings.data_dir / "uploads" / f"{identifier}.xlsx"
        size, digest = 0, hashlib.sha256()
        try:
            with path.open("wb") as f:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > self.settings.max_upload_bytes:
                        raise InputError("Размер файла превышает 80 МБ.")
                    digest.update(chunk)
                    f.write(chunk)
            validate_xlsx(path)
            with self.sessions.begin() as db:
                db.add(
                    FileRecord(
                        id=identifier,
                        original_name=name,
                        sha256=digest.hexdigest(),
                        size=size,
                        module=module,
                        path=str(path),
                    )
                )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return identifier
