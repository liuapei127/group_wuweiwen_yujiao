from app.modules.consultant.service import ALLOWED_TRANSITIONS


def test_signed_terminal():
    assert ALLOWED_TRANSITIONS["signed"] == set()


def test_new_can_contact():
    assert "contacting" in ALLOWED_TRANSITIONS["new"]


def test_lost_can_return_to_contacting():
    assert ALLOWED_TRANSITIONS["lost"] == {"contacting"}
