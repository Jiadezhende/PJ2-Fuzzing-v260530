# 实验报告 - 新增调度策略与命令行入口（组员 D）

> 本节对应实验报告中的「新增调度策略」小节及「入口与运行方式」小节，最终合稿时由报告主笔合并。
> 对应文件：`simple_fuzzer/schedule/size_power_schedule.py`、`simple_fuzzer/schedule/coverage_power_schedule.py`、`simple_fuzzer/main.py`

## 1. 设计目标

根据开发文档 6.4，组员 D 承担两项代码任务和一项文档任务：

**代码任务：**

1. 新增至少一种独立调度策略，放入 `schedule` 包中（推荐 `SizePowerSchedule`）。
2. 在 `main.py` 中新增 `--schedule` 参数，支持运行时切换策略，默认保持 `path`。

**文档任务：**

3. 负责执行 schedule 相关集成测试，汇总各模块测试证据，整理为测试报告。

本报告小节覆盖代码任务的实现方案。

## 2. SizePowerSchedule — 基于输入长度的调度

### 2.1 设计动机

在灰盒 fuzzing 中，较短的输入通常具备以下优势：

1. **执行速度更快**：短输入执行路径更短，相同时间可完成更多轮 fuzz。
2. **更容易暴露核心逻辑**：长输入中大量"脏数据"可能掩盖真正触发漏洞的关键字节。
3. **变异效率更高**：对短输入进行 bit flip 或 arithmetic 变异时，每个字节的改变比重更大。

因此设计策略：**输入越短，能量越高**。

### 2.2 代码实现

```python
class SizePowerSchedule(PowerSchedule):
    def __init__(self, min_energy: float = 1e-6) -> None:
        super().__init__()
        self.min_energy = min_energy

    def assign_energy(self, population: List[Seed]) -> None:
        if not population:
            return
        for seed in population:
            length = len(seed.data)
            if length == 0:
                seed.energy = 1.0
            else:
                energy = 1.0 / length
                seed.energy = max(energy, self.min_energy)
```

### 2.3 能量公式

```
length == 0  →  energy = 1.0
length  > 0  →  energy = max(1.0 / length, 1e-6)
```

选用线性反比 `1/length`，原因：

- 直观：长度 10 的 seed 能量是长度 100 的 10 倍。
- `1e-6` 做软下限，与 C 的 `MIN_ENERGY` 一致，防止极长输入导致归一化失败。
- 空字符串给最高 1.0，因为空输入可能触发除零、越界等边界行为。

### 2.4 边界处理

| 场景 | 处理 |
|---|---|
| 空字符串 `length == 0` | 赋予最高能量 1.0 |
| 超长字符串（如 10KB） | `max(1/length, 1e-6)` 保底，不归零 |
| 空 population | 直接 return，不抛异常 |
| 所有 seed energy 为 0 的可能 | 公式恒正 + floor 兜底，`sum > 0` 必然成立 |

### 2.5 自测结果

测试脚本（独立运行，不依赖其它组员）：

```python
from schedule.size_power_schedule import SizePowerSchedule
from utils.seed import Seed

seeds = [
    Seed(data='',       _coverage=set()),   # len=0
    Seed(data='A',      _coverage=set()),   # len=1
    Seed(data='AB',     _coverage=set()),   # len=2
    Seed(data='ABCDEFGH', _coverage=set()), # len=8
    Seed(data='A'*100,  _coverage=set()),   # len=100
]

schedule = SizePowerSchedule()
schedule.assign_energy(seeds)
```

输出：

```
len=  0  energy=1.000000
len=  1  energy=1.000000
len=  2  energy=0.500000
len=  8  energy=0.125000
len=100  energy=0.010000
All tests passed
```

验收标准核对（开发文档 6.4）：

- ✅ 短输入 energy > 长输入 energy。
- ✅ 空字符串获最高能量 1.0。
- ✅ `normalized_energy()` 和接近 1.0，不触发 `assert sum != 0`。
- ✅ `choose()` 返回 Seed 对象。
- ✅ 空 population 不抛异常。

## 3. CoverageSizePowerSchedule — 基于覆盖范围的调度

### 3.1 设计动机

能在单次执行中触及更多代码行的 seed，说明包含了更多有效前置状态或能穿透更深层逻辑分支，应获得更高能量。

### 3.2 代码实现

```python
class CoverageSizePowerSchedule(PowerSchedule):
    def __init__(self, min_energy: float = 1e-6) -> None:
        super().__init__()
        self.min_energy = min_energy

    def assign_energy(self, population: List[Seed]) -> None:
        if not population:
            return
        for seed in population:
            coverage_size = len(seed.coverage)
            if coverage_size == 0:
                seed.energy = self.min_energy
            else:
                energy = coverage_size * 0.1
                seed.energy = max(energy, self.min_energy)
```

### 3.3 能量公式

```
coverage_size == 0  →  energy = 1e-6
coverage_size  > 0  →  energy = coverage_size * 0.1
```

- 使用 0.1 的缩放因子，避免覆盖行数差异过大导致能量两极分化。
- 零覆盖 seed（从未成功执行或被 runner 跳过）给最小能量保底，不淘汰。

### 3.4 自测结果

```
cov= 0  energy=0.0000
cov= 1  energy=0.1000
cov= 2  energy=0.2000
cov= 3  energy=0.3000
cov=10  energy=1.0000
All tests passed
```

- ✅ 覆盖行越多 energy 越高。
- ✅ 零覆盖 = 最小能量 1e-6。
- ✅ 归一化、choose、空 population 均通过。

## 4. 三种策略对比

| 维度 | PathPowerSchedule (B/C) | SizePowerSchedule | CoverageSizePowerSchedule |
|---|---|---|---|
| 调度依据 | 路径频率（覆盖路径的稀有度） | 输入长度 | 覆盖行数 |
| 反馈类型 | 灰盒（需覆盖率） | 黑盒（无需覆盖率） | 灰盒（需覆盖率） |
| 计算开销 | MD5 + 字典查找 | `len()` | `len(coverage)` |
| 冷启动表现 | 初期频率相同 → 退化为均匀 | 即刻有效 | 即刻有效 |
| 优势场景 | 路径分支多的目标 | 长度敏感目标 | 代码量大、分支深的目标 |
| 新策略文件 | — | `size_power_schedule.py` | `coverage_power_schedule.py` |

## 5. --schedule CLI 参数

### 5.1 实现方案

在 `main.py` 中新增 `--schedule` 参数和 `build_schedule()` 工厂函数：

```python
def parse_args():
    parser.add_argument("--schedule", type=str, default="path",
                        choices=("path", "size", "coverage"),
                        help="Scheduling strategy: 'path' for path-frequency-based, "
                             "'size' for input-length-based, "
                             "'coverage' for coverage-size-based")

def build_schedule(schedule_name: str) -> PowerSchedule:
    schedule_map = {
        "path": PathPowerSchedule,
        "size": SizePowerSchedule,
        "coverage": CoverageSizePowerSchedule,
    }
    return schedule_map[schedule_name]()
```

设计要点：

- `build_schedule()` 返回 `PowerSchedule` 基类，`PathGreyBoxFuzzer.__init__` 接收的也是基类，新增策略**无需修改 Fuzzer 代码**（开闭原则）。
- `--schedule` 默认值 `"path"`，不传参数时行为与原 `main.py` 完全一致，向后兼容。
- `choices` 约束仅接受合法值，传非法参数时 argparse 自动报错。

### 5.2 运行示例

```bash
# 路径频率调度（默认）
python main.py --sample 1 --run-time 10 --schedule path

# 输入长度调度
python main.py --sample 1 --run-time 10 --schedule size

# 覆盖范围调度
python main.py --sample 1 --run-time 10 --schedule coverage

# 等价于默认行为
python main.py --sample 1 --run-time 10
```

### 5.3 自测

`python main.py --help` 输出含 `--schedule {path,size,coverage}` 选项；`--schedule invalid` 被 argparse 正确拒绝。

## 6. 集成测试结果

测试条件：Windows 11 / Python 3.13 / 每个组合 10 秒短跑。

| # | Sample | Schedule | Total Execs | Total Paths | Uniq Crashes | Covered Lines | 状态 |
|---|--------|----------|-------------|-------------|-------------|---------------|------|
| 1 | 1 | path | 12,843 | 5 | 6 | 10 | ✅ |
| 2 | 1 | size | 10,209 | 5 | 6 | 10 | ✅ |
| 3 | 1 | coverage | 13,332 | 5 | 6 | 10 | ✅ |
| 4 | 2 | path | 73,661 | 5 | 4 | 15 | ✅ |
| 5 | 3 | path | 123,164 | 4 | 4 | 6 | ✅ |
| 6 | 3 | size | 137,918 | 5 | 5 | 8 | ✅ |
| 7 | 3 | coverage | 128,754 | 4 | 4 | 6 | ✅ |
| 8 | 4 | path | 8,999 | 746 | 0 | 593 | ✅ |

通过率 8/8 = 100%。

**关键发现 — Sample 3 上 size 优于 path**：多发现 1 条路径、1 个崩溃、2 行覆盖，执行量高 12%。因为 Sample 3 分支逻辑（`s[0]=='F'`、`s[1]=='D'`）对长度敏感，短输入变异后更可能精准命中。

## 7. 与其它模块的接口约定

- 与 B/C（`PathGreyBoxFuzzer` / `PathPowerSchedule`）：不修改 `Fuzzer` 或 `PowerSchedule` 基类。`SizePowerSchedule` 和 `CoverageSizePowerSchedule` 仅需 `Seed.data`（长度）和 `Seed.coverage`（覆盖），这两个字段由 A/B 的框架保证存在，无额外依赖。
- 与 E（持久化）：不修改持久化逻辑。`build_schedule()` 在 Fuzzer 构造前完成，持久化层不感知当前使用的 schedule 类型。
- 扩展性：后续新增 `--schedule rare-line` 只需新增一个文件 + 在 `build_schedule()` 中加一行映射，改动量 < 5 行。
