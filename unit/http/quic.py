import asyncio
import json
from collections import deque
from typing import Dict, Optional

from aioquic.asyncio.protocol import QuicConnectionProtocol
from aioquic.h3.connection import H3Connection
from aioquic.h3.events import DataReceived, HeadersReceived


class HttpClient(QuicConnectionProtocol):
    """HTTP/3 客戶端協議"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http = H3Connection(self._quic)
        self._request_events = {}
        self._request_waiter = {}

    async def get(self, url: str, headers: Optional[Dict[str, str]] = None):
        """執行 GET 請求"""
        url = url.replace("https://", "")
        parts = url.split("/", 1)
        authority = parts[0]
        path = "/" + parts[1] if len(parts) > 1 else "/"
        
        request_headers = [
            (b":method", b"GET"),
            (b":scheme", b"https"),
            (b":authority", authority.encode()),
            (b":path", path.encode()),
        ]
        
        if headers:
            for k, v in headers.items():
                request_headers.append((k.encode(), v.encode()))
        
        stream_id = self._quic.get_next_available_stream_id()
        self._http.send_headers(stream_id=stream_id, headers=request_headers, end_stream=True)
        
        waiter = self._loop.create_future()
        self._request_events[stream_id] = deque()
        self._request_waiter[stream_id] = waiter
        self.transmit()
        
        return await asyncio.shield(waiter)

    def quic_event_received(self, event):
        """處理 QUIC 事件"""
        for http_event in self._http.handle_event(event):
            if isinstance(http_event, (HeadersReceived, DataReceived)):
                stream_id = http_event.stream_id
                if stream_id in self._request_events:
                    self._request_events[stream_id].append(http_event)
                    if http_event.stream_ended:
                        self._request_waiter.pop(stream_id).set_result(
                            self._request_events.pop(stream_id)
                        )


class QuicResponse:
    def __init__(self, url: str, events: list):
        self.url = url
        self.events = events
        self.headers = {}
        self.data = b""
        self._parsed = False

    def parse(self):
        if self._parsed:
            return
        for event in self.events:
            if isinstance(event, HeadersReceived):
                for h, v in event.headers:
                    self.headers[h.decode()] = v.decode()
            elif isinstance(event, DataReceived):
                self.data += event.data
        self._parsed = True

    @property
    def status(self):
        self.parse()
        return self.headers.get(":status")

    @property
    def content_type(self):
        self.parse()
        return self.headers.get("content-type", "").lower()

    @property
    def content_length(self):
        self.parse()
        return len(self.data)

    @property
    def body(self):
        self.parse()
        ct = self.content_type
        if "application/json" in ct:
            try:
                return json.loads(self.data.decode())
            except Exception as e:
                return f"[JSON decode error] {e}"
        elif "text/" in ct:
            try:
                return self.data.decode()
            except Exception as e:
                return f"[Text decode error] {e}"
        else:
            return self.data