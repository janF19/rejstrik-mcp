from rejstrik.registry.models import Company, legal_form_name


def test_company_pads_ico():
    c = Company(ico="6947", name="Test s.r.o.")
    assert c.ico == "00006947"
    assert c.address is None


def test_company_keeps_full_ico():
    c = Company(ico="00006947", name="Test", address="Praha", legal_form="s.r.o.")
    assert c.ico == "00006947"
    assert c.address == "Praha"


def test_legal_form_name_maps_known_code():
    assert legal_form_name("302") == "národní podnik"
    assert legal_form_name("112") == "společnost s ručením omezeným (s.r.o.)"


def test_legal_form_name_unknown_returns_none():
    assert legal_form_name("99999") is None
    assert legal_form_name(None) is None


def test_company_carries_legal_form_name():
    c = Company(ico="00514152", name="Budvar", legal_form="302")
    c2 = Company(
        ico="00514152",
        name="Budvar",
        legal_form="302",
        legal_form_name="národní podnik",
    )
    assert c.legal_form_name is None
    assert c2.legal_form_name == "národní podnik"
