from confluent_kafka import Consumer, Producer
import json
from typing import Optional


class KafkaClient:
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self.consumer = None
        self.producer = None

    def create_consumer(self, group_id: str, topics: list):
        self.consumer = Consumer({
            "bootstrap.servers": self.bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",

            "enable.auto.commit": False,
        })

        self.consumer.subscribe(topics)
        return self.consumer

    def create_producer(self):
        self.producer = Producer({
            "bootstrap.servers": self.bootstrap_servers,
            "client.id": "normalizer-producer"
        })

        return self.producer

    def _delivery_report(self, err, msg):
        if err is not None:
            print(f"Kafka delivery failed: {err}")

    def produce_message(
        self,
        topic: str,
        key: Optional[str],
        value: dict,
        flush: bool = False
    ):
        if self.producer is None:
            self.create_producer()

        if isinstance(key, bytes):
            kafka_key = key
        elif key:
            kafka_key = str(key).encode("utf-8")
        else:
            kafka_key = None

        self.producer.produce(
            topic,
            key=kafka_key,
            value=json.dumps(
                value,
                ensure_ascii=False,
                default=str
            ).encode("utf-8"),
            callback=self._delivery_report
        )

        self.producer.poll(0)

        if flush:
            self.producer.flush()