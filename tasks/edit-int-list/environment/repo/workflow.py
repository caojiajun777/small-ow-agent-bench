from parse import parse_int_list

def process(request):
    ids = parse_int_list(request["ids"])
    lookup = {row["id"]: row for row in request["rows"]}
    return [dict(lookup[ident]) for ident in sorted(set(ids)) if ident in lookup]

