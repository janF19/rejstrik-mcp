from pydantic import BaseModel, field_validator

# Common ARES právní forma (legal form) codes → Czech names. Not exhaustive;
# unknown codes surface as None so the raw legal_form code is still available.
LEGAL_FORM_NAMES: dict[str, str] = {
    "101": "OSVČ (živnostník)",
    "111": "veřejná obchodní společnost (v.o.s.)",
    "112": "společnost s ručením omezeným (s.r.o.)",
    "113": "komanditní společnost (k.s.)",
    "121": "akciová společnost (a.s.)",
    "205": "družstvo",
    "301": "státní podnik",
    "302": "národní podnik",
    "421": "odštěpný závod zahraniční právnické osoby",
    "641": "spolek",
    "801": "obec",
}


def legal_form_name(code: str | None) -> str | None:
    """Map an ARES legal-form code to its Czech name, or None if unknown."""
    if code is None:
        return None
    return LEGAL_FORM_NAMES.get(code.strip())


class Company(BaseModel):
    ico: str
    name: str
    address: str | None = None
    legal_form: str | None = None
    legal_form_name: str | None = None
    founded: str | None = None

    @field_validator("ico")
    @classmethod
    def pad_ico(cls, v: str) -> str:
        return v.strip().zfill(8)
