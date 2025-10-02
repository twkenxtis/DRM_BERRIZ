from typing import Any, Dict, List, Optional

class Notice:
    def __init__(self, payload: Any) -> None:
        # Root
        self.code: Optional[Any] = payload.get("code")
        self.message: Optional[Any] = payload.get("message")

        # Data container (may be missing)
        data: Dict[str, Any] = payload.get("data", {}) if isinstance(payload, dict) else {}

        # Cursor info
        cursor: Dict[str, Any] = data.get("cursor", {}) if isinstance(data, dict) else {}
        self.cursor_next: Optional[Any] = cursor.get("next")

        # Pagination flag
        self.has_next: Optional[Any] = data.get("hasNext")

        # Raw contents list
        contents: List[Any] = data.get("contents", []) if isinstance(data, dict) else []
        if not isinstance(contents, list):
            contents = []

        # Normalized notices: keep original key names from JSON
        self.notices: List[Dict[str, Any]] = []
        for item in contents:
            if not isinstance(item, dict):
                continue
            self.notices.append({
                "communityNoticeId": item.get("communityNoticeId"),
                "title": item.get("title"),
                "reservedAt": item.get("reservedAt"),
            })

        # Convenience indexes and maps
        # By ID
        self.by_id: Dict[Any, Dict[str, Any]] = {
            n["communityNoticeId"]: n
            for n in self.notices
            if n.get("communityNoticeId") is not None
        }
        # Sorted by reservedAt ascending (ISO timestamps sort correctly as strings in UTC form)
        self.sorted_by_time: List[Dict[str, Any]] = sorted(
            self.notices,
            key=lambda n: (n.get("reservedAt") is None, n.get("reservedAt"))
        )
        # Most recent first
        self.sorted_desc_time: List[Dict[str, Any]] = list(reversed(self.sorted_by_time))

        # Lightweight helpers (no extra methods, per “one class, one __init__” constraint)
        self.first: Optional[Dict[str, Any]] = self.sorted_by_time[0] if self.sorted_by_time else None
        self.last: Optional[Dict[str, Any]] = self.sorted_desc_time[0] if self.sorted_desc_time else None


class Notice_info:
    def __init__(self, payload: Any) -> None:
        # Root
        self.code: Optional[Any] = payload.get("code")
        self.message: Optional[Any] = payload.get("message")

        # Data container (may be missing)
        data: Dict[str, Any] = payload.get("data", {}) if isinstance(payload, dict) else {}
        communityNotice: Dict[str, Any] = data.get("communityNotice", {}) if isinstance(data, dict) else {}

        # info
        self.communityNoticeId: Any = communityNotice.get("communityNoticeId", {}) if isinstance(communityNotice, dict) else {}
        self.title: Any = communityNotice.get("title", {}) if isinstance(communityNotice, dict) else {}
        self.body: Any = communityNotice.get("body", {}) if isinstance(communityNotice, dict) else {}
        self.eventId: Any = communityNotice.get("eventId", {}) if isinstance(communityNotice, dict) else {}
        self.reservedAt: Any = communityNotice.get("reservedAt", {}) if isinstance(communityNotice, dict) else {}
