import atexit
import os
import queue
import threading
from pathlib import Path
from typing import Set

import joblib

from static.route import Route
from unit.handle.handle_log import setup_logging


logger = setup_logging('download_lock', 'forest_green')


class PKLErrorHandler:
    @staticmethod
    def handle(error: Exception) -> None:
        logger.error(f"[PKL ERROR] {error.__class__.__name__}: {error}")


BIN_FILE: Path = Route().download_info_bin


class UUIDSetStore:
    def __init__(self) -> None:
        lock_dir: str = os.path.join(os.getcwd(), "lock")
        os.makedirs(lock_dir, exist_ok=True)

        self.filename: str = os.path.join(lock_dir, BIN_FILE)
        self.data: Set[str] = set()
        self.lock: threading.Lock = threading.Lock()

        self.task_queue: queue.Queue[str] = queue.Queue()
        self.stop_event: threading.Event = threading.Event()
        self.flush_interval: int = 2
        self.worker_thread: threading.Thread = threading.Thread(target=self._worker, daemon=True)

        self._load()
        self.worker_thread.start()
        atexit.register(self.stop)

    def _load(self) -> None:
        """Load the joblib file; use an empty set if it doesn't exist."""
        if os.path.exists(self.filename):
            try:
                loaded = joblib.load(self.filename)
                # Validate that the loaded object is a set
                if isinstance(loaded, set):
                    self.data = loaded
                else:
                    self.data = set()
            except Exception as e:
                print(f"[UUIDSetStore] Load failed: {e}")
                self.data = set()
        else:
            self.data = set()

    def _save(self) -> None:
        """Synchronously save the current set to the joblib file."""
        try:
            with self.lock:
                joblib.dump(self.data, self.filename, compress=3)
        except Exception as e:
            print(f"[UUIDSetStore] Save failed: {e}")

    def _worker(self) -> None:
        """
        Background thread that periodically flushes queued UUIDs into
        the in-memory set and writes it out to disk.
        """
        while not self.stop_event.is_set() or not self.task_queue.empty():
            try:
                # Wait for up to flush_interval seconds for a new UUID
                uuid_str: str = self.task_queue.get(timeout=self.flush_interval)
                with self.lock:
                    self.data.add(uuid_str)
                self.task_queue.task_done()
            except queue.Empty:
                # No new items arrived; still trigger a save
                pass

            # Periodic save
            self._save()

    def add(self, uuid_str: str) -> None:
        """
        Add a UUID string to the store (enqueued for asynchronous saving).
        Raises ValueError if the input is not a string.
        """
        try:
            if not isinstance(uuid_str, str):
                raise ValueError("UUID must be a string")
            self.task_queue.put(uuid_str)
        except Exception as e:
            logger.error(e)

    def exists(self, uuid_str: str) -> bool:
        """
        Check whether a UUID string is already present in the store.
        Returns True if found, False otherwise.
        """
        with self.lock:
            return uuid_str in self.data

    def stop(self) -> None:
        """
        Signal the background thread to finish processing and save
        remaining data to disk before exiting.
        """
        try:
            if not self.stop_event.is_set():
                self.stop_event.set()
                self.worker_thread.join()
                self._save()
        except KeyboardInterrupt:
            pass
