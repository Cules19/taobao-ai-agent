import pytest

import catalog


@pytest.mark.parametrize("sort_by,expected", [
    ("price_asc", ["P101", "P102", "P103"]),
    ("price_desc", ["P103", "P102", "P101"]),
    ("sales_desc", ["P102", "P101", "P103"]),
    ("rating_desc", ["P102", "P101", "P103"]),
])
def test_search_applies_budget_keyword_and_sort(sort_by, expected):
    result = catalog.search_products(category="耳机", keyword="蓝牙", min_price=100,
                                     max_price=200, sort_by=sort_by)
    assert [product["id"] for product in result["products"]] == expected


def test_search_applies_all_tags_and_handles_no_results():
    result = catalog.search_products(tags=["运动", "防水"], max_price=200)
    assert [product["id"] for product in result["products"]] == ["P102"]
    assert catalog.search_products(category="耳机", max_price=1)["status"] == "not_found"
    assert catalog.search_products(min_price=200, max_price=100)["status"] == "invalid"


def test_detail_uses_catalog_fields():
    product = catalog.get_product_detail("p102")["product"]
    assert (product["price"], product["stock"], product["rating"]) == (179, 83, 98)
    assert catalog.get_product_detail("P999")["status"] == "not_found"


def test_coupon_checks_amount_category_and_activity():
    assert [coupon["id"] for coupon in catalog.list_coupons("耳机", 179)["coupons"]] == ["C02"]
    assert [coupon["id"] for coupon in catalog.list_coupons("键盘", 400)["coupons"]] == ["C01"]
    assert catalog.list_coupons("耳机", 99)["status"] == "not_found"


def test_order_returns_status_and_tracking():
    order = catalog.query_order("demo1001")["order"]
    assert order["status"] == "运输中"
    assert order["tracking"][-1]["event"] == "到达上海分拨中心"
    assert catalog.query_order("DEMO9999")["status"] == "not_found"


def test_favorites_only_add_existing_products_once():
    favorites = []
    assert catalog.manage_favorites(favorites, "add")["status"] == "invalid"
    assert catalog.manage_favorites(favorites, "add", "P999")["status"] == "not_found"
    assert not catalog.manage_favorites(favorites, "add", "p102")["already_favorited"]
    assert catalog.manage_favorites(favorites, "add", "P102")["already_favorited"]
    assert [item["id"] for item in catalog.manage_favorites(favorites, "list")["products"]] == ["P102"]
