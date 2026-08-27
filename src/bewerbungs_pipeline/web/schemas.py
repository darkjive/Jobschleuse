"""Pydantic-Antwort- und Request-Modelle für die JSON-API unter /api.

sqlite3.Row unterstützt keinen Attributzugriff (nur `row["x"]`) — die
*_out-Hilfsfunktionen gehen deshalb über `dict(row)` statt über
`model_validate(row, from_attributes=True)`.
"""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

Status = Literal["new", "selected", "rejected"]


class JobOut(BaseModel):
    id: int
    title: str
    company: str
    location: str
    url: str
    source: str
    status: str
    source_ref: str | None = None
    posted_at: date | None = None
    description_md: str
    job_kind: str | None = None
    employer_kind: str | None = None
    source_partner: str | None = None
    external_host: str | None = None
    homeoffice: str | None = None
    salary: str | None = None
    contract: str | None = None
    worktime: str | None = None
    distance_km: int | None = None
    start_date: date | None = None
    changed_at: datetime | None = None
    street: str | None = None
    plz: str | None = None
    education: str | None = None
    gone_at: datetime | None = None
    scraped_at: datetime
    application_id: int | None = None


def job_out(row, application_id: int | None = None) -> JobOut:
    return JobOut.model_validate({**dict(row), "application_id": application_id})


class SlotOut(BaseModel):
    value: str
    source: str
    updated_at: str


class ApplicationOut(BaseModel):
    id: int
    job_id: int
    template_path: str
    created_at: str
    updated_at: str
    slots: dict[str, SlotOut]


class ApplicationDetail(BaseModel):
    application: ApplicationOut
    stelle: JobOut


class TaskOut(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    beschreibung: str
    status: str
    meldung: str = ""
    ergebnis: Any = None


class TaskRef(BaseModel):
    task_id: str


class StatusUpdate(BaseModel):
    status: Status


class BulkStatusUpdate(BaseModel):
    ids: list[int]
    status: Status


class SlotValue(BaseModel):
    value: str


class ApplicationCreate(BaseModel):
    job_id: int


class FetchRequest(BaseModel):
    was: str
    wo: str
    umkreis: int = 25
    seit: int | None = None
    ohne_zeitarbeit: bool = False
    nur_arbeit: bool = False
    quelle: Literal["arbeitsagentur", "indeed"] = "arbeitsagentur"
