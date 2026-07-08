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
    scraped_at: datetime
