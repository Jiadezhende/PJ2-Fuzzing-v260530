# PJ2 - 模糊测试（Fuzzing）实验报告

## 一、实验信息

- **课程名称**：软件质量保障与测试
- **实验名称**：模糊测试（Fuzzing）
- **实验类型**：课程项目
- **小组成员**：A印伟辰 / B丘俊 / C顾祎炜 / D高伟博 / E俞楚凡
- **完成日期**：2026-06-11

### 小组分工

| 组员 | 负责模块 | 对应文件 |
|------|----------|----------|
| 印伟辰 | 输入变异器 | `utils/mutator.py` |
| 丘俊 | 路径灰盒 Fuzzer | `fuzzer/path_grey_box_fuzzer.py`, `utils/seed.py` |
| 顾祎炜 | 路径频率调度 | `schedule/path_power_schedule.py` |
| 高伟博 | 新增调度策略与 CLI 入口、测试报告 | `schedule/size_power_schedule.py`, `schedule/coverage_power_schedule.py`, `main.py` |
| 俞楚凡 | 持久化与运行中落盘 | `fuzzer/grey_box_fuzzer.py`, `fuzzer/path_grey_box_fuzzer.py`, `main.py`, `utils/seed.py` |

---

## 二、实验目的

本实验旨在基于给定的简易 fuzzing 框架，完成输入变异、seed 调度、覆盖率反馈与结果持久化等关键能力，理解灰盒模糊测试的基本流程，并在此基础上形成一个可重复运行、可观察、可分析的实验闭环。

具体目标：

1. 完善输入变异策略，使 Fuzzer 能产生多样化且稳定的测试输入。
2. 实现基于路径频率的灰盒调度逻辑，使稀有路径获得更高变异机会。
3. 新增至少一种独立调度策略。
4. 对 seed、crash 及中间结果进行运行中持久化，避免长时间运行时内存持续增长。
5. 完成集成测试并形成可复现的实验材料。

---

## 三、项目理解

### 3.1 框架结构

项目基于 `simple_fuzzer` 灰盒模糊测试框架，由以下模块组成：

| 模块 | 职责 |
|------|------|
| `fuzzer/` | 控制 fuzz 循环、seed 选择与输入生成 |
| `runner/` | 执行目标样例并返回运行结果与覆盖率 |
| `schedule/` | 对不同 seed 进行能量分配或优先级判断 |
| `utils/` | 提供覆盖率追踪、种子封装、对象持久化与输入变异工具 |
| `samples/` | 提供 4 个用于验证 fuzz 效果的示例程序 |

### 3.2 核心流程

```text
读取初始 corpus
    ↓
选择 seed（schedule 调度）
    ↓
执行多次 mutate
    ↓
runner 执行目标函数并采集 coverage
    ↓
根据 coverage 生成路径标识 path_id
    ↓
发现新覆盖或 crash 时更新统计 + 持久化
    ↓
schedule 根据 seed 特征重新分配 energy → 下一轮
```

### 3.3 模块依赖关系

```
main.py ──→ PathGreyBoxFuzzer ──→ GreyBoxFuzzer ──→ Fuzzer (基类)
                 │                      │
                 ├──→ schedule (PathPowerSchedule / SizePowerSchedule / CoverageSizePowerSchedule)
                 ├──→ Mutator (utils/mutator.py)
                 └──→ object_utils (持久化)
```

所有调度策略均继承 `PowerSchedule` 基类，通过 `main.py` 的 `build_schedule()` 工厂函数在运行时选择，不修改 Fuzzer 核心代码。

---

## 四、实现内容

### 4.1 变异器实现（组员 印伟辰）

> 对应文件：`utils/mutator.py` | 自测脚本：`tests/test_mutator.py`

#### 4.1.1 设计目标

变异器是灰盒模糊测试的输入引擎，目标是：

1. 覆盖实验说明要求的全部基础变异策略。
2. 对空串、短串、非 ASCII 输入等边界输入永不抛异常。
3. 所有 mutator 输入为 `str`，输出也为 `str`。
4. 避免变异后输入无限膨胀（单次输出长度设上限 `MAX_INPUT_LENGTH = 4096`）。
5. 模块自包含，不依赖 runner / coverage / schedule，便于独立自测。

#### 4.1.2 变异策略清单

`Mutator` 聚合 9 个模块级策略函数：

| 策略函数 | 说明 | 类型 |
|----------|------|------|
| `insert_random_character` | 随机位置插入一个可打印 ASCII 字符 | 随机插入 |
| `delete_random_bytes` | 删除相邻 N(1/2/4) 字节（新增） | 随机删除 |
| `replace_random_bytes` | 将相邻 N 字节替换为随机可打印 ASCII（新增） | 随机替换 |
| `flip_random_bits` | 翻转相邻 N(1/2/4) 位 | bit flip |
| `arithmetic_random_bytes` | 相邻 N 字节加减 [-35,35]（模 256） | arithmetic inc/dec |
| `interesting_random_bytes` | 相邻 N 字节替换为 interesting value | interesting values |
| `havoc_random_insert` | 随机插入一段（75% 取自原文 / 25% 随机字节） | 块插入 |
| `havoc_random_replace` | 随机替换一段（75% 取自原文 / 25% 随机字节） | 块替换 |
| `random_block_swap` | 交换两段相邻字节块 | 块交换 |

字节级策略统一通过 `bytearray(s.encode('utf-8'))` 操作，以 `.decode('utf-8', errors='ignore')` 还原为 `str`，天然处理多字节 UTF-8 被切断的情况。

#### 4.1.3 健壮性控制

核心改动集中在 `Mutator.mutate()` 统一入口：

```python
MAX_INPUT_LENGTH = 4096

def mutate(self, inp: str) -> str:
    if not isinstance(inp, str):
        inp = str(inp)
    mutator = random.choice(self.mutators)
    try:
        result = mutator(inp)
    except Exception:
        result = inp   # 异常兜底，永不抛异常
    if not isinstance(result, str):
        result = inp
    if len(result) > MAX_INPUT_LENGTH:
        result = result[:MAX_INPUT_LENGTH]
    return result
```

边界处理：

| 场景 | 处理方式 |
|------|----------|
| 空串 `""` | 各字节级策略 `if not s: return s`；插入类仍可产出保证多样性 |
| 单字符 / 短串（不足 N 字节） | `delete`/`replace` 退化为操作 1 字节 |
| 非 ASCII（如「中文输入」） | `encode/decode(errors='ignore')` 安全处理 |
| 超长串（> 4096） | `mutate()` 出口截断 |
| 非 str 入参 | 入口 `str(inp)` 归一 |
| 策略内部异常 | `try/except` 回退原输入 |

#### 4.1.4 自测结果

```bash
$ python tests/test_mutator.py
[PASS] 1000 次变异无异常，输出均为 str 且长度受控
[PASS] 多样性测试：200 次变异得到 194 种不同结果
[PASS] 策略可达性：共 9 个策略，必需策略齐全
[PASS] 非 str 输入被安全处理
mutator smoke test passed
```

---

### 4.2 调度策略实现

#### 4.2.1 PathPowerSchedule — 路径频率调度（组员 顾祎炜）

> 对应文件：`schedule/path_power_schedule.py`

**设计动机**：灰盒模糊测试的核心直觉是**罕见路径**比高频路径更可能藏着新覆盖或漏洞。因此调度器应当让触达罕见路径的 seed 获得更高的被选概率。

**数据结构**：

```python
class PathPowerSchedule(PowerSchedule):
    def __init__(self) -> None:
        super().__init__()
        self.path_frequency: Dict[str, int] = {}
```

`path_id` 由 丘俊 通过 `get_md5_of_object(tuple(sorted(runner.coverage())))` 生成，顾祎炜 只把它当作字符串 key 使用。

**频率更新**：

```python
def update_frequency(self, path_id: str) -> None:
    if path_id is None:
        return
    self.path_frequency[path_id] = self.path_frequency.get(path_id, 0) + 1
```

`PathGreyBoxFuzzer` 在**每次执行后**调用一次（非仅新路径时），`None` 入参直接忽略。

**能量公式**：

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

选用指数反比 `2 ^ -frequency`：
- 比线性 `1/frequency` 区分度更强：频率从 1 到 10，能量从 0.5 降到 0.001（差 500 倍）
- `MIN_ENERGY = 1e-6` 防止高频路径能量下溢导致归一化断言失败
- 无 `path_id` 的 seed（丘俊 未接入时）给默认 1.0，不阻塞流程

**自测结果**：

```
path=P_RARE freq=1  energy=0.5
path=P_MID  freq=5  energy=0.03125
path=P_HOT  freq=20 energy=1e-06
path=None   freq=None energy=1.0
```

验收标准全部达成：罕见路径能量 > 高频路径，归一化不抛异常。

#### 4.2.2 路径灰盒 Fuzzer（组员 丘俊）

> 对应文件：`fuzzer/path_grey_box_fuzzer.py`, `utils/seed.py`

**Seed 扩展**：

```python
class Seed:
    def __init__(self, data, _coverage):
        self.data = data
        self.coverage = _coverage
        self.energy = 0.0
        self.path_id: Optional[str] = None     # 路径标识
        self.created_at = time.time()           # 创建时间
        self.saved_path: Optional[str] = None   # 落盘路径
```

**路径统计字段**（`PathGreyBoxFuzzer`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `seen_paths` | `Set[str]` | 已发现的唯一路径 ID 集合 |
| `total_paths` | `int` | 路径总数，新路径出现时递增 |
| `last_path_time` | `float` | 最近一次新路径发现的时间戳 |

**路径 ID 生成**：

```python
@staticmethod
def get_path_id(runner) -> Optional[str]:
    coverage = runner.coverage()
    if not coverage:
        return None
    path = tuple(sorted(coverage))
    return get_md5_of_object(path)
```

**run() 流程**：

```python
def run(self, runner):
    existing_seeds = set(self.population)
    result, outcome = super().run(runner)
    path_id = self.get_path_id(runner)

    # 通知调度器更新频率（每次执行后，非仅新路径）
    update_frequency = getattr(self.schedule, "update_frequency", None)
    if callable(update_frequency):
        update_frequency(path_id)

    # 新路径出现
    if path_id is not None and path_id not in self.seen_paths:
        self.seen_paths.add(path_id)
        self.last_path_time = time.time()
        self.total_paths = len(self.seen_paths)

    # 给新加入 population 的 seed 绑定 path_id
    for seed in self.population:
        if seed in existing_seeds:
            continue
        seed.path_id = path_id

    return result, outcome
```

设计要点：
- `update_frequency` 通过 `getattr` + `callable` 安全调用，即使 schedule 不是 `PathPowerSchedule` 也不会崩
- 频率在**每次 run** 后累加（非仅新路径），确保高频路径被正确冷却
- 打印表格含 7 列（含 `Last New Path` 和 `Total Paths`），通过 `is_print` 门控

#### 4.2.3 SizePowerSchedule — 基于输入长度的调度（组员 高伟博）

> 对应文件：`schedule/size_power_schedule.py`

**设计动机**：较短的输入执行更快、更容易暴露核心逻辑、变异时每个字节的改变比重更大。因此 **输入越短，能量越高**。

**能量公式**：

```
length == 0  →  energy = 1.0
length  > 0  →  energy = max(1.0 / length, 1e-6)
```

- 线性反比 `1/length`：长度 10 的 seed 能量是长度 100 的 10 倍
- `1e-6` 软下限，与 顾祎炜 的 `MIN_ENERGY` 一致
- 空字符串获最高 1.0（可能触发除零、越界等边界行为）

**自测结果**：

```
len=  0  energy=1.000000
len=  1  energy=1.000000
len=  2  energy=0.500000
len=  8  energy=0.125000
len=100  energy=0.010000
```

#### 4.2.4 CoverageSizePowerSchedule — 基于覆盖范围的调度（组员 高伟博）

> 对应文件：`schedule/coverage_power_schedule.py`

**设计动机**：能在单次执行中触及更多代码行的 seed，说明包含了更多有效前置状态或能穿透更深层逻辑分支，应获得更高能量。

**能量公式**：

```
coverage_size == 0  →  energy = 1e-6
coverage_size  > 0  →  energy = coverage_size * 0.1
```

- 缩放因子 0.1 避免覆盖行数差异过大导致能量两极分化
- 零覆盖 seed 给最小能量保底，不淘汰

**自测结果**：

```
cov= 0  energy=0.0000
cov= 1  energy=0.1000
cov= 2  energy=0.2000
cov= 3  energy=0.3000
cov=10  energy=1.0000
```

#### 4.2.5 三种调度策略对比

| 维度 | PathPowerSchedule | SizePowerSchedule | CoverageSizePowerSchedule |
|------|-------------------|-------------------|---------------------------|
| 调度依据 | 路径频率（覆盖路径的稀有度） | 输入长度 | 覆盖行数 |
| 反馈类型 | 灰盒（需覆盖率） | 黑盒（无需覆盖率） | 灰盒（需覆盖率） |
| 计算开销 | MD5 哈希 + 字典查找 | `len()` | `len(coverage)` |
| 冷启动表现 | 初期退化为均匀随机 | 即刻有效 | 即刻有效 |
| 优势场景 | 路径分支多、需长期运行 | 长度敏感目标、快速冒烟 | 代码量大、分支深的目标 |
| 负责组员 |  丘俊 + 顾祎炜 | 高伟博 | 高伟博 |

---

### 4.3 持久化与框架优化（组员 俞楚凡）

> 对应文件：`fuzzer/grey_box_fuzzer.py`, `fuzzer/path_grey_box_fuzzer.py`, `main.py`, `utils/seed.py` | 自测脚本：`tests/test_persistence.py`

#### 4.3.1 设计目标

1. 发现新覆盖、新路径或 crash 时及时保存对应对象。
2. 保存周期性 snapshot 与最终 snapshot，便于复现实验过程。
3. 使用 hash 文件名去重，避免同一 seed 或 crash 反复写入。
4. 控制内存中 `population` 规模，防止长时间运行持续累积。
5. 保持原有 `Sample-*.pkl` 输出不变。

#### 4.3.2 目录结构

```text
_result/
├── seeds/          # 新覆盖 seed / 新路径 seed（MD5 去重）
├── crashes/        # 去重后的 crash 记录（MD5 去重）
├── snapshots/      # 周期性快照和 final 快照
└── Sample-*.pkl    # 原有最终结果文件
```

#### 4.3.3 Seed 持久化

在 `GreyBoxFuzzer.run()` 中，如果当前输入带来新全局覆盖且结果为 PASS，则创建 Seed 并保存：

```python
seed = Seed(self.inp, runner.coverage())
self.population.append(seed)
self.persist_seed(seed, "new_coverage")
```

`persist_seed()` 使用输入内容的 MD5 作为文件名，同一输入多次出现会覆盖同名文件实现去重。

#### 4.3.4 Crash 持久化

```python
record = {
    "input": self.inp,
    "crash_id": crash_id,
    "coverage": coverage,
    "total_execs": self.total_execs,
    "created_at": time.time(),
}
```

crash id 由异常栈的 MD5 生成，同一个 crash id 只保存一次。

#### 4.3.5 Snapshot 持久化

周期性 snapshot（默认每 1000 execs）+ `main.py` 末尾的 `persist_snapshot("final")`。内容包括：`total_execs`、`covered_line`、`unique_crashes`、`population_size`、`persisted_seed_count`、`total_paths`、`path_frequency` 等。

#### 4.3.6 内存控制

`trim_population()`：当 population 超过 `MAX_SEEDS`（1000）时，按 `(energy, created_at)` 降序保留。低价值 seed 已被持久化，从内存淘汰不丢失数据。

#### 4.3.7 自测结果

```bash
$ python tests/test_persistence.py
persistence smoke test passed
```

10 秒短跑 4 个 sample 产出：1355 seeds + 13 crashes + 57 snapshots + 4 Sample-*.pkl。

---

### 4.4 入口与运行方式（组员 高伟博）

#### 4.4.1 命令行参数

`main.py` 是本实验的统一入口：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--sample` | `int` (1-4) | `4` | 选择被测样例程序 |
| `--run-time` | `int` | `300` | 运行时长（秒） |
| `--schedule` | `str` (`path`, `size`, `coverage`) | `path` | 调度策略选择（新增） |
| `--output-dir` | `str` | `_result` | 结果持久化目录 |
| `--quiet` | `flag` | `False` | 禁用状态表打印 |

`build_schedule()` 工厂函数：

```python
def build_schedule(schedule_name: str) -> PowerSchedule:
    schedule_map = {
        "path": PathPowerSchedule,
        "size": SizePowerSchedule,
        "coverage": CoverageSizePowerSchedule,
    }
    return schedule_map[schedule_name]()
```

返回 `PowerSchedule` 基类，新增策略无需修改 Fuzzer 代码（开闭原则）。

#### 4.4.2 运行示例

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

#### 4.4.3 结果文件

运行结束后，结果保存至 `_result/Sample-{n}.pkl`，含覆盖率集合、唯一崩溃数和时间戳。中间文件落在 `_result/seeds/`、`_result/crashes/`、`_result/snapshots/` 下。

---

## 五、测试与结果

### 5.1 测试环境

| 项目 | 内容 |
|------|------|
| 操作系统 | Windows 11 Pro 10.0.26200 |
| Python 版本 | 3.13 |
| 项目路径 | `simple_fuzzer/` |
| 被测样例 | sample1 ~ sample4 |

### 5.2 被测样例说明

| Sample | 类型 | 特点 |
|--------|------|------|
| 1 | 数值计算 | 浮点运算、递归、字符串索引 |
| 2 | 字符串解析 | split、format、类型转换 |
| 3 | 分支嵌套 | 多级字符比较（F→D→U）、assert |
| 4 | HTML 解析 | `HTMLParser.feed()` |

### 5.3 单元测试结果

**变异器（印伟辰）**：

```
[PASS] 1000 次变异无异常，输出均为 str 且长度受控
[PASS] 多样性测试：200 次变异得到 194 种不同结果
[PASS] 策略可达性：共 9 个策略，必需策略齐全
[PASS] 非 str 输入被安全处理
```

**路径频率调度（顾祎炜）**：

```
path=P_RARE freq=1  energy=0.5
path=P_MID  freq=5  energy=0.03125
path=P_HOT  freq=20 energy=1e-06
罕见路径能量 > 高频路径能量 ✓
normalized_energy() 不触发 assert ✓
```

**SizePowerSchedule（高伟博）**：

```
len=  0  energy=1.0  >  len=100  energy=0.01  ✓
```

**CoverageSizePowerSchedule（高伟博）**：

```
cov=10  energy=1.0  >  cov=1   energy=0.1  >  cov=0  energy=1e-6  ✓
```

**持久化（俞楚凡）**：

```
persistence smoke test passed
```

### 5.4 集成测试结果（10 秒短跑，8 项全部通过）

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

**通过率**：8/8 = 100%

### 5.5 覆盖率达成情况（≥50% 目标验证）

评分目标要求「Fuzzer 在某一 Scheduler 下，可以在 4 个 Sample 上得到 50%+ 的覆盖率」。下表在 `--schedule path`、每个 sample 运行 30s 的条件下统计**目标样例函数自身**的行覆盖率。

**统计口径**：分母为目标函数体内的全部可执行行数，由 CPython code object 的 `co_lines()` 推导得到，并排除 `def` 声明行（该行在函数体内不会被 line trace 命中）；`sample2` 含其嵌套函数 `can_convert_to_int`。分子为运行结束后落入这些行的覆盖集合。

| Sample | 目标函数 | 覆盖行数 | 可执行行数 | 覆盖率 | ≥50% |
|--------|----------|----------|------------|--------|------|
| 1 | `sample1` | 8 | 8 | **100.0%** | ✅ |
| 2 | `sample2`（含 `can_convert_to_int`） | 13 | 13 | **100.0%** | ✅ |
| 3 | `sample3` | 6 | 9 | **66.7%** | ✅ |
| 4 | `sample4` | 2 | 2 | **100.0%** | ✅ |

**结论**：在 `path` 调度下，4 个 sample 的目标函数覆盖率均 **≥ 50%**（最低 66.7%），满足「Fuzzer 可用性」目标。

补充说明：

- **Sample 3** 未覆盖第 42–44 行（`assert s[index+1] == 'A'` 及其后的 `if not ...startswith('B')` / `raise RuntimeError` 分支）。这些分支要求输入同时满足「以 `FDU` 开头、`ord(s[4])-65 != 0`、含字符 `L` 且其后紧跟 `A`」等多重精确约束，本次 30s 运行未能凑齐全部条件；其余 6/9 行已覆盖，已超过 50% 目标。
- **Sample 4** 函数自身只有 2 行（实例化并调用 `HTMLParser.feed`），其真正价值在于驱动标准库 HTML 解析器：本次运行除自身 2 行外，**额外触达标准库 656 行**（`html.parser`、`re` 等模块），`Total Paths` 高达 746，是 4 个 sample 中路径探索最充分的一个。

### 5.6 结果分析

**1. 路径频率调度（path）已验证**：所有 4 个 sample 的 `Total Paths` 均能增长，`Last New Path` 正确显示时间差。Sample 4（HTML 解析器）路径数量高达 746，远超其他 sample，但 0 crash。

**2. SizePowerSchedule 在 Sample 3 表现最优**：

| 指标 | path | size | 提升 |
|------|------|------|------|
| Total Execs | 123,164 | 137,918 | +12% |
| Total Paths | 4 | **5** | +25% |
| Uniq Crashes | 4 | **5** | +25% |
| Covered Lines | 6 | **8** | +33% |

Sample 3 的分支逻辑（`s[0]=='F'`、`s[1]=='D'`、`s[2]=='U'`）对长度高度敏感：输入的精确长度和每个位置的字节值决定能否穿透三层条件。短输入在变异后更可能精准命中这些关键位置。相比之下，长输入在一次变异中被改变的比例很小，很难同时命中多个条件字符。

**3. CoverageSizePowerSchedule**：Sample 3 上与 path 持平，Sample 1 执行量略高于 path。因为初始 seed 覆盖信息有限，在 10 秒短跑中路径频率调度优势尚未完全展现。

**4. 调度策略互补性**：
- **path**：依靠路径频率反馈，适合长时间运行发现稀有路径
- **size**：冷启动即刻有效，对长度敏感目标高效，适合快速冒烟测试
- **coverage**：覆盖行多的 seed 获高能，适合代码量大、分支深的目标

### 5.7 持久化产出

| 产物 | 数量（4 个 sample 合计） |
|------|--------------------------|
| `Sample-*.pkl` | 4 |
| `seeds/*.pkl` | 1355 |
| `crashes/*.pkl` | 13 |
| `snapshots/*.pkl` | 57 |

### 5.8 终端输出示例

Sample 1 使用 `--schedule path` 运行 10 秒：

```
┌───────────────────────┬───────────────────────┬───────────────────────┬───────────────────┬───────────────────┬────────────────┬───────────────────┐
│        Run Time       │     Last New Path     │    Last Uniq Crash    │    Total Execs    │    Total Paths    │  Uniq Crashes  │   Covered Lines   │
├───────────────────────┼───────────────────────┼───────────────────────┼───────────────────┼───────────────────┼────────────────┼───────────────────┤
│        00:00:01       │        00:00:00       │        00:00:00       │        1627       │         4         │       5        │         10        │
│        00:00:02       │        00:00:01       │        00:00:02       │        3266       │         5         │       6        │         10        │
│        00:00:09       │        00:00:01       │        00:00:09       │       12843       │         5         │       6        │         10        │
├───────────────────────┼───────────────────────┼───────────────────────┼───────────────────┼───────────────────┼────────────────┼───────────────────┤
Covered Lines: 10, Crashes Num: 6
```

---

## 六、总结与反思

### 6.1 收获

1. **对灰盒 fuzzing 形成了完整理解**：通过实现 seed 调度、路径跟踪、覆盖率反馈和持久化闭环，理解了 AFL 类 fuzzer 的核心工作原理。

2. **模块解耦的价值**：5 名组员并行开发 5 个模块，通过清晰接口约定（`PowerSchedule.choose()` 不修改、`Seed` 字段扩展用 `getattr`、`update_frequency` 用 `callable` 判断）实现了零阻塞的并行协作。

3. **调度策略互补性的实证**：通过 8 项集成测试验证了不同调度策略在不同 target 上的表现差异，SizePowerSchedule 在 Sample 3 上优于 PathPowerSchedule，说明**没有万能调度策略，应根据目标特征选择合适的策略**。

### 6.2 难点

1. **丘俊与顾祎炜 联调的接口对齐**：`update_frequency` 的调用时机（每次 run vs 仅新路径时）需要仔细约定，顾祎炜 通过 `getattr` + `callable` 实现了对非 PathPowerSchedule 的兼容。

2. **高伟博与俞楚凡 的 `main.py` 合并冲突**：高伟博 的 `build_schedule()` 和 E 的 `output_dir`/`persist_snapshot("final")` 修改了同一行，但两处改动完全正交，取并集即可。

3. **路径 ID 生成的可哈希性**：`runner.coverage()` 返回 `Set[Location]` 不可哈希，需要先 `tuple(sorted(...))` 再做 MD5，丘俊 的实现正确处理了这一点。

### 6.3 改进空间

1. **更多变异策略**：可引入基于字典的变异（参考 AFL 的 dictionary 模式），对特定协议或格式的目标更有效。

2. **Rare-Line 调度**：开发文档提到「基于罕见代码行的调度」方向（统计每行代码的被触发频率），与现有的三种策略互补，可作为后续扩展。

3. **更稳定的路径统计**：当前路径 ID 基于 `sorted(coverage)`，对于代码行数多的 target（如 Sample 4 有 593 行覆盖），同一路径的微小差异可能产生不同路径 ID。可考虑引入路径剪枝或归一化。

4. **population 上限可配置化**：当前 `MAX_SEEDS = 1000` 是固定值，可通过 `--max-population` 参数暴露给用户。

5. **并行 fuzz**：当前为单进程，可扩展为多进程或 master-slave 模式，进一步提升吞吐量。

---

