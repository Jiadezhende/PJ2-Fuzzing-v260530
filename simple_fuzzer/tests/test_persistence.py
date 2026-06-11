import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fuzzer.path_grey_box_fuzzer import PathGreyBoxFuzzer
from runner.function_coverage_runner import FunctionCoverageRunner
from schedule.path_power_schedule import PathPowerSchedule


def target(inp: str) -> None:
    if inp.startswith("A"):
        if "!" in inp:
            raise RuntimeError("boom")
    else:
        return


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        runner = FunctionCoverageRunner(target)
        fuzzer = PathGreyBoxFuzzer(
            seeds=["A!", "B"],
            schedule=PathPowerSchedule(),
            is_print=False,
            output_dir=tmp,
            snapshot_interval=1,
        )

        fuzzer.runs(runner, run_time=1)
        fuzzer.persist_snapshot("final")

        root = Path(tmp)
        seed_files = list((root / "seeds").glob("*.pkl"))
        crash_files = list((root / "crashes").glob("*.pkl"))
        snapshot_files = list((root / "snapshots").glob("*.pkl"))

        assert seed_files, "expected persisted seed files"
        assert crash_files, "expected persisted crash files"
        assert snapshot_files, "expected persisted snapshot files"
        assert len(fuzzer.population) <= fuzzer.max_population

    print("persistence smoke test passed")


if __name__ == "__main__":
    main()
