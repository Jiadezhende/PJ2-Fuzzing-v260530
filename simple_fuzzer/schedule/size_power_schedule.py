from typing import List

from schedule.power_schedule import PowerSchedule
from utils.seed import Seed


class SizePowerSchedule(PowerSchedule):
    """基于输入长度的调度策略。

    核心思想：较短的输入执行更快，且更容易暴露出核心逻辑的漏洞
    而不被繁杂的脏数据干扰。因此输入越短，分配的能量越高。
    """

    def __init__(self, min_energy: float = 1e-6) -> None:
        super().__init__()
        self.min_energy = min_energy

    def assign_energy(self, population: List[Seed]) -> None:
        """根据输入长度分配能量：长度越短，能量越高。

        公式：energy = max(1.0 / len(seed.data), min_energy)

        边界处理：
        - 空字符串：赋予最高能量 (1.0)，因为空输入可能触发边界行为
        - 超长字符串：能量趋近于 0，但设置最小值保证不被完全淘汰
        """
        if not population:
            return

        for seed in population:
            length = len(seed.data)
            if length == 0:
                # 空字符串 — 最高能量，可能触发边界行为
                seed.energy = 1.0
            else:
                # 能量与长度成反比，并保证不低于最小值
                energy = 1.0 / length
                seed.energy = max(energy, self.min_energy)
