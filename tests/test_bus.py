"""Tests for the in-app event bus helpers (page.pubsub wrapper)."""

from app.interface import bus


class _FakePubSub:
    """Recording stand-in for the Flet PubSubClient."""

    def __init__(self) -> None:
        self.sent: list = []
        self.subs: dict = {}
        self.unsubs: list = []
        self.all_unsubscribed = False

    def send_all_on_topic(self, topic, message):
        self.sent.append((topic, message))

    def subscribe_topic(self, topic, handler):
        self.subs[topic] = handler

    def unsubscribe_topic(self, topic):
        self.unsubs.append(topic)

    def unsubscribe_all(self):
        self.all_unsubscribed = True


class _PageStub:
    def __init__(self, pubsub=None) -> None:
        self.pubsub = pubsub


def test_topics_are_namespaced():
    for topic in (
        bus.TOPIC_FILTERS,
        bus.TOPIC_PREVIEW,
        bus.TOPIC_DOWNLOAD_REQUEST,
        bus.TOPIC_DOWNLOAD,
        bus.TOPIC_SET_WALLPAPER,
        bus.TOPIC_TAG,
        bus.TOPIC_API_KEY,
    ):
        assert topic.startswith("ywallhaven/")
    assert len(
        {
            bus.TOPIC_FILTERS,
            bus.TOPIC_PREVIEW,
            bus.TOPIC_DOWNLOAD_REQUEST,
            bus.TOPIC_DOWNLOAD,
            bus.TOPIC_SET_WALLPAPER,
            bus.TOPIC_TAG,
            bus.TOPIC_API_KEY,
        }
    ) == 7


def test_publish_sends_on_topic():
    pubsub = _FakePubSub()

    assert bus.publish(_PageStub(pubsub), bus.TOPIC_TAG, {"name": "x"}) is True
    assert pubsub.sent == [(bus.TOPIC_TAG, {"name": "x"})]


def test_helpers_tolerate_missing_page():
    assert bus.publish(None, bus.TOPIC_TAG, {}) is False
    assert bus.subscribe(None, bus.TOPIC_TAG, lambda t, m: None) is False
    assert bus.unsubscribe(None, bus.TOPIC_TAG) is False
    assert bus.unsubscribe_all(None) is False
    assert bus.publish(_PageStub(None), bus.TOPIC_TAG, {}) is False


def test_helpers_tolerate_pubsub_errors():
    class _Boom:
        def send_all_on_topic(self, topic, message):
            raise RuntimeError("boom")

        def subscribe_topic(self, topic, handler):
            raise RuntimeError("boom")

        def unsubscribe_topic(self, topic):
            raise RuntimeError("boom")

        def unsubscribe_all(self):
            raise RuntimeError("boom")

    page = _PageStub(_Boom())
    assert bus.publish(page, bus.TOPIC_TAG, {}) is False
    assert bus.subscribe(page, bus.TOPIC_TAG, lambda t, m: None) is False
    assert bus.unsubscribe(page, bus.TOPIC_TAG) is False
    assert bus.unsubscribe_all(page) is False


def test_subscribe_unsubscribe_roundtrip():
    pubsub = _FakePubSub()
    page = _PageStub(pubsub)
    handler = lambda t, m: None  # noqa: E731

    assert bus.subscribe(page, bus.TOPIC_FILTERS, handler) is True
    assert pubsub.subs[bus.TOPIC_FILTERS] is handler

    assert bus.unsubscribe(page, bus.TOPIC_FILTERS) is True
    assert bus.TOPIC_FILTERS in pubsub.unsubs

    assert bus.unsubscribe_all(page) is True
    assert pubsub.all_unsubscribed is True
