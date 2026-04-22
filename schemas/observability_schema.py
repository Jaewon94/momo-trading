from pydantic import BaseModel


class ErrorIncidentUpdateRequest(BaseModel):
    status: str | None = None
    owner_note: str | None = None
