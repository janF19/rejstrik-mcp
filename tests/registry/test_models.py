from rejstrik.registry.models import Company


def test_company_pads_ico():
    c = Company(ico="6947", name="Test s.r.o.")
    assert c.ico == "00006947"
    assert c.address is None


def test_company_keeps_full_ico():
    c = Company(ico="00006947", name="Test", address="Praha", legal_form="s.r.o.")
    assert c.ico == "00006947"
    assert c.address == "Praha"
