import pytest

from awaz_agent.cart import Cart
from awaz_agent.dari import normalize, normalize_phone, to_ascii_digits


def test_normalize_treats_arabic_and_persian_letters_alike():
    assert normalize("كباب كوبيده") == normalize("کباب کوبیده")
    assert normalize("قابلی‌پلو") == normalize("قابلی پلو")
    assert normalize("  Qabuli   PALAW ") == "qabuli palaw"


def test_digits_and_phone_numbers():
    assert to_ascii_digits("۰۷۹۹ ١٢٣") == "0799 123"
    assert normalize_phone("۰۷۹۹ ۱۲۳ ۴۵۶") == "0799123456"
    assert normalize_phone("+93 799-123-456") == "+93799123456"
    assert normalize_phone("0093799123456") == "+93799123456"
    assert normalize_phone("12345") is None


@pytest.mark.parametrize(
    ("spoken", "slug"),
    [
        ("qabuli-palaw", "qabuli-palaw"),
        ("قابلی پلو", "qabuli-palaw"),
        ("کابلی", "qabuli-palaw"),
        ("Mantu", "mantu"),
        ("مانتو", "mantu"),
        ("كوبيده", "kabab-kobide"),
        ("یک قابلی پلو بزرگ", "qabuli-palaw"),
        ("coke", "cola"),
    ],
)
def test_menu_resolves_what_callers_say(menu, spoken, slug):
    assert menu.resolve(spoken).slug == slug


def test_menu_refuses_to_guess(menu):
    assert menu.resolve("پیتزا") is None
    # Two kebabs are on the menu, so plain "kebab" must be asked about, not guessed.
    assert menu.resolve("کباب") is None
    assert menu.resolve("") is None


def test_menu_prompt_and_speech_hints(menu):
    text = menu.prompt_text()
    assert "id=qabuli-palaw | قابلی پلو (Qabuli palaw) | 250 افغانی" in text
    assert text.index("غذاها:") < text.index("نوشیدنی:")
    phrases = menu.adaptation_phrases()
    assert "قابلی پلو" in phrases and "مانتو" in phrases
    assert len(phrases) == len(set(map(normalize, phrases)))


def test_cart_adds_merges_and_updates(menu):
    cart = Cart()
    qabuli, doogh = menu.by_slug("qabuli-palaw"), menu.by_slug("doogh")
    cart.add(qabuli, 1)
    cart.add(qabuli, 2)
    cart.add(qabuli, 1, note="بدون کشمش")
    cart.add(doogh, 2)
    assert [(ln.slug, ln.quantity, ln.note) for ln in cart.lines] == [
        ("qabuli-palaw", 3, ""),
        ("qabuli-palaw", 1, "بدون کشمش"),
        ("doogh", 2, ""),
    ]
    assert cart.subtotal_afn == 4 * 250 + 2 * 50
    assert cart.summary() == "3 × قابلی پلو، 1 × قابلی پلو (بدون کشمش)، 2 × دوغ"

    # Setting a count merges duplicate lines of the same item into one.
    assert cart.set_quantity("qabuli-palaw", 2)
    assert [(ln.slug, ln.quantity) for ln in cart.lines] == [("qabuli-palaw", 2), ("doogh", 2)]
    assert cart.set_quantity("doogh", 0)
    assert not cart.set_quantity("mantu", 1)
    assert cart.to_order_items() == [{"slug": "qabuli-palaw", "quantity": 2}]


def test_cart_round_trips_through_flow_state(menu):
    cart = Cart()
    cart.add(menu.by_slug("mantu"), 2, note="تند")
    restored = Cart.from_state(cart.to_state())
    assert restored.to_order_items() == [{"slug": "mantu", "quantity": 2, "note": "تند"}]


def test_cart_rejects_silly_quantities(menu):
    cart = Cart()
    with pytest.raises(ValueError):
        cart.add(menu.by_slug("naan"), 0)
    with pytest.raises(ValueError):
        cart.add(menu.by_slug("naan"), 51)
    assert Cart().summary() == "هنوز چیزی سفارش داده نشده."
