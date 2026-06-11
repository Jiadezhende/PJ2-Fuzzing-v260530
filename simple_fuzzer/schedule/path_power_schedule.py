from typing import Dict, Sequence

from schedule.power_schedule import PowerSchedule
from utils.seed import Seed

# Lower bound on per-seed energy so normalized_energy() never asserts on sum == 0.
MIN_ENERGY = 1e-6


class PathPowerSchedule(PowerSchedule):

    def __init__(self) -> None:
        super().__init__()
        self.path_frequency: Dict[str, int] = {}

    def update_frequency(self, path_id: str) -> None:
        """Record one execution of the given path."""
        if path_id is None:
            return
        self.path_frequency[path_id] = self.path_frequency.get(path_id, 0) + 1

    def assign_energy(self, population: Sequence[Seed]) -> None:
        """Assign exponential energy inversely proportional to path frequency"""
        for seed in population:
            path_id = getattr(seed, "path_id", None)
            if path_id is None:
                # No path information yet — fall back to a neutral default
                # so the seed still has a chance of being chosen.
                seed.energy = 1.0
                continue

            frequency = max(1, self.path_frequency.get(path_id, 1))
            # 2 ** -frequency makes rare paths exponentially more attractive
            # while keeping all energies strictly positive.
            seed.energy = max(MIN_ENERGY, 2.0 ** (-frequency))
