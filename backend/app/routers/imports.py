import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app import importer
from app.db import get_db
from app.schemas import ImportReport, IssueOut, RowReport

router = APIRouter(prefix="/imports", tags=["imports"])
DbDep = Annotated[Session, Depends(get_db)]


@router.post("/hazards", response_model=ImportReport)
def import_hazards(
    db: DbDep,
    file: UploadFile,
    source_crs: Annotated[str, Form()] = "EPSG:4326",
    dry_run: Annotated[bool, Form()] = True,
    on_error: Annotated[Literal["skip", "abort"], Form()] = "skip",
    reject_overlaps: Annotated[bool, Form()] = False,
) -> ImportReport:
    """Validate (and optionally apply) a CSV or GeoJSON file of hazards.

    - `dry_run=true` (default) only validates and returns the report.
    - `on_error=skip` imports the valid rows and reports the rest;
      `abort` imports nothing if any row is rejected.
    - Rows with a `code` of an existing hazard update it; rows without one create a new hazard.
    """
    try:
        content = file.file.read(importer.MAX_BYTES + 1)
        rows = importer.parse_upload(file.filename or "", content)
        transformer = importer.make_transformer(source_crs)
    except importer.ImportFileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    plans = importer.validate(db, rows, transformer, reject_overlaps)
    rejected = sum(1 for p in plans if not p.ok)
    import_id = uuid.uuid4()

    committed = False
    created = updated = 0
    can_commit = not dry_run and not (on_error == "abort" and rejected > 0)
    if can_commit:
        created, updated = importer.apply(db, plans, import_id)
        db.commit()
        committed = True
    else:
        created = sum(1 for p in plans if p.ok and p.action == "create")
        updated = sum(1 for p in plans if p.ok and p.action == "update")

    return ImportReport(
        import_id=str(import_id),
        filename=file.filename or "",
        source_crs=source_crs,
        dry_run=dry_run,
        on_error=on_error,
        committed=committed,
        total=len(plans),
        accepted=len(plans) - rejected,
        rejected=rejected,
        created=created,
        updated=updated,
        warning_count=sum(len(p.warnings) for p in plans),
        rows=[
            RowReport(
                row=p.index,
                label=p.label,
                code=p.code,
                outcome="accepted" if p.ok else "rejected",
                action=p.action,
                errors=[IssueOut(code=i.code, message=i.message) for i in p.errors],
                warnings=[IssueOut(code=i.code, message=i.message) for i in p.warnings],
            )
            for p in plans
        ],
    )
