from typing import List

from schedule.power_schedule import PowerSchedule
from utils.seed import Seed


class CoverageSizePowerSchedule(PowerSchedule):
    """基于覆盖范围的调度策略。

    核心思想：能在单次执行中触及更多代码行的种子，说明它包含了
    更多的有效前置状态或能穿透更深层的逻辑分支，应当获得更高的能量。
    """

    def __init__(self, min_energy: float = 1e-6) -> None:
        super().__init__()
        self.min_energy = min_energy

    def assign_energy(self, population: List[Seed]) -> None:
        """根据种子覆盖行数分配能量：覆盖行数越多，能量越高。

        公式：energy = max(len(seed.coverage) * 0.1, min_energy)

        使用 0.1 的缩放因子避免覆盖行数差异过大导致能量两极分化。
        设置最小值 min_energy 保证所有种子在归一化中都有非零概率。

        边界处理：
        - 空覆盖集：能量为 min_energy（种子从未被成功执行）
        - 空 population：直接返回
        """
        if not population:
            return

        for seed in population:
            coverage_size = len(seed.coverage)
            if coverage_size == 0:
                # 无覆盖信息 — 给最低能量，避免淘汰零覆盖种子
                seed.energy = self.min_energy
            else:
                # 覆盖行数与能量成正比
                energy = coverage_size * 0.1
                seed.energy = max(energy, self.min_energy)
