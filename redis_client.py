import json
import redis
import hashlib
import re
from datetime import datetime, UTC
from typing import Optional, Dict, List


class RedisClient:
    def __init__(
        self,
        url: str,
        synonyms_key: str = "product_synonyms",
        fallback_key: str = "fallback_products"
    ):
        self.client = redis.Redis.from_url(
            url,
            decode_responses=True
        )
        self.synonyms_key = synonyms_key
        self.fallback_key = fallback_key

    def normalize_lookup_key(self, product_name: str) -> str:

        if not product_name:
            return ""

        text = str(product_name).lower().strip()
        text = text.replace("ё", "е")
        text = text.replace("\xa0", " ")

        # 128gb -> 128 gb, 930мл -> 930 мл
        text = re.sub(
            r"(\d)(gb|гб|tb|тб|mb|мб|мл|л|г|кг|%)\b",
            r"\1 \2",
            text
        )

        # Запятые в числах
        text = re.sub(r"(\d),(\d)", r"\1.\2", text)

        # Убираем мусор, но оставляем буквы/цифры/точки/проценты
        text = re.sub(r"[^\w\s.%+-]", " ", text)

        # Убираем маркетинговые слова
        text = re.sub(
            r"\b(скидка|акция|распродажа|sale|выгода|хит|новинка|товар дня)\b",
            " ",
            text,
            flags=re.I
        )

        text = re.sub(r"\s+", " ", text).strip()

        return text

    def get_synonym(self, product_name: str) -> Optional[Dict]:
        lookup_key = self.normalize_lookup_key(product_name)

        if not lookup_key:
            return None

        canonical = self.client.hget(self.synonyms_key, lookup_key)

        if canonical:
            return json.loads(canonical)

        return None

    def save_fallback(self, product_name: str, raw_data: Dict):
        lookup_key = self.normalize_lookup_key(product_name)

        if not lookup_key:
            return

        hash_key = hashlib.md5(
            lookup_key.encode("utf-8")
        ).hexdigest()

        fallback_key = f"{self.fallback_key}:{hash_key}"

        data = {
            "product_name": product_name,
            "lookup_key": lookup_key,
            "raw_data": raw_data,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "pending"
        }

        self.client.set(
            fallback_key,
            json.dumps(data, ensure_ascii=False)
        )
        self.client.expire(
            fallback_key,
            60 * 60 * 24 * 30
        )

    def get_fallback_list(self, limit: int = 100) -> List[Dict]:
        keys = self.client.keys(f"{self.fallback_key}:*")

        result = []

        for key in keys[:limit]:
            data = self.client.get(key)

            if data:
                result.append(json.loads(data))

        return result

    def add_synonym(self, product_name: str, canonical: Dict):
        lookup_key = self.normalize_lookup_key(product_name)

        if not lookup_key:
            return

        self.client.hset(
            self.synonyms_key,
            lookup_key,
            json.dumps(canonical, ensure_ascii=False)
        )