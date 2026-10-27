from collections.abc import Callable
from time import perf_counter


class DeadlineManager:
    def __init__(
        self, budget_ms: int, reserve_ms: int, clock: Callable[[], float] = perf_counter
    ) -> None:
        self.budget_ms = budget_ms
        self.reserve_ms = reserve_ms
        self.clock = clock
        self.started = clock()

    @property
    def elapsed_ms(self) -> float:
        return (self.clock() - self.started) * 1000

    @property
    def remaining_ms(self) -> float:
        return max(0.0, self.budget_ms - self.elapsed_ms)

    def can_start(self, expected_ms: int) -> bool:
        return self.remaining_ms + 1e-8 >= expected_ms + self.reserve_ms

    def call_timeout_ms(self, cap_ms: int) -> float:
        return max(0.0, min(cap_ms, self.remaining_ms - self.reserve_ms))
