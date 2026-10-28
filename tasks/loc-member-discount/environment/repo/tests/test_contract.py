import pytest
from app import process, run
from pricing import list_price, member_price


def test_member_price_contract():
    for amount in (0, 7.5, 100):
        item = {"price": amount}
        assert member_price(item) == pytest.approx(amount * .9)
        assert list_price(item) == amount


def test_invoice_routes_quantity_membership_and_shipping():
    order = {"lines": [{"sku": "A", "qty": 2}, {"sku": "B", "qty": 1}], "member": True, "shipping": 3}
    assert process(order) == {"subtotal": 40.5, "shipping": 3.0, "total": 43.5}
    assert order["lines"][0]["qty"] == 2
    assert process(dict(order, member=False))["total"] == 48
    assert process({"lines": [{"sku": "FREE", "qty": 3}], "member": True})["total"] == 0
    assert run([{"price": 7.5}], True) == pytest.approx(6.75)


def test_empty_and_invalid_quantity_regressions():
    assert process({"lines": [], "shipping": 2})["total"] == 2
    with pytest.raises(ValueError):
        process({"lines": [{"sku": "A", "qty": -1}]})
