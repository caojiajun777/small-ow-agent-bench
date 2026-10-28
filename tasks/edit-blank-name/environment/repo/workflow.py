from profile import display_name

def process(request):
    return [{"id": user["id"], "display": display_name(user) or 'guest'} for user in request["users"]]

