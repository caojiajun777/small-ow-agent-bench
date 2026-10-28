def parse_int_list(text):
    return list(map(int, filter(None, (field.strip() for field in text.split(",")))))
