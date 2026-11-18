import json
import logging
from time import perf_counter
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

import catalog

logger = logging.getLogger("uvicorn.error.shop_tools")

Category = Literal["耳机", "背包", "水杯", "键盘", "台灯", "充电宝"]
Amount = Annotated[float, Field(ge=0, le=1_000_000)]
ProductId = Annotated[str, Field(pattern=r"^[Pp][0-9]{3}$")]
OrderId = Annotated[str, Field(pattern=r"^[Dd][Ee][Mm][Oo][0-9]{4}$")]


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)


class SearchArguments(ToolArguments):
    category: Category | None = None
    keyword: str | None = Field(default=None, max_length=80, description="简短关键词；空格分隔时要求全部匹配")
    tags: list[str] | None = Field(default=None, max_length=5, description="精确卖点标签，如 运动、防水、主动降噪")
    min_price: Amount | None = None
    max_price: Amount | None = None
    sort_by: Literal["price_asc", "price_desc", "sales_desc", "rating_desc"] | None = None


class DetailArguments(ToolArguments):
    product_id: ProductId


class CouponArguments(ToolArguments):
    category: Category | None = None
    order_amount: Amount | None = None


class OrderArguments(ToolArguments):
    order_id: OrderId


class FavoriteArguments(ToolArguments):
    action: Literal["add", "list"]
    product_id: ProductId | None = None


TOOL_REGISTRY = {
    "search_products": (SearchArguments, catalog.search_products,
                        "搜索模拟商品，按类目、关键词、标签、预算过滤，可按价格、销量、好评率排序。"),
    "get_product_detail": (DetailArguments, catalog.get_product_detail,
                           "按编号查询商品价格、销量、好评率、库存、颜色和卖点；商品不明确时先问。"),
    "list_coupons": (CouponArguments, catalog.list_coupons,
                     "查活动中的模拟满减券与品类券；可传类目和订单金额，金额未知可省略。"),
    "query_order": (OrderArguments, catalog.query_order,
                    "按 DEMO 加四位数字的演示订单号查状态及物流；缺订单号时先问。"),
    "manage_favorites": (FavoriteArguments, catalog.manage_favorites,
                         "用户明确要求收藏时用 add 和商品编号；查看当前会话收藏时用 list。"),
}

TOOLS = [
    {"type": "function", "function": {"name": name, "description": description,
     "parameters": schema.model_json_schema()}}
    for name, (schema, function, description) in TOOL_REGISTRY.items()
]

ARGUMENT_HINTS = {
    "search_products": "请确认要找的商品、预算区间或排序方式。",
    "get_product_detail": "请提供商品编号，例如 P102，或说明你指哪一件。",
    "list_coupons": "请确认商品类目或订单金额。",
    "query_order": "请提供演示订单号，例如 DEMO1001。",
    "manage_favorites": "请说明要收藏哪一件商品，或是否要查看收藏。",
}


def execute_tool(name: str, raw_arguments: str, favorites: list[str]) -> dict:
    """校验模型的 JSON 参数，只运行注册表中的函数，并记录耗时。"""
    start = perf_counter()
    result = {"status": "error", "message": "工具暂时不可用，请稍后再试。"}
    arguments_for_log = "<未通过校验>"
    log_name = name if name in TOOL_REGISTRY else "<未知工具>"
    try:
        if name not in TOOL_REGISTRY:
            return result
        schema, function, _ = TOOL_REGISTRY[name]
        try:
            arguments = schema.model_validate_json(raw_arguments).model_dump(exclude_none=True)
        except ValidationError:
            result = {"status": "invalid", "message": ARGUMENT_HINTS[name]}
            return result

        logged = {key: ("<省略>" if key in {"keyword", "tags"} else value)
                  for key, value in arguments.items()}
        arguments_for_log = json.dumps(logged, ensure_ascii=False)
        if name == "manage_favorites":
            result = function(favorites, **arguments)
        else:
            result = function(**arguments)
        return result
    except Exception as error:
        logger.warning("tool_failure name=%s error_type=%s", log_name, type(error).__name__)
        return result
    finally:
        logger.info("tool=%s args=%s elapsed_ms=%.2f status=%s", log_name,
                    arguments_for_log, (perf_counter() - start) * 1000, result["status"])
