import json
import signal

from .config import Config
from .redis_client import RedisClient
from .kafka_client import KafkaClient
from .product_normalizer import ProductNormalizer

from prometheus_client import Counter, start_http_server, CollectorRegistry


REGISTRY = CollectorRegistry()

MESSAGES_RECEIVED = Counter(
    "normalizer_messages_received_total",
    "Received messages",
    registry=REGISTRY
)

MESSAGES_NORMALIZED = Counter(
    "normalizer_messages_normalized_total",
    "Normalized messages",
    registry=REGISTRY
)

NORMALIZATION_ERRORS = Counter(
    "normalizer_errors_total",
    "Normalization errors",
    registry=REGISTRY
)

FALLBACK_SAVED = Counter(
    "normalizer_fallback_saved_total",
    "Fallback saved",
    registry=REGISTRY
)


class NormalizerService:
    def __init__(self):
        self.config = Config()
        self.running = True

        self.redis_client = RedisClient(
            url=self.config.REDIS_URL,
            synonyms_key=self.config.REDIS_SYNONYMS_KEY,
            fallback_key=self.config.REDIS_FALLBACK_KEY
        )

        self.kafka_client = KafkaClient(
            self.config.KAFKA_BOOTSTRAP_SERVERS
        )

        self.normalizer = ProductNormalizer(
            redis_client=self.redis_client,
            save_fallback=self.config.SAVE_FALLBACK
        )

        start_http_server(
            self.config.METRICS_PORT,
            registry=REGISTRY
        )

        print(f"Метрики доступны на порту {self.config.METRICS_PORT}")

    def run(self):
        print("ЗАПУСК НОРМАЛИЗАТОРА")
        print(f"Kafka: {self.config.KAFKA_BOOTSTRAP_SERVERS}")
        print(f"Redis: {self.config.REDIS_URL}")
        print(f"Raw topic: {self.config.RAW_PRODUCTS_TOPIC}")
        print(f"Normalized topic: {self.config.NORMALIZED_PRODUCTS_TOPIC}")

        consumer = self.kafka_client.create_consumer(
            group_id=self.config.CONSUMER_GROUP_ID,
            topics=[self.config.RAW_PRODUCTS_TOPIC]
        )

        self.kafka_client.create_producer()

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

        try:
            while self.running:
                msg = consumer.poll(1.0)

                if msg is None:
                    continue

                if msg.error():
                    print(f"Kafka error: {msg.error()}")
                    continue

                MESSAGES_RECEIVED.inc()

                try:
                    raw_data = json.loads(
                        msg.value().decode("utf-8")
                    )

                    normalized = self.normalizer.normalize(raw_data)

                    if normalized:
                        self.kafka_client.produce_message(
                            topic=self.config.NORMALIZED_PRODUCTS_TOPIC,
                            key=msg.key(),
                            value=normalized,
                            flush=True
                        )

                        consumer.commit(msg)

                        MESSAGES_NORMALIZED.inc()

                        if normalized.get("match_status") == "fallback":
                            FALLBACK_SAVED.inc()

                        print(
                            "Normalized: "
                            f"{normalized.get('raw_product_name', 'unknown')[:80]} | "
                            f"match={normalized.get('match_status')}"
                        )

                    else:
                        NORMALIZATION_ERRORS.inc()
                        print(f"Failed to normalize: {raw_data}")


                        consumer.commit(msg)

                except json.JSONDecodeError as e:
                    NORMALIZATION_ERRORS.inc()
                    print(f"JSON decode error: {e}")

                    consumer.commit(msg)

                except Exception as e:
                    NORMALIZATION_ERRORS.inc()
                    print(f"Normalization error: {e}")

                    consumer.commit(msg)

        except KeyboardInterrupt:
            print("\nInterrupted by user")

        finally:
            consumer.close()
            print("Normalizer stopped")

    def _shutdown(self, signum, frame):
        print("\nReceived shutdown signal")
        self.running = False


def main():
    service = NormalizerService()
    service.run()


if __name__ == "__main__":
    main()