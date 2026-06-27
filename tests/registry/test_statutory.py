import json
from pathlib import Path

import httpx
import respx

from rejstrik.registry.statutory import (
    Officer,
    get_statutory_bodies,
    parse_statutory_bodies,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "ares" / "vr_00514152.json"


def test_parse_statutory_bodies_returns_active_officers():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    officers = parse_statutory_bodies(payload)
    assert isinstance(officers, list)
    assert all(isinstance(o, Officer) for o in officers)
    assert all(o.name for o in officers)
    assert any("ADAM" in o.name for o in officers)


@respx.mock
def test_get_statutory_bodies_returns_empty_on_error():
    respx.get(
        "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-vr/00006947"
    ).mock(return_value=httpx.Response(500))
    assert get_statutory_bodies("00006947") == []
