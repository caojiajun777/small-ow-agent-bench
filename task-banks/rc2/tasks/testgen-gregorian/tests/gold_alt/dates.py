import calendar

def valid_date(year, month, day):
    if not 1 <= year <= 9999 or not 1 <= month <= 12:
        return False
    return 1 <= day <= calendar.monthrange(year, month)[1]
