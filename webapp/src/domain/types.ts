/** Wire types shared with the FastAPI backend (camelCase JSON). Money is integer kopecks. */

export type Lang = 'ru' | 'en';
export interface LocalizedText {
  ru: string;
  en: string;
}

export interface Category {
  id: string;
  name: LocalizedText;
}
export interface GrindOption {
  id: string;
  name: LocalizedText;
}
export interface PickupPoint {
  id: string;
  name: LocalizedText;
  hours: LocalizedText;
}
export interface Variant {
  id: string;
  label: LocalizedText;
  price: number;
}
export type ArtKind = 'bag' | 'drip' | 'tin' | 'dripper' | 'filters' | 'kettle' | 'gaiwan';
export interface Product {
  id: string;
  categoryId: string;
  name: LocalizedText;
  subtitle: LocalizedText;
  description: LocalizedText;
  notes: LocalizedText[];
  roast?: number | null;
  grindable: boolean;
  badge?: 'new' | null;
  inStock?: boolean;
  art: { kind: ArtKind | string; colors: string[] };
  variants: Variant[];
}
export interface Catalog {
  categories: Category[];
  grindOptions: GrindOption[];
  pickupPoints: PickupPoint[];
  deliveryWindows: Record<Exclude<DeliverySlot, 'asap'>, string>;
  products: Product[];
}

export type DeliveryMethod = 'courier' | 'pickup';
export type PaymentMethod = 'stars' | 'on_receipt';
export type DeliverySlot = 'asap' | 'morning' | 'evening';
export type OrderStatus =
  | 'awaiting_payment'
  | 'new'
  | 'paid'
  | 'confirmed'
  | 'in_delivery'
  | 'ready_for_pickup'
  | 'completed'
  | 'cancelled'
  | 'refunded';

export interface CartItemIn {
  productId: string;
  variantId: string;
  grind?: string | null;
  quantity: number;
}

export interface QuoteRequest {
  items: CartItemIn[];
  deliveryMethod: DeliveryMethod;
  promoCode?: string | null;
}

export interface Quote {
  subtotal: number;
  discount: number;
  deliveryFee: number;
  total: number;
  stars: number;
  promoCode: string | null;
  promoError: 'unknown' | null;
}

export interface OrderCreate extends QuoteRequest {
  customer: { name: string; phone: string };
  address?: string | null;
  pickupPointId?: string | null;
  deliverySlot: DeliverySlot;
  comment?: string | null;
  paymentMethod: PaymentMethod;
}

export interface OrderItem {
  productId: string;
  variantId: string;
  grind: string | null;
  title: string;
  variantLabel: string;
  unitPrice: number;
  quantity: number;
}

export interface Order {
  id: number;
  userId: number;
  status: OrderStatus;
  source: 'api' | 'web_app_data';
  customerName: string;
  phone: string;
  deliveryMethod: DeliveryMethod;
  address: string | null;
  pickupPointId: string | null;
  deliverySlot: DeliverySlot;
  comment: string | null;
  paymentMethod: PaymentMethod;
  promoCode: string | null;
  subtotal: number;
  discount: number;
  deliveryFee: number;
  total: number;
  starsAmount: number | null;
  createdAt: string;
  items: OrderItem[];
  events: { status: OrderStatus; createdAt: string }[];
}

export interface OrderCreated {
  order: Order;
  invoiceUrl: string | null;
}
