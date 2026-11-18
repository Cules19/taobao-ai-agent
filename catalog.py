import json
from pathlib import Path


def load_dataset(filename: str) -> list[dict]:
    path = Path(__file__).resolve().parent / "demo_data" / filename
    return json.loads(path.read_text(encoding="utf-8"))


PRODUCTS = {product["id"]: product for product in load_dataset("products.json")}
COUPONS = load_dataset("coupons.json")
ORDERS = {order["order_id"]: order for order in load_dataset("orders.json")}


def search_products(category=None, keyword=None, tags=None, min_price=None,
                    max_price=None, sort_by=None) -> dict:
    """过滤模拟商品，按需排序，最多返回 8 件。"""
    if min_price is not None and max_price is not None and min_price > max_price:
        return {"status": "invalid", "message": "最低价不能高于最高价。请确认预算区间。"}

    matches = []
    for product in PRODUCTS.values():
        if category and category != product["category"]:
            continue
        if min_price is not None and product["price"] < min_price:
            continue
        if max_price is not None and product["price"] > max_price:
            continue
        searchable = " ".join([product["name"], product["category"], product["description"],
                               *product["tags"], *product["colors"]]).casefold()
        if keyword and not all(word in searchable for word in keyword.casefold().split()):
            continue
        if tags and not set(tags).issubset(product["tags"]):
            continue
        matches.append(product)

    if sort_by:
        field = {"price_asc": "price", "price_desc": "price",
                 "sales_desc": "sales", "rating_desc": "rating"}[sort_by]
        matches.sort(key=lambda product: product[field], reverse=sort_by != "price_asc")

    if not matches:
        return {"status": "not_found", "message": "模拟商品库没有符合条件的商品。可以调整预算或筛选条件。"}
    fields = ("id", "name", "category", "price", "sales", "rating", "tags", "colors")
    return {"status": "ok", "total": len(matches),
            "products": [{field: product[field] for field in fields} for product in matches[:8]]}


def get_product_detail(product_id: str) -> dict:
    """根据商品编号返回详细字段。"""
    product = PRODUCTS.get(product_id.upper())
    if product is None:
        return {"status": "not_found", "message": "没有找到这个模拟商品编号，请确认商品。"}
    return {"status": "ok", "product": product}


def list_coupons(category=None, order_amount=None) -> dict:
    """查询活动中的券，可按适用类目和满减门槛过滤。"""
    coupons = [coupon for coupon in COUPONS
               if coupon["active"]
               and (not category or coupon["category"] in ("全场", category))
               and (order_amount is None or order_amount >= coupon["min_spend"])]
    if not coupons:
        return {"status": "not_found", "message": "没有找到符合条件的模拟优惠券。"}
    return {"status": "ok", "coupons": coupons}


def query_order(order_id: str) -> dict:
    """查询演示订单状态和物流节点。"""
    order = ORDERS.get(order_id.upper())
    if order is None:
        return {"status": "not_found", "message": "没有找到该演示订单，请核对订单编号。"}
    return {"status": "ok", "order": order}


def manage_favorites(favorites: list[str], action: str, product_id=None) -> dict:
    """在当前会话收藏商品，或列出已收藏商品。"""
    if action == "list":
        if not favorites:
            return {"status": "not_found", "message": "这个会话还没有收藏商品。"}
        return {"status": "ok", "products": [PRODUCTS[item] for item in favorites]}

    if not product_id:
        return {"status": "invalid", "message": "请说明要收藏哪一件商品。"}
    product_id = product_id.upper()
    result = get_product_detail(product_id)
    if result["status"] != "ok":
        return result
    already_favorited = product_id in favorites
    if not already_favorited:
        favorites.append(product_id)
    return {"status": "ok", "product": result["product"],
            "already_favorited": already_favorited}
