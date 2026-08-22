import importlib

from routing import HANDLERS


def tax_fn(kind):
    if kind == "digital":
        from tax.legacy import standard_vat

        return standard_vat
    path = HANDLERS[kind]
    mod, name = path.rsplit(".", 1)
    return getattr(importlib.import_module(mod), name)
