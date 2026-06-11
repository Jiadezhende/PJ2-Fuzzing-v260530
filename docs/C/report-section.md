# 实验报告 - 路径频率调度策略（组员 C）

> 本节对应实验报告中的「路径频率调度策略」小节，最终合稿时由报告主笔合并。
> 对应文件：`simple_fuzzer/schedule/path_power_schedule.py`

## 1. 设计目标

灰盒模糊测试的核心直觉是：**罕见路径**比高频路径更可能藏着新覆盖或漏洞。
因此调度器应当让触达罕见路径的 seed 获得更高的被选概率，让触达高频路径的
seed 被更频繁地"冷却"。

具体到实现，本模块需要做到：

1. 每条被执行过的路径都有一个累积频率计数。
2. 每个 seed 的能量与其所对应路径的频率成反比。
3. 与现有 `PowerSchedule.choose()` 流程兼容，不破坏 `normalized_energy()`
   中 `assert sum_energy != 0` 的前提。

## 2. 数据结构

```python
class PathPowerSchedule(PowerSchedule):
    def __init__(self) -> None:
        super().__init__()
        self.path_frequency: Dict[str, int] = {}
```

`path_id` 由 `PathGreyBoxFuzzer` 通过
`get_md5_of_object(tuple(sorted(runner.coverage())))` 生成（见开发文档 5.2），
这里只把它当作字符串 key 使用，不感知具体生成方式，保持模块解耦。

## 3. 频率更新

```python
def update_frequency(self, path_id: str) -> None:
    if path_id is None:
        return
    self.path_frequency[path_id] = self.path_frequency.get(path_id, 0) + 1
```

`PathGreyBoxFuzzer` 每次执行结束后调用一次。`None` 入参直接忽略，避免
B 在路径生成失败的极端情况下污染字典。

## 4. 能量公式

```python
MIN_ENERGY = 1e-6

def assign_energy(self, population: Sequence[Seed]) -> None:
    for seed in population:
        path_id = getattr(seed, "path_id", None)
        if path_id is None:
            seed.energy = 1.0
            continue
        frequency = max(1, self.path_frequency.get(path_id, 1))
        seed.energy = max(MIN_ENERGY, 2.0 ** (-frequency))
```

选用指数反比 `2 ** -frequency`，原因：

- 与开发文档 6.3 给出的"指数反比"建议一致。
- 比线性反比 `1/frequency` 区分度更强：频率从 1 到 10 时，
  线性反比能量从 1.0 降到 0.1（差 10 倍）；指数反比从 0.5 降到 0.001（差 500 倍）。
  能更激进地把变异预算压向罕见路径。
- 高频路径会被快速冷却，但永远不为 0，配合 `MIN_ENERGY` 避免归一化失败。

`MIN_ENERGY = 1e-6` 是软下限，防止频率过高（例如 frequency = 50 时
`2 ** -50 ≈ 8.88e-16`）导致 `normalized_energy()` 中
`sum_energy` 小到浮点下溢触发 `assert`。

无 `path_id` 的 seed（B 还未接入或路径生成失败时）给默认 1.0，
确保它仍能被选中，整个调度流程不依赖 B 的提交进度也能跑。

## 5. 边界情况

| 场景 | 处理 |
|---|---|
| `update_frequency(None)` | 直接 return，不写入字典 |
| seed 没有 `path_id` 字段 | `getattr` fallback 给默认 energy = 1.0 |
| 频率字典里查不到该 path_id | `get(..., 1)`，默认按出现过 1 次处理 |
| 频率极高导致 `2 ** -freq` 下溢 | `max(MIN_ENERGY, ...)` 兜底为 1e-6 |
| 空 population | for 循环自然跳过，不抛异常 |
| seed 全部 energy 为 0 | 公式恒正 + floor 兜底，`sum > 0` 必然成立 |

## 6. 自测结果

测试脚本（独立运行，不依赖其它组员的进度）：

```python
from schedule.path_power_schedule import PathPowerSchedule, MIN_ENERGY
from utils.seed import Seed

s1 = Seed("a", set()); s1.path_id = "P_RARE"
s2 = Seed("b", set()); s2.path_id = "P_MID"
s3 = Seed("c", set()); s3.path_id = "P_HOT"
s4 = Seed("d", set())  # 无 path_id

sched = PathPowerSchedule()
for _ in range(20): sched.update_frequency("P_HOT")
for _ in range(5):  sched.update_frequency("P_MID")
sched.update_frequency("P_RARE")

sched.assign_energy([s1, s2, s3, s4])
```

输出：

```
path=P_RARE freq=1  energy=0.5
path=P_MID  freq=5  energy=0.03125
path=P_HOT  freq=20 energy=1e-06
path=None   freq=None energy=1.0
after burning P_RARE: s1.energy=0.00048828125 (was 0.5)
floor check: s3.energy=1e-06, floor=1e-06
OK: path_power_schedule self-tests passed
```

验收标准核对（开发文档 6.3）：

- ✅ 同一路径频率增加后 energy 下降（P_RARE 从 0.5 降到 ~4.88e-4）。
- ✅ 罕见路径 seed 的 energy 高于高频路径 seed（0.5 > 0.03125 > 1e-6）。
- ✅ `normalized_energy()` 不触发 `assert sum_energy != 0`（所有 energy 恒正）。

集成 smoke：`python main.py --sample 1 --run-time 5 --quiet` 跑通，
33k execs / 10 covered lines / 6 unique crashes，调度器未抛异常。

## 7. 与其它模块的接口约定

- 与 B（`PathGreyBoxFuzzer`）：B 在每次 run 后调用
  `self.schedule.update_frequency(path_id)`，并在新加入 population 的 seed
  上设置 `seed.path_id`。本模块不直接读 `runner.coverage()`，避免与路径
  生成逻辑耦合。
- 与 D（新增调度策略）：本模块不修改 `PowerSchedule.choose()` 与
  `normalized_energy()`，D 的新策略可以平行存在，由 `--schedule` 参数选择。
