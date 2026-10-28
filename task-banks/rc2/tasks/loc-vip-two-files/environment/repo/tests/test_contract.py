import pytest
from app import process
from checkout import charge
from discounts.legacy import promo_price
from pricing.vip import vip_price


def test_strategy_contract_and_standard_regressions():
    for price in (0, 7.5, 100):
        item = {"price": price}
        assert vip_price(item) == pytest.approx(price * .8)
        assert charge(item, True) == pytest.approx(price * .8)
        assert charge(item, False) == price
        assert promo_price(item) == price


def test_order_call_chain_and_shipping():
    order = {"lines": [{"sku": "A", "price": 10, "qty": 2}, {"sku": "B", "price": 25, "qty": 1}], "vip": True, "shipping": 3}
    assert process(order) == {"lines": [{"sku": "A", "total": 16.0}, {"sku": "B", "total": 20.0}], "subtotal": 36.0, "total": 39.0}
    assert process(dict(order, vip=False))["total"] == 48
    assert process({"lines": [], "vip": True, "shipping": 2})["total"] == 2
