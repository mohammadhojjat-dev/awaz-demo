"""The caller's order while the call is in progress.

It lives in the Flows state as plain JSON so prompts can show it and nothing
is lost between conversation steps. Prices here are only for the running
summary; the backend recomputes every price before the order is saved.
"""

from dataclasses import asdict, dataclass

from .menu import MenuItem

MAX_QUANTITY = 50


@dataclass
class CartLine:
    slug: str
    name_fa: str
    unit_price_afn: int
    quantity: int
    note: str = ""

    @property
    def line_total_afn(self) -> int:
        return self.unit_price_afn * self.quantity


class Cart:
    def __init__(self, lines: list[CartLine] | None = None):
        self.lines: list[CartLine] = lines or []

    @classmethod
    def from_state(cls, data: list[dict] | None) -> "Cart":
        return cls([CartLine(**line) for line in data or []])

    def to_state(self) -> list[dict]:
        return [asdict(line) for line in self.lines]

    def _find(self, slug: str, note: str) -> CartLine | None:
        return next((ln for ln in self.lines if ln.slug == slug and ln.note == note), None)

    def add(self, item: MenuItem, quantity: int, note: str = "") -> CartLine:
        """Add an item; the same item with the same note just increases the count."""
        if quantity < 1 or quantity > MAX_QUANTITY:
            raise ValueError(f"quantity must be between 1 and {MAX_QUANTITY}")
        note = note.strip()
        line = self._find(item.slug, note)
        if line:
            if line.quantity + quantity > MAX_QUANTITY:
                raise ValueError(f"quantity must be between 1 and {MAX_QUANTITY}")
            line.quantity += quantity
            return line
        line = CartLine(item.slug, item.name_fa, item.price_afn, quantity, note)
        self.lines.append(line)
        return line

    def set_quantity(self, slug: str, quantity: int) -> bool:
        """Set the total count of an item; 0 removes it. False if it is not in the order."""
        if quantity < 0 or quantity > MAX_QUANTITY:
            raise ValueError(f"quantity must be between 0 and {MAX_QUANTITY}")
        matching = [ln for ln in self.lines if ln.slug == slug]
        if not matching:
            return False
        # Keep the first line (and its note), drop any duplicates of the same item.
        first = matching[0]
        self.lines = [ln for ln in self.lines if ln.slug != slug or ln is first]
        if quantity == 0:
            self.lines.remove(first)
        else:
            first.quantity = quantity
        return True

    @property
    def is_empty(self) -> bool:
        return not self.lines

    @property
    def subtotal_afn(self) -> int:
        return sum(line.line_total_afn for line in self.lines)

    def summary(self) -> str:
        """One line per item, in Dari, for prompts and tool results."""
        if not self.lines:
            return "هنوز چیزی سفارش داده نشده."
        parts = []
        for line in self.lines:
            note = f" ({line.note})" if line.note else ""
            parts.append(f"{line.quantity} × {line.name_fa}{note}")
        return "، ".join(parts)

    def to_order_items(self) -> list[dict]:
        """The shape the backend expects: names and counts only, never prices."""
        items = []
        for line in self.lines:
            item = {"slug": line.slug, "quantity": line.quantity}
            if line.note:
                item["note"] = line.note
            items.append(item)
        return items
