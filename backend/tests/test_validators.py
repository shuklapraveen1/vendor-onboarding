from app.matching import compare_names
from app.validators import india


def test_gstin_valid_and_checksum():
    res = india.validate_gstin("29AABCK4127M1ZA")
    assert res.valid
    assert res.details["state"] == "Karnataka"
    assert res.details["embedded_pan"] == "AABCK4127M"


def test_gstin_transposition_caught_by_checksum():
    res = india.validate_gstin("27AAKCS7371Q1ZH")
    assert not res.valid
    assert "check digit" in res.reason


def test_gstin_bad_state_and_length():
    assert not india.validate_gstin("98AABCK4127M1ZA").valid
    assert not india.validate_gstin("29AABCK4127M1Z").valid


def test_gstin_accepts_spaces_and_lowercase():
    assert india.validate_gstin(" 29aabck4127m1za ").valid


def test_pan_types():
    assert india.validate_pan("AABCK4127M").details["holder_type"] == "Company"
    assert not india.validate_pan("AABXK4127M").valid  # X is not a holder type
    assert not india.validate_pan("AABC4127M").valid


def test_cin_parsing():
    res = india.validate_cin("U29100KA2015PTC081234")
    assert res.valid and res.details["ownership"] == "PTC" and res.details["year"] == "2015"
    assert not india.validate_cin("U29100ZZ2015PTC081234").valid


def test_ifsc_phone_pincode():
    assert india.validate_ifsc("HDFC0000523").valid
    assert not india.validate_ifsc("HDFC1000523").valid  # 5th char must be 0
    assert india.validate_phone("+91 98450 12345").value == "9845012345"
    assert not india.validate_phone("1234567890").valid
    assert not india.validate_pincode("012345").valid


def test_name_suffix_normalisation():
    m = compare_names("Kaveri Precision Components Private Limited", "KAVERI PRECISION COMPONENTS PVT LTD")
    assert m.verdict == "exact"


def test_name_m_s_prefix_and_ampersand():
    assert compare_names("M/s. Deccan Paper & Packaging Pvt. Ltd.", "DECCAN PAPER AND PACKAGING PRIVATE LIMITED").is_match


def test_different_legal_form_is_not_a_match():
    m = compare_names("Acme Traders LLP", "Acme Traders Pvt Ltd")
    assert m.verdict == "partial" and not m.is_match


def test_unrelated_names_mismatch():
    assert compare_names("Tungabhadra Steel Fabricators Pvt Ltd", "RAVI KUMAR ENTERPRISES").verdict == "mismatch"


def test_truncated_bank_name():
    assert compare_names("Tungabhadra Steel Fabricators Private Limited", "TUNGABHADRA STEEL FABRICATORS").is_match
