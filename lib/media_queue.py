from collections import deque
from typing import Any, Dict, List, Optional


class MediaQueue:
    """A queue class for managing media IDs to be processed."""

    def __init__(self) -> None:
        self._queue: deque[tuple[str, str]] = deque()
        self._processed_items: set[str] = set()  # To avoid duplicates

    def enqueue(self, media_id: str, media_type: str) -> None:
        """Add a media ID to the queue if it hasn't been processed yet."""
        if media_id not in self._processed_items:
            self._queue.append((media_id, media_type))
            self._processed_items.add(media_id)

    def enqueue_batch(self, media_items: List[Dict[str, Any]], Type:str) -> None:
        """Add multiple media items to the queue."""
        if Type != 'POST':
            for item in media_items:
                if "mediaId" in item and "mediaType" in item:
                    self.enqueue(item["mediaId"], item["mediaType"])
        elif Type == 'POST':
            for item in media_items:
                if "postId" in item:
                    self.enqueue(item["postId"], item["mediaType"])
        else:
            raise TabError("Type must be POST LIVE VOD PHOTO")

    def dequeue(self) -> Optional[tuple[str, str]]:
        """Remove and return the next media ID and type from the queue."""
        if not self.is_empty():
            return self._queue.popleft()
        return None

    def is_empty(self) -> bool:
        """Check if the queue is empty."""
        return len(self._queue) == 0

    def size(self) -> int:
        """Return the current size of the queue."""
        return len(self._queue)