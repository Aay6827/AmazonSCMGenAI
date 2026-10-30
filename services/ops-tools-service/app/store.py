import threading

from app.data import seed


class Store:
    def __init__(self):
        self.lock = threading.RLock()
        self.reset()

    def reset(self):
        d = seed()
        self.shipments = d["shipments"]
        self.orders = d["orders"]
        self.inventory = d["inventory"]
        self.actions: dict[str, dict] = {}
        self._seq = 0

    def next_action_id(self) -> str:
        self._seq += 1
        return f"ACT-{self._seq:04d}"