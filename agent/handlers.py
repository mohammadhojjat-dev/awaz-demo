"""The tools the ordering flow (flow.yaml) offers the LLM.

Each tool is a Flows "direct function": its name, description and parameters
come from the signature and docstring. Tools never pick the next step; they
report a `status`, and flow.yaml decides where each status leads.

All money is computed by the backend. The LLM only names items and counts.
"""

from typing import Any

from loguru import logger
from pipecat.flows import TRANSITION_IN_YAML, FlowManager

from awaz_agent.backend import Backend, BackendError
from awaz_agent.cart import Cart
from awaz_agent.dari import normalize, normalize_phone

_backend: Backend | None = None


def configure(backend: Backend) -> None:
    """Set the backend the tools use. Called once at startup by bot.py (and by tests)."""
    global _backend
    _backend = backend


def backend() -> Backend:
    if _backend is None:
        raise RuntimeError("handlers.configure(backend) was not called")
    return _backend


def initial_state(
    *,
    restaurant_name: str,
    menu_text: str,
    session_id: str,
    channel: str,
    caller_phone: str | None,
) -> dict[str, Any]:
    """Everything the prompts in flow.yaml refer to, with empty starting values."""
    phone = normalize_phone(caller_phone or "") if caller_phone else None
    return {
        "restaurant_name": restaurant_name,
        "menu_text": menu_text,
        "session_id": session_id,
        "channel": channel,
        "caller_phone": phone or "",
        "phone_instruction": (
            "The caller's phone number is already known from their call; do not ask for it."
            if phone
            else "Also ask for a phone number the restaurant can call back on."
        ),
        "cart": [],
        "cart_summary": Cart().summary(),
        "misunderstood": 0,
        "customer_name": "",
        "customer_address": "",
        "customer_landmark": "",
        "customer_phone": phone or "",
        "order_readback": "",
        "order_code": "",
        "order_id": None,
        "eta_minutes": "",
        "outcome": "abandoned",
    }


def _cart(fm: FlowManager) -> Cart:
    return Cart.from_state(fm.state.get("cart"))


def _save_cart(fm: FlowManager, cart: Cart) -> None:
    fm.state["cart"] = cart.to_state()
    fm.state["cart_summary"] = cart.summary()


def _misunderstood(fm: FlowManager, result: dict) -> dict:
    """Count misses in a row; after two, nudge the LLM toward a human callback."""
    fm.state["misunderstood"] = fm.state.get("misunderstood", 0) + 1
    if fm.state["misunderstood"] >= 2:
        result["hint"] = (
            "This is the second miss in a row. Ask once more simply, and if it is still unclear, "
            "call request_callback."
        )
    return result


async def add_item(flow_manager: FlowManager, item: str, quantity: int = 1, note: str = ""):
    """Add a menu item to the caller's order.

    Args:
        item (str): The item's id from the menu, for example "qabuli-palaw". If unsure, the item's name as the caller said it.
        quantity (int): How many the caller wants. Use 1 if they did not say.
        note (str): A request for this item such as "without onions", or empty.
    """
    menu = await backend().get_menu()
    found = menu.by_slug(item) or menu.resolve(item)
    if found is None:
        key = normalize(item)
        candidates = [
            i.name_fa
            for i in menu.items
            if key and i.available and any(key in normalize(n) for n in (i.name_fa, *i.aliases))
        ]
        result: dict[str, Any] = {"status": "unknown_item", "said": item}
        if len(candidates) > 1:
            result["status"] = "ambiguous"
            result["options"] = candidates
            result["say"] = "Ask which one the caller means."
        else:
            result["say"] = "Tell the caller this is not on the menu and suggest something similar."
        return _misunderstood(flow_manager, result), TRANSITION_IN_YAML
    if not found.available:
        return {
            "status": "unavailable",
            "item": found.name_fa,
            "say": "Tell the caller it is finished today and suggest another item.",
        }, TRANSITION_IN_YAML

    cart = _cart(flow_manager)
    try:
        cart.add(found, int(quantity), note or "")
    except ValueError as error:
        return {"status": "bad_quantity", "message": str(error)}, TRANSITION_IN_YAML
    _save_cart(flow_manager, cart)
    flow_manager.state["misunderstood"] = 0
    return {
        "status": "added",
        "item": found.name_fa,
        "quantity": int(quantity),
        "order_so_far": cart.summary(),
    }, TRANSITION_IN_YAML


async def update_item(flow_manager: FlowManager, item: str, quantity: int):
    """Change how many of an item is in the order. Use quantity 0 to remove it.

    Args:
        item (str): The item's id from the menu, or its name as the caller said it.
        quantity (int): The new total count for this item, or 0 to remove it.
    """
    menu = await backend().get_menu()
    found = menu.by_slug(item) or menu.resolve(item)
    cart = _cart(flow_manager)
    try:
        changed = found is not None and cart.set_quantity(found.slug, int(quantity))
    except ValueError as error:
        return {"status": "bad_quantity", "message": str(error)}, TRANSITION_IN_YAML
    if not changed:
        return {
            "status": "not_in_order",
            "order_so_far": cart.summary(),
            "say": "That item is not in the order; tell the caller what is.",
        }, TRANSITION_IN_YAML
    _save_cart(flow_manager, cart)
    return {"status": "updated", "order_so_far": cart.summary()}, TRANSITION_IN_YAML


async def finish_items(flow_manager: FlowManager):
    """The caller has finished choosing food and wants nothing more."""
    cart = _cart(flow_manager)
    if cart.is_empty:
        return {
            "status": "empty",
            "say": "Nothing is ordered yet; ask what the caller would like.",
        }, TRANSITION_IN_YAML
    return {"status": "ok", "order": cart.summary()}, TRANSITION_IN_YAML


async def set_customer_details(
    flow_manager: FlowManager, name: str, address: str, landmark: str = "", phone: str = ""
):
    """Save the caller's name and delivery details.

    Args:
        name (str): The caller's name.
        address (str): The delivery address as the caller said it (area, street, house).
        landmark (str): A nearby landmark such as a mosque, school, square or shop.
        phone (str): The phone number the caller gave, if they gave one.
    """
    state = flow_manager.state
    missing = [field for field, value in (("name", name), ("address", address)) if not value.strip()]
    if missing:
        return {"status": "missing", "missing": missing}, TRANSITION_IN_YAML

    caller_phone = normalize_phone(phone) if phone.strip() else None
    if phone.strip() and caller_phone is None:
        return {
            "status": "bad_phone",
            "say": "The phone number seems incomplete; ask the caller to say it again slowly.",
        }, TRANSITION_IN_YAML
    caller_phone = caller_phone or state.get("customer_phone") or state.get("caller_phone") or None
    if not caller_phone:
        return {"status": "missing", "missing": ["phone"]}, TRANSITION_IN_YAML

    state.update(
        customer_name=name.strip(),
        customer_address=address.strip(),
        customer_landmark=landmark.strip(),
        customer_phone=caller_phone,
    )
    try:
        quote = await backend().quote(_cart(flow_manager).to_order_items())
    except BackendError as error:
        logger.warning(f"Quote failed: {error}")
        return {
            "status": "item_problem",
            "message": str(error),
            "say": "Tell the caller there is a problem with one item and call change_items.",
        }, TRANSITION_IN_YAML
    state["order_readback"] = quote.readback()
    return {"status": "ok", "total_afn": quote.total_afn}, TRANSITION_IN_YAML


def _order_payload(fm: FlowManager, status: str, reason: str | None = None) -> dict:
    state = fm.state
    payload = {
        "sessionId": state["session_id"],
        "channel": state["channel"],
        "status": status,
        "items": _cart(fm).to_order_items(),
    }
    for key, field in (
        ("customerName", "customer_name"),
        ("customerPhone", "customer_phone"),
        ("address", "customer_address"),
        ("landmark", "customer_landmark"),
    ):
        if state.get(field):
            payload[key] = state[field]
    if reason:
        payload["callbackReason"] = reason[:300]
    return payload


async def confirm_order(flow_manager: FlowManager):
    """The caller confirmed the order is correct. Places the order with the restaurant."""
    try:
        result = await backend().create_order(_order_payload(flow_manager, "new"))
    except BackendError as error:
        logger.error(f"Placing the order failed: {error}")
        return {
            "status": "error",
            "say": "Apologize that the order could not be saved and call request_callback.",
        }, TRANSITION_IN_YAML
    flow_manager.state.update(
        order_code=result.code,
        order_id=result.id,
        eta_minutes=str(result.eta_minutes or ""),
        outcome="ordered",
    )
    return {"status": "ok", "order_code": result.code, "eta_minutes": result.eta_minutes}, TRANSITION_IN_YAML


async def request_callback(flow_manager: FlowManager, reason: str, phone: str = ""):
    """Hand the caller to restaurant staff, who will phone them back.

    Use when you could not understand the caller twice, they ask for a person, they are upset, or an order could not be saved.

    Args:
        reason (str): A short reason in English for the staff, such as "could not understand the address".
        phone (str): The caller's phone number, if they gave one and it is not already known.
    """
    state = flow_manager.state
    given = normalize_phone(phone) if phone.strip() else None
    callback_phone = given or state.get("customer_phone") or state.get("caller_phone")
    if not callback_phone:
        return {
            "status": "need_phone",
            "say": "Ask for a phone number so staff can call back, then call request_callback again.",
        }, TRANSITION_IN_YAML
    state["customer_phone"] = callback_phone
    try:
        await backend().create_order(_order_payload(flow_manager, "callback", reason or "callback"))
    except BackendError as error:
        # Still end politely; the call log keeps the transcript for staff.
        logger.error(f"Saving the callback request failed: {error}")
    state["outcome"] = "callback"
    return {"status": "ok"}, TRANSITION_IN_YAML
