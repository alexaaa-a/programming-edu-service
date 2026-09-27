import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class Timer:
    start_time: float

    @staticmethod
    def start() -> "Timer":
        return Timer(start_time=time.perf_counter())

    @property
    def elapsed_seconds(self) -> float:
        return time.perf_counter() - self.start_time

    def stop(self, callback: Callable[[float], None]) -> None:
        callback(self.elapsed_seconds)
