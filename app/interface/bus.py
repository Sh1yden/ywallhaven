"""In-app event bus topics over page.pubsub.

Decouples the panels: publishers emit plain-dict messages, subscribers
react. The only deliberate exception is fullscreen navigation, which
needs a return value (fire-and-forget pubsub cannot answer) and stays
a direct callback wired in flet_app.
"""

from typing import Any, Callable

TOPIC_FILTERS = "ywallhaven/filters"
"""Left -> middle: {"api_key": str, "filters": dict}."""

TOPIC_PREVIEW = "ywallhaven/preview"
"""Middle -> right: {"wallpaper": dict, "index": int | None}."""

TOPIC_DOWNLOAD_REQUEST = "ywallhaven/download_request"
"""Middle -> right: {"wallpaper": dict} (open the resolution dialog)."""

TOPIC_DOWNLOAD = "ywallhaven/download"
"""Right -> app: {"url": str, "file_name": str, "size": tuple | None}."""

TOPIC_SET_WALLPAPER = "ywallhaven/set_wallpaper"
"""Right -> app: {"url": str}."""

TOPIC_TAG = "ywallhaven/tag"
"""Right -> left: {"name": str}."""

TOPIC_API_KEY = "ywallhaven/api_key"
"""Settings -> left+right: {"api_key": str}."""


def _pubsub(page: Any) -> Any | None:
    """Return the page pubsub client, or None when unavailable."""
    if page is None:
        return None
    return getattr(page, "pubsub", None)


def publish(page: Any, topic: str, message: dict) -> bool:
    """Publish a message dict on a topic.

    Args:
        page: The Flet page (may be None in unit tests).
        topic: One of the TOPIC_* constants.
        message: Plain-dict payload.

    Returns:
        True when the message was sent.
    """
    pubsub = _pubsub(page)
    if pubsub is None:
        return False
    try:
        pubsub.send_all_on_topic(topic, message)
    except Exception:
        return False
    return True


def subscribe(
    page: Any, topic: str, handler: Callable[[str, Any], Any]
) -> bool:
    """Subscribe a (topic, message) handler.

    Args:
        page: The Flet page (may be None in unit tests).
        topic: One of the TOPIC_* constants.
        handler: Sync or async callback receiving (topic, message).

    Returns:
        True when subscribed.
    """
    pubsub = _pubsub(page)
    if pubsub is None:
        return False
    try:
        pubsub.subscribe_topic(topic, handler)
    except Exception:
        return False
    return True


def unsubscribe(page: Any, topic: str) -> bool:
    """Remove the page subscription for a topic.

    Args:
        page: The Flet page (may be None in unit tests).
        topic: One of the TOPIC_* constants.

    Returns:
        True when the call went through.
    """
    pubsub = _pubsub(page)
    if pubsub is None:
        return False
    try:
        pubsub.unsubscribe_topic(topic)
    except Exception:
        return False
    return True


def unsubscribe_all(page: Any) -> bool:
    """Remove every subscription of the page.

    Args:
        page: The Flet page (may be None in unit tests).

    Returns:
        True when the call went through.
    """
    pubsub = _pubsub(page)
    if pubsub is None:
        return False
    try:
        pubsub.unsubscribe_all()
    except Exception:
        return False
    return True
