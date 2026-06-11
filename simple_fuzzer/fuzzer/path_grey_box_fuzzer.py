import time
from typing import Any, Dict, List, Optional, Set, Tuple

from fuzzer.grey_box_fuzzer import GreyBoxFuzzer
from runner.runner import Runner
from schedule.path_power_schedule import PathPowerSchedule
from runner.function_coverage_runner import FunctionCoverageRunner
from utils.object_utils import get_md5_of_object
from utils.seed import Seed


class PathGreyBoxFuzzer(GreyBoxFuzzer):
    """Count how often individual paths are exercised."""

    def __init__(
            self,
            seeds: List[str],
            schedule: PathPowerSchedule,
            is_print: bool,
            output_dir: str = "_result",
            snapshot_interval: int = 1000,
            max_population: int = 1000):
        super().__init__(seeds, schedule, False, output_dir, snapshot_interval, max_population)
        self.is_print = is_print

        self.seen_paths: Set[str] = set()
        self.last_path_time = self.start_time
        self.total_paths = 0

        if self.is_print:
            print("""
┌───────────────────────┬───────────────────────┬───────────────────────┬───────────────────┬───────────────────┬────────────────┬───────────────────┐
│        Run Time       │     Last New Path     │    Last Uniq Crash    │    Total Execs    │    Total Paths    │  Uniq Crashes  │   Covered Lines   │
├───────────────────────┼───────────────────────┼───────────────────────┼───────────────────┼───────────────────┼────────────────┼───────────────────┤""")

    def print_stats(self):
        if not self.is_print:
            return

        def format_seconds(seconds):
            hours = int(seconds) // 3600
            minutes = int(seconds % 3600) // 60
            remaining_seconds = int(seconds) % 60
            return f"{hours:02d}:{minutes:02d}:{remaining_seconds:02d}"

        template = """│{runtime}│{path_time}│{crash_time}│{total_exec}│{total_path}│{uniq_crash}│{covered_line}│
├───────────────────────┼───────────────────────┼───────────────────────┼───────────────────┼───────────────────┼────────────────┼───────────────────┤"""
        template = template.format(runtime=format_seconds(time.time() - self.start_time).center(23),
                                   path_time=format_seconds(self.last_path_time - self.start_time).center(23),
                                   crash_time=format_seconds(self.last_crash_time - self.start_time).center(23),
                                   total_exec=str(self.total_execs).center(19),
                                   total_path=str(self.total_paths).center(19),
                                   uniq_crash=str(len(set(self.crash_map.values()))).center(16),
                                   covered_line=str(len(self.covered_line)).center(19))
        print(template)

    @staticmethod
    def get_path_id(runner: FunctionCoverageRunner) -> Optional[str]:
        coverage = runner.coverage()
        if not coverage:
            return None
        path = tuple(sorted(coverage))
        return get_md5_of_object(path)

    def snapshot_extra(self) -> Dict[str, Any]:
        return {
            "total_paths": self.total_paths,
            "seen_paths": self.seen_paths,
            "path_frequency": getattr(self.schedule, "path_frequency", {}),
        }

    def persist_path_seed(self, path_id: str, coverage) -> Seed:
        seed = Seed(self.inp, coverage)
        seed.path_id = path_id
        self.population.append(seed)
        self.last_new_seed = seed
        self.persist_seed(seed, "new_path")
        return seed

    def run(self, runner: FunctionCoverageRunner) -> Tuple[Any, str]:  # type: ignore
        """Inform scheduler about path frequency"""
        existing_seeds = set(self.population)
        result, outcome = super().run(runner)
        path_id = self.get_path_id(runner)

        update_frequency = getattr(self.schedule, "update_frequency", None)
        if callable(update_frequency):
            update_frequency(path_id)

        if path_id is not None and path_id not in self.seen_paths:
            self.seen_paths.add(path_id)
            self.last_path_time = time.time()
            self.total_paths = len(self.seen_paths)
            if self.last_new_seed is None and outcome == Runner.PASS:
                self.persist_path_seed(path_id, runner.coverage())

        for seed in self.population:
            if seed in existing_seeds:
                continue
            seed.path_id = path_id
            if (seed is self.last_new_seed
                    and path_id is not None
                    and getattr(seed, "saved_reason", None) == "new_coverage"):
                self.persist_seed(seed, "new_coverage")

        self.trim_population()

        return result, outcome
