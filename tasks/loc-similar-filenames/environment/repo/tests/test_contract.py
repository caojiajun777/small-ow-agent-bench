from app import process
from cli import save_user
from text.normalize import clean_name
from utils.names import normalize


def test_active_name_api():
    assert clean_name("  Ada\t  Lovelace\n") == "Ada Lovelace"
    assert save_user("A\u2003\u2003B") == "A B"
    assert save_user(" \t\n") == ""
    assert save_user("Jean-Luc  O'Neil") == "Jean-Luc O'Neil"


def test_contact_import_preserves_non_name_contracts():
    request = {"contacts": [{"id": 7, "name": " Grace  HOPPER ", "email": " G@EXAMPLE.COM "}, {"id": 2, "name": "", "email": "B@X"}]}
    assert process(request) == {"contacts": [{"id": 7, "display_name": "Grace HOPPER", "email_key": "g@example.com"}, {"id": 2, "display_name": "", "email_key": "b@x"}]}
    assert normalize("Two  Words") == "two  words"
    assert request["contacts"][0]["name"] == " Grace  HOPPER "
