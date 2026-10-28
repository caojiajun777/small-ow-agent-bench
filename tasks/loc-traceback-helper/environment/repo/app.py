from loader import load_records


def report(path):
    try:
        rows = load_records(path)
    except Exception as exc:
        raise RuntimeError("load failed") from exc
    return {"rows": rows, "missing": sum(row["amount"] is None for row in rows), "total": sum(row["amount"] for row in rows if row["amount"] is not None)}


def process(request):
    return report(request.get("path", "data/records.txt"))


def main():
    return process({})


if __name__ == "__main__":
    print(main())
