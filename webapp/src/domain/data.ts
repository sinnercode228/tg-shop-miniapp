/** Static shop data bundled from `/shared` — the same JSON files the backend loads. */
import catalogJson from '../../../shared/catalog.json';
import pricingJson from '../../../shared/pricing.json';
import { rulesFromJson } from './pricing';
import type { Catalog } from './types';

export const bundledCatalog = catalogJson as unknown as Catalog;
export const pricingRules = rulesFromJson(pricingJson);
