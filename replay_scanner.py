"""Single-worker replay scanning with coalesced requests and bounded results."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import queue
import threading


@dataclass(frozen=True)
class ReplayRow:
    path: Path
    values: tuple[str, str]


class ReplayScanner:
    def __init__(self, store):
        self.store = store
        self.results = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self._condition = threading.Condition()
        self._pending = None
        self._generation = 0
        self._thread = threading.Thread(target=self._run, name="replay-scanner", daemon=True)
        self._thread.start()

    def request(self):
        with self._condition:
            self._generation += 1
            self._pending = self._generation
            self._condition.notify()
            return self._generation

    def close(self):
        self.stop.set()
        with self._condition:
            self._condition.notify()

    def _publish(self, result):
        if self.stop.is_set():
            return
        try:
            self.results.get_nowait()
        except queue.Empty:
            pass
        self.results.put_nowait(result)

    def _run(self):
        while not self.stop.is_set():
            with self._condition:
                self._condition.wait_for(lambda: self._pending is not None or self.stop.is_set())
                if self.stop.is_set():
                    return
                generation, self._pending = self._pending, None
            try:
                rows = [ReplayRow(path, (
                    datetime.fromtimestamp(info.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                    f"{info.st_size / 1024:.1f} KB",
                )) for path, info in self.store.list_entries()]
                self._publish((generation, rows, None))
                # Publish the listing first; hashing must not delay its display.
                self.store.warm_index(self.stop)
            except Exception as exc:
                self._publish((generation, None, str(exc)))
