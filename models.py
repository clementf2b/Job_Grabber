"""Job data model."""
import dataclasses
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class Job:
    title: str
    company: str
    location: str
    source: str
    url: str
    description: Optional[str] = None
    salary: Optional[str] = None
    job_type: Optional[str] = None
    posted_at: Optional[str] = None
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)
