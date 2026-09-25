import { create } from 'zustand';
import type { Lang, LocalizedText } from '../domain/types';
import { telegramLanguage } from '../telegram/sdk';

const ru = {
  tagline: 'Кофе и чай свежей обжарки',
  search: 'Поиск по каталогу',
  all: 'Всё',
  nothingFound: 'Ничего не нашлось',
  orderNotFound: 'Заказ не найден',
  tryAnother: 'Попробуйте другой запрос или категорию',
  from: 'от',
  new: 'новинка',
  outOfStock: 'нет в наличии',
  addToCart: 'В корзину',
  added: 'Добавлено',
  inCart: 'в корзине',
  size: 'Фасовка',
  grind: 'Помол',
  roast: 'Обжарка',
  notes: 'Вкус',
  cart: 'Корзина',
  cartEmpty: 'Корзина пуста',
  cartEmptyHint: 'Загляните в каталог — там свежая обжарка',
  toCatalog: 'В каталог',
  promo: 'Промокод',
  apply: 'Применить',
  promoUnknown: 'Такого промокода нет',
  promoApplied: 'Промокод применён',
  subtotal: 'Товары',
  discount: 'Скидка',
  delivery: 'Доставка',
  free: 'бесплатно',
  total: 'Итого',
  freeDeliveryLeft: 'До бесплатной доставки: {amount}',
  freeDeliveryReached: 'Доставка курьером бесплатно',
  checkout: 'Оформить заказ',
  checkoutTitle: 'Оформление',
  courier: 'Курьер',
  pickup: 'Самовывоз',
  address: 'Адрес доставки',
  addressPlaceholder: 'Улица, дом, квартира',
  pickupPoint: 'Точка самовывоза',
  slot: 'Когда',
  slot_asap: 'Как можно скорее',
  slot_morning: 'Утром, 9–12',
  slot_evening: 'Вечером, 18–21',
  contacts: 'Получатель',
  name: 'Имя',
  phone: 'Телефон',
  comment: 'Комментарий к заказу',
  payment: 'Оплата',
  pay_stars: 'Telegram Stars',
  pay_stars_hint: 'Мгновенная оплата в Telegram',
  pay_on_receipt: 'При получении',
  pay_on_receipt_hint: 'Картой или наличными',
  placeOrder: 'Заказать',
  payStars: 'Оплатить {stars} ⭐',
  required: 'Заполните поле',
  badPhone: 'Нужно 10–15 цифр',
  orderPlaced: 'Заказ оформлен',
  orderPaid: 'Заказ оплачен',
  awaitingPayment: 'Ожидает оплаты',
  thanks: 'Спасибо! Мы уже собираем ваш заказ.',
  payNow: 'Оплатить',
  paymentCancelled: 'Оплата отменена — можно оплатить позже из истории заказов',
  orders: 'Мои заказы',
  noOrders: 'Заказов пока нет',
  noOrdersHint: 'Здесь появится история ваших покупок',
  order: 'Заказ',
  items: 'Состав',
  back: 'Назад',
  goShopping: 'За покупками',
  demoNote: 'Демо-проект: вымышленный магазин, оплата и данные имитируются в браузере.',
  error: 'Что-то пошло не так',
  retry: 'Повторить',
  status_awaiting_payment: 'Ждёт оплаты',
  status_new: 'Принят',
  status_paid: 'Оплачен',
  status_confirmed: 'Подтверждён',
  status_in_delivery: 'В пути',
  status_ready_for_pickup: 'Готов к выдаче',
  status_completed: 'Выполнен',
  status_cancelled: 'Отменён',
  status_refunded: 'Возврат',
  demoInvoiceTitle: 'Оплата звёздами',
  demoInvoiceHint: 'Демо-режим: в Telegram здесь откроется нативное окно оплаты Stars.',
  confirmPay: 'Подтвердить оплату',
  cancel: 'Отмена',
  itemsCount: '{n} шт.',
  quantity: 'Количество',
  serverPriced: 'Цены пересчитываются на сервере при оформлении',
  promoPlaceholder: 'Например, ZERNO10',
};

type Dict = typeof ru;
export type MessageKey = keyof Dict;

const en: Dict = {
  tagline: 'Freshly roasted coffee & tea',
  search: 'Search the catalog',
  all: 'All',
  nothingFound: 'Nothing found',
  orderNotFound: 'Order not found',
  tryAnother: 'Try another query or category',
  from: 'from',
  new: 'new',
  outOfStock: 'out of stock',
  addToCart: 'Add to cart',
  added: 'Added',
  inCart: 'in cart',
  size: 'Size',
  grind: 'Grind',
  roast: 'Roast',
  notes: 'Notes',
  cart: 'Cart',
  cartEmpty: 'Your cart is empty',
  cartEmptyHint: 'Take a look at the catalog — fresh roasts inside',
  toCatalog: 'Browse catalog',
  promo: 'Promo code',
  apply: 'Apply',
  promoUnknown: 'Unknown promo code',
  promoApplied: 'Promo code applied',
  subtotal: 'Items',
  discount: 'Discount',
  delivery: 'Delivery',
  free: 'free',
  total: 'Total',
  freeDeliveryLeft: '{amount} more for free delivery',
  freeDeliveryReached: 'Courier delivery is free',
  checkout: 'Checkout',
  checkoutTitle: 'Checkout',
  courier: 'Courier',
  pickup: 'Pickup',
  address: 'Delivery address',
  addressPlaceholder: 'Street, building, apartment',
  pickupPoint: 'Pickup point',
  slot: 'When',
  slot_asap: 'As soon as possible',
  slot_morning: 'Morning, 9–12',
  slot_evening: 'Evening, 6–9pm',
  contacts: 'Recipient',
  name: 'Name',
  phone: 'Phone',
  comment: 'Order comment',
  payment: 'Payment',
  pay_stars: 'Telegram Stars',
  pay_stars_hint: 'Instant in-app payment',
  pay_on_receipt: 'On receipt',
  pay_on_receipt_hint: 'Card or cash',
  placeOrder: 'Place order',
  payStars: 'Pay {stars} ⭐',
  required: 'Required',
  badPhone: '10–15 digits expected',
  orderPlaced: 'Order placed',
  orderPaid: 'Order paid',
  awaitingPayment: 'Awaiting payment',
  thanks: 'Thank you! We are already packing your order.',
  payNow: 'Pay now',
  paymentCancelled: 'Payment cancelled — you can pay later from your order history',
  orders: 'My orders',
  noOrders: 'No orders yet',
  noOrdersHint: 'Your purchase history will appear here',
  order: 'Order',
  items: 'Items',
  back: 'Back',
  goShopping: 'Go shopping',
  demoNote: 'Demo project: a fictional shop; payments and data are simulated in the browser.',
  error: 'Something went wrong',
  retry: 'Retry',
  status_awaiting_payment: 'Awaiting payment',
  status_new: 'Accepted',
  status_paid: 'Paid',
  status_confirmed: 'Confirmed',
  status_in_delivery: 'On the way',
  status_ready_for_pickup: 'Ready for pickup',
  status_completed: 'Completed',
  status_cancelled: 'Cancelled',
  status_refunded: 'Refunded',
  demoInvoiceTitle: 'Pay with Stars',
  demoInvoiceHint: 'Demo mode: inside Telegram the native Stars payment sheet opens here.',
  confirmPay: 'Confirm payment',
  cancel: 'Cancel',
  itemsCount: '{n} pcs',
  quantity: 'Quantity',
  serverPriced: 'Prices are re-calculated by the server at checkout',
  promoPlaceholder: 'e.g. ZERNO10',
};

const dicts: Record<Lang, Dict> = { ru, en };

function initialLang(): Lang {
  try {
    const saved = localStorage.getItem('zernolist.lang');
    if (saved === 'ru' || saved === 'en') return saved;
  } catch {
    /* ignore */
  }
  const code = telegramLanguage() ?? (typeof navigator !== 'undefined' ? navigator.language : 'ru');
  return code?.toLowerCase().startsWith('ru') ? 'ru' : code ? 'en' : 'ru';
}

export const useLang = create<{ lang: Lang; setLang: (l: Lang) => void }>((set) => ({
  lang: initialLang(),
  setLang: (lang) => {
    try {
      localStorage.setItem('zernolist.lang', lang);
    } catch {
      /* ignore */
    }
    document.documentElement.lang = lang;
    set({ lang });
  },
}));

export type Translate = (key: MessageKey, vars?: Record<string, string | number>) => string;

export function useT(): { t: Translate; lang: Lang; l: (text: LocalizedText) => string } {
  const lang = useLang((s) => s.lang);
  const dict = dicts[lang];
  const t: Translate = (key, vars) =>
    dict[key].replace(/\{(\w+)\}/g, (_, name: string) => String(vars?.[name] ?? ''));
  return { t, lang, l: (text) => text[lang] };
}
