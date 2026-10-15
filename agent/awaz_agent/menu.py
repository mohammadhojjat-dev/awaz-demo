"""The menu as the agent sees it: lookup by spoken name, and text for the prompt."""

from dataclasses import dataclass, field
from typing import Any

from .dari import normalize

CATEGORY_LABELS = {
    "main": "غذاها",
    "side": "کنار غذا",
    "drink": "نوشیدنی",
    "dessert": "شیرینی",
}


@dataclass(frozen=True)
class MenuItem:
    id: int
    slug: str
    name_fa: str
    name_en: str
    category: str
    price_afn: int
    aliases: tuple[str, ...] = ()
    available: bool = True

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "MenuItem":
        """Build from the backend's JSON (camelCase) or the local sample file."""
        return cls(
            id=int(data["id"]),
            slug=str(data["slug"]),
            name_fa=str(data.get("nameFa") or data.get("name_fa")),
            name_en=str(data.get("nameEn") or data.get("name_en") or ""),
            category=str(data.get("category") or "main"),
            price_afn=int(data.get("priceAfn") or data.get("price_afn")),
            aliases=tuple(data.get("aliases") or ()),
            available=bool(data.get("available", True)),
        )


@dataclass
class Menu:
    items: list[MenuItem]
    _keys: dict[str, MenuItem] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._keys = {}
        for item in self.items:
            for name in (item.slug, item.name_fa, item.name_en, *item.aliases):
                key = normalize(name)
                # The first item claims a shared alias such as "کباب"; the
                # full names below still tell items apart.
                if key and key not in self._keys:
                    self._keys[key] = item
        # Exact slugs and full names always win over another item's alias.
        for item in self.items:
            for name in (item.slug, item.name_fa, item.name_en):
                if name:
                    self._keys[normalize(name)] = item

    def by_slug(self, slug: str) -> MenuItem | None:
        return next((item for item in self.items if item.slug == slug), None)

    def resolve(self, spoken: str) -> MenuItem | None:
        """Find the item a caller (or the LLM) meant: slug, Dari or English name, or alias.

        Falls back to a unique partial match ("قابلی" inside "قابلی پلو بزرگ"),
        and returns None when nothing, or more than one item, fits.
        """
        key = normalize(spoken)
        if not key:
            return None
        if key in self._keys:
            return self._keys[key]
        partial = {item.slug: item for k, item in self._keys.items() if k in key or key in k}
        return next(iter(partial.values())) if len(partial) == 1 else None

    def prompt_text(self) -> str:
        """The menu block given to the LLM: one line per item with its id and price."""
        lines: list[str] = []
        for category, label in CATEGORY_LABELS.items():
            items = [item for item in self.items if item.category == category]
            if not items:
                continue
            lines.append(f"{label}:")
            for item in items:
                status = "" if item.available else " (امروز تمام شده — پیشنهاد نکن)"
                lines.append(
                    f"- id={item.slug} | {item.name_fa} ({item.name_en}) | {item.price_afn} افغانی{status}"
                )
        others = [item for item in self.items if item.category not in CATEGORY_LABELS]
        for item in others:
            lines.append(f"- id={item.slug} | {item.name_fa} | {item.price_afn} افغانی")
        return "\n".join(lines)

    def adaptation_phrases(self, limit: int = 100) -> list[str]:
        """Names and aliases to bias speech recognition toward menu words."""
        phrases: list[str] = []
        seen: set[str] = set()
        for item in self.items:
            for name in (item.name_fa, *item.aliases):
                key = normalize(name)
                if key and key not in seen:
                    seen.add(key)
                    phrases.append(name)
        return phrases[:limit]
