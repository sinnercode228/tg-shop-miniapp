"""User-facing bot texts (Russian — the shop's primary language)."""

from __future__ import annotations

from html import escape

from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import DeliveryMethod, DeliverySlot, OrderStatus, PaymentMethod
from tgshop.domain.schemas import OrderOut

STATUS_LABELS: dict[OrderStatus, str] = {
    OrderStatus.AWAITING_PAYMENT: "⏳ Ожидает оплаты",
    OrderStatus.NEW: "🆕 Новый",
    OrderStatus.PAID: "💫 Оплачен",
    OrderStatus.CONFIRMED: "✅ Подтверждён",
    OrderStatus.IN_DELIVERY: "🚚 В пути",
    OrderStatus.READY_FOR_PICKUP: "📦 Готов к выдаче",
    OrderStatus.COMPLETED: "🎉 Выполнен",
    OrderStatus.CANCELLED: "✖️ Отменён",
    OrderStatus.REFUNDED: "↩️ Возврат",
}

SLOT_LABELS: dict[DeliverySlot, str] = {
    DeliverySlot.ASAP: "как можно скорее",
    DeliverySlot.MORNING: "10:00–14:00",
    DeliverySlot.EVENING: "18:00–22:00",
}

WELCOME = (
    "<b>Зернолист</b> — кофе свежей обжарки и чай в Telegram.\n\n"
    "Откройте витрину кнопкой ниже: каталог, корзина и оформление заказа — прямо в чате.\n\n"
    "<i>Демо-проект: магазин вымышленный, заказы не доставляются.</i>"
)

HELP = (
    "/start — открыть магазин\n"
    "/myorders — мои заказы\n"
    "/paysupport — вопросы по оплате\n"
    "/help — эта справка"
)

PAY_SUPPORT = (
    "По вопросам оплаты Telegram Stars напишите номер заказа в ответ на это сообщение — "
    "администратор проверит платёж и при необходимости оформит возврат."
)

ADMIN_HELP = (
    "<b>Команды администратора</b>\n"
    "/orders [статус|all] — последние заказы\n"
    "/order &lt;id&gt; — карточка заказа\n"
    "/status &lt;id&gt; &lt;статус&gt; — сменить статус\n"
    "/refund &lt;id&gt; — вернуть Stars\n\n"
    "Статусы: " + ", ".join(s.value for s in OrderStatus)
)


def money(kopecks: int) -> str:
    rub, kop = divmod(kopecks, 100)
    whole = f"{rub:,}".replace(",", " ")
    return f"{whole} ₽" if kop == 0 else f"{whole},{kop:02d} ₽"


def order_summary(order: OrderOut, catalog: Catalog, *, for_admin: bool = False) -> str:
    lines = [f"<b>Заказ №{order.id}</b> · {STATUS_LABELS[order.status]}", ""]
    for item in order.items:
        grind = ""
        if item.grind:
            grind = f", {escape(catalog.grind(item.grind).name.ru.lower())}"
        lines.append(
            f"• {escape(item.title)} ({escape(item.variant_label)}{grind}) × {item.quantity}"
            f" — {money(item.unit_price * item.quantity)}"
        )
    lines.append("")
    if order.discount:
        lines.append(f"Скидка ({escape(order.promo_code or '')}): −{money(order.discount)}")
    if order.delivery_method is DeliveryMethod.COURIER:
        fee = money(order.delivery_fee) if order.delivery_fee else "бесплатно"
        lines.append(f"Доставка: {fee}")
    lines.append(f"<b>Итого: {money(order.total)}</b>")
    if order.payment_method is PaymentMethod.STARS and order.stars_amount:
        lines.append(f"Оплата: {order.stars_amount} ⭐ Telegram Stars")
    else:
        lines.append("Оплата: при получении")

    if order.delivery_method is DeliveryMethod.COURIER:
        where = f"🚚 Курьер: {escape(order.address or '')} ({SLOT_LABELS[order.delivery_slot]})"
    else:
        point = catalog.pickup_point(order.pickup_point_id or "")
        where = f"🏪 Самовывоз: {escape(point.name.ru)}"
    lines += ["", where]

    if for_admin:
        lines.append(f"👤 {escape(order.customer_name)}, <code>{escape(order.phone)}</code>")
        lines.append(f'<a href="tg://user?id={order.user_id}">Написать клиенту</a>')
        if order.comment:
            lines.append(f"💬 {escape(order.comment)}")
    return "\n".join(lines)


def status_update(order: OrderOut) -> str:
    return f"Заказ №{order.id}: {STATUS_LABELS[order.status]}"
