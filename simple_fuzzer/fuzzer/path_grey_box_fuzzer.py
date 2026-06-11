import time
from typing import Any, List, Optional, Set, Tuple

from fuzzer.grey_box_fuzzer import GreyBoxFuzzer
from schedule.path_power_schedule import PathPowerSchedule
from runner.function_coverage_runner import FunctionCoverageRunner
from utils.object_utils import get_md5_of_object


class PathGreyBoxFuzzer(GreyBoxFuzzer):
    """Count how often individual paths are exercised."""

    def __init__(self, seeds: List[str], schedule: PathPowerSchedule, is_print: bool):
        super().__init__(seeds, schedule, False)
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

        for seed in self.population:
            if seed in existing_seeds:
                continue
            seed.path_id = path_id

        return result, outcome
