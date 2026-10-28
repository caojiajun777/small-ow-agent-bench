import pytest
from app import process
from invoice import invoice_total
from tax import with_tax


def test_public_tax_api_for_sales_and_credits():
    for net in (0, 7.5, 100, -20):
        assert with_tax(net) == pytest.approx(net * 1.1)
        assert invoice_total(net) == pytest.approx(net * 1.1)


def test_quantity_discount_and_exempt_shipping():
    order = {"lines": [{"price": 50, "qty": 2}, {"price": 20, "qty": 1}], "discount": .25, "shipping": 4}
    result = process(order)
    assert result["net"] == 90
    assert result["tax"] == pytest.approx(9)
    assert result["total"] == pytest.approx(103)
    assert order["lines"][0]["price"] == 50
    assert process({"lines": [], "shipping": 5})["total"] == 5
