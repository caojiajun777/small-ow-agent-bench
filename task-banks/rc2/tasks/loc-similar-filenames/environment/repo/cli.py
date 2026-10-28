from text.normalize import clean_name
from utils.names import normalize


def save_user(name):
    return clean_name(name)


def import_contacts(records):
    return [{"id": row["id"], "display_name": save_user(row["name"]), "email_key": normalize(row["email"].strip())} for row in records]
