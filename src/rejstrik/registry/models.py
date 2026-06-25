from pydantic import BaseModel, field_validator


class Company(BaseModel):
    ico: str
    name: str
    address: str | None = None
    legal_form: str | None = None
    founded: str | None = None

    @field_validator("ico")
    @classmethod
    def pad_ico(cls, v: str) -> str:
        return v.strip().zfill(8)
