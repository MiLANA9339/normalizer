import os


class Config:
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS = os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS",
        "localhost:9092"
    )
    RAW_PRODUCTS_TOPIC = os.getenv(
        "RAW_PRODUCTS_TOPIC",
        "raw_products"
    )
    NORMALIZED_PRODUCTS_TOPIC = os.getenv(
        "NORMALIZED_PRODUCTS_TOPIC",
        "normalized_products"
    )

    # Redis
    REDIS_URL = os.getenv(
        "REDIS_URL",
        "redis://localhost:6379/0"
    )
    REDIS_SYNONYMS_KEY = os.getenv(
        "REDIS_SYNONYMS_KEY",
        "product_synonyms"
    )
    REDIS_FALLBACK_KEY = os.getenv(
        "REDIS_FALLBACK_KEY",
        "fallback_products"
    )

    # Metrics
    METRICS_PORT = int(os.getenv("METRICS_PORT", 8002))

    # Processing
    CONSUMER_GROUP_ID = os.getenv(
        "CONSUMER_GROUP_ID",
        "product-normalizer"
    )
    BATCH_SIZE = int(os.getenv("BATCH_SIZE", 10))

    # Normalization
    SAVE_FALLBACK = os.getenv("SAVE_FALLBACK", "true").lower() == "true"