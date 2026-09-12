import re
from typing import Dict, Optional, Any
from datetime import datetime, UTC


class ProductNormalizer:
    def __init__(self, redis_client, save_fallback: bool = True):
        self.redis = redis_client
        self.save_fallback = save_fallback

    def normalize(self, raw_product: Dict) -> Optional[Dict]:
        product_name = self._get_first_non_empty(
            raw_product,
            [
                "product_name",
                "raw_product_name",
                "name",
                "title",
                "имя",
                "название",
                "название товара"
            ]
        )

        if not product_name:
            return None

        canonical = self.redis.get_synonym(product_name)

        if canonical is None and self.save_fallback:
            self.redis.save_fallback(product_name, raw_product)

        current_price_text = self._get_first_non_empty(
            raw_product,
            [
                "current_price",
                "current_price_text",
                "price_current",
                "new_price",
                "new_price_text",
                "новая",
                "текущая цена товара",
                "цена"
            ]
        )

        old_price_text = self._get_first_non_empty(
            raw_product,
            [
                "old_price",
                "old_price_text",
                "price_old",
                "previous_price",
                "regular_price",
                "старая",
                "старая цена товара"
            ]
        )

        discount_text = self._get_first_non_empty(
            raw_product,
            [
                "discount",
                "discount_text",
                "discount_percent",
                "процент скидки",
                "размер скидки"
            ]
        )

        current_price_kopecks = self._extract_price_kopecks(
            current_price_text
        )
        old_price_kopecks = self._extract_price_kopecks(
            old_price_text
        )

        discount_abs_kopecks = None
        discount_pct = None

        if (
            current_price_kopecks is not None
            and old_price_kopecks is not None
            and old_price_kopecks > 0
            and old_price_kopecks > current_price_kopecks
        ):
            discount_abs_kopecks = old_price_kopecks - current_price_kopecks
            discount_pct = round(
                discount_abs_kopecks / old_price_kopecks * 100,
                2
            )
        else:
            parsed_discount_pct = self._extract_discount_pct(discount_text)
            if parsed_discount_pct is not None:
                discount_pct = parsed_discount_pct

        has_promotion = self._detect_promotion(
            raw_product=raw_product,
            current_price_kopecks=current_price_kopecks,
            old_price_kopecks=old_price_kopecks,
            discount_text=discount_text
        )

        normalized_name = self._normalize_name(product_name)

        product_url = self._get_first_non_empty(
            raw_product,
            [
                "product_name_url",
                "product_url",
                "url",
                "ссылка",
                "url товара"
            ]
        )

        promo_name = self._get_first_non_empty(
            raw_product,
            [
                "promo_name",
                "promotion_name",
                "promotion",
                "название акции"
            ]
        )

        promo_url = self._get_first_non_empty(
            raw_product,
            [
                "promo_name_url",
                "promo_url",
                "promotion_url",
                "url акции"
            ]
        )

        promo_end_date = self._get_first_non_empty(
            raw_product,
            [
                "promo_end_date",
                "promotion_end_date",
                "дата окончания акции"
            ]
        )

        normalized = {
            # Источник
            "source": raw_product.get("source"),
            "store": raw_product.get("store"),
            "collected_at": raw_product.get("collected_at"),

            # Исходные данные
            "raw_product_name": product_name,
            "product_url": product_url,
            "raw_data": raw_product,

            # Акция
            "promo_name": promo_name,
            "promo_url": promo_url,
            "promo_end_date": promo_end_date,

            # Канонические данные из Redis
            "canonical_id": canonical.get("id") if canonical else None,
            "canonical_name": canonical.get("name") if canonical else None,
            "canonical_brand": canonical.get("brand") if canonical else None,
            "canonical_category": canonical.get("category") if canonical else None,

            # Нормализованные данные
            "normalized_name": normalized_name,
            "price_current_kopecks": current_price_kopecks,
            "price_old_kopecks": old_price_kopecks,
            "discount_abs_kopecks": discount_abs_kopecks,
            "discount_pct": discount_pct,
            "has_promotion": has_promotion,

            # Статус матчинга
            "match_status": "found" if canonical else "fallback",

            # Технические метаданные
            "normalized_at": datetime.now(UTC).isoformat(),
        }

        return normalized

    def _get_first_non_empty(
        self,
        data: Dict,
        keys: list[str]
    ) -> Optional[Any]:
        for key in keys:
            value = data.get(key)

            if value is not None and str(value).strip() != "":
                return value

        return None

    def _normalize_name(self, name: str) -> str:
        if not name:
            return ""

        name = str(name).lower().strip()
        name = name.replace("ё", "е")
        name = name.replace("\xa0", " ")

        name = re.sub(
            r"(\d)(gb|гб|tb|тб|mb|мб|мл|л|г|кг|%)\b",
            r"\1 \2",
            name
        )

        name = re.sub(r"(\d),(\d)", r"\1.\2", name)

        name = re.sub(
            r"\b(скидка|акция|распродажа|sale|%|off|выгода|хит|новинка)\b",
            " ",
            name,
            flags=re.I
        )

        name = re.sub(r"[^\w\s.%+-]", " ", name)
        name = re.sub(r"\s+", " ", name).strip()

        return name

    def _extract_price_kopecks(
        self,
        price_text: Optional[Any]
    ) -> Optional[int]:

        if price_text is None:
            return None

        text = str(price_text).lower().strip()

        if not text:
            return None

        text = text.replace("\xa0", " ")
        text = text.replace("₽", "")
        text = text.replace("руб.", "")
        text = text.replace("руб", "")
        text = text.replace("р.", "")
        text = text.replace("р", "")
        text = text.replace("от", "")
        text = text.replace(" ", "")

        # Если формат 1.299,99 — приводим к 1299.99
        if "," in text and "." in text:
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "")
                text = text.replace(",", ".")
            else:
                text = text.replace(",", "")
        else:
            text = text.replace(",", ".")

        text = re.sub(r"[^0-9.]", "", text)

        if not text:
            return None

        try:
            value = float(text)
        except ValueError:
            return None

        return int(round(value * 100))

    def _extract_discount_pct(
        self,
        discount_text: Optional[Any]
    ) -> Optional[float]:
        if discount_text is None:
            return None

        text = str(discount_text).lower().replace(",", ".")

        match = re.search(r"(-?\d+(?:\.\d+)?)\s?%", text)

        if not match:
            return None

        return abs(float(match.group(1)))

    def _detect_promotion(
        self,
        raw_product: Dict,
        current_price_kopecks: Optional[int],
        old_price_kopecks: Optional[int],
        discount_text: Optional[Any]
    ) -> bool:
        if "has_promotion" in raw_product:
            return bool(raw_product["has_promotion"])

        if (
            current_price_kopecks is not None
            and old_price_kopecks is not None
            and old_price_kopecks > current_price_kopecks
        ):
            return True

        discount_pct = self._extract_discount_pct(discount_text)

        if discount_pct is not None and discount_pct > 0:
            return True

        promotion = self._get_first_non_empty(
            raw_product,
            [
                "promotion",
                "promo_name",
                "promotion_name",
                "название акции"
            ]
        )

        if promotion:
            return True

        return False