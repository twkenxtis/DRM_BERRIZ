import atexit
import os
import pickle
import queue
import threading

from unit.handle_log import setup_logging


logger = setup_logging('download_lock', 'forest_green')


class PKLErrorHandler:
    @staticmethod
    def handle(error: Exception):
        logger.error(f"[PKL ERROR] {error.__class__.__name__}: {error}")


class UUIDSetStore:
    def __init__(self, filename="download_info.pkl", flush_interval=2):
        lock_dir = os.path.join(os.getcwd(), "lock")
        os.makedirs(lock_dir, exist_ok=True)

        self.filename = os.path.join(lock_dir, filename)
        self.data = set()
        self.lock = threading.Lock()

        self.task_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.flush_interval = flush_interval
        self.worker_thread = threading.Thread(target=self._worker, daemon=True)

        self._load()
        self.worker_thread.start()
        atexit.register(self.stop)  # ensure data is saved on program exit

    def _load(self):
        """Load the pickle file; use an empty set if it doesn't exist."""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "rb") as f:
                    loaded = pickle.load(f)
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

    def _save(self):
        """Synchronously save the current set to the pickle file."""
        try:
            with self.lock:
                with open(self.filename, "wb") as f:
                    pickle.dump(self.data, f)
        except Exception as e:
            print(f"[UUIDSetStore] Save failed: {e}")

    def _worker(self):
        """
        Background thread that periodically flushes queued UUIDs into
        the in-memory set and writes it out to disk.
        """
        while not self.stop_event.is_set() or not self.task_queue.empty():
            try:
                # Wait for up to flush_interval seconds for a new UUID
                uuid_str = self.task_queue.get(timeout=self.flush_interval)
                with self.lock:
                    self.data.add(uuid_str)
                self.task_queue.task_done()
            except queue.Empty:
                # No new items arrived; still trigger a save
                pass

            # Periodic save
            self._save()

    def add(self, uuid_str: str):
        """
        Add a UUID string to the store (enqueued for asynchronous saving).
        Raises ValueError if the input is not a string.
        """
        if not isinstance(uuid_str, str):
            raise ValueError("UUID must be a string")
        self.task_queue.put(uuid_str)

    def exists(self, uuid_str: str) -> bool:
        """
        Check whether a UUID string is already present in the store.
        Returns True if found, False otherwise.
        """
        with self.lock:
            return uuid_str in self.data

    def stop(self):
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
