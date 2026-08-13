from datetime import date, datetime

from pydantic import BaseModel


class JobItem(BaseModel):
    title: str
    company: str
    location: str
    url: str
    source: str
    source_ref: str | None = None
    company_website: str | None = None
    posted_at: date | None = None
    contact_name: str | None = None
    contact_email: str | None = None
    description_md: str = ""
    # Angaben aus der Trefferliste und dem Detail-Abruf der Quelle.
    # Alle optional: was die Quelle nicht liefert, bleibt None und wird in
    # der Oberflaeche weggelassen statt als „unbekannt" behauptet.
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
    employer_hash: str | None = None
    gone_at: datetime | None = None
    scraped_at: datetime
