# PJ2 - 模糊测试（Fuzzing）开发文档

## 1. 文档信息

- 项目名称：PJ2 - 模糊测试（Fuzzing）
- 开发周期：2026-06-10 至 2026-06-21
- 截止日期：2026-06-21
- 当前日期：2026-06-10
- 开发模式：5 人并行开发，模块解耦，集中集成
- 本轮要求：不安排阶段汇报，按文档推进开发、联调、测试、报告与提交

## 2. 项目目标

本项目基于现有 `simple_fuzzer` 简易灰盒模糊测试框架，补齐实验说明要求的关键能力，使其能够完成可复现的模糊测试流程。

最终需要完成：

1. 完善输入变异策略，使 Fuzzer 能产生多样化且稳定的测试输入。
2. 实现基于路径频率的灰盒调度逻辑，使稀有路径获得更高变异机会。
3. 新增至少一种独立调度策略，并放入 `schedule` 包。
4. 使用 `object_utils` 对 seed、crash 或中间结果进行运行中持久化，避免长时间运行时内存持续增长。
5. 完成基本自测、集成测试和最终提交材料准备。

## 3. 现有代码分析

### 3.1 项目结构

```text
simple_fuzzer/
├── main.py
├── corpus/
├── fuzzer/
│   ├── fuzzer.py
│   ├── grey_box_fuzzer.py
│   └── path_grey_box_fuzzer.py
├── runner/
│   ├── runner.py
│   └── function_coverage_runner.py
├── samples/
│   └── samples.py
├── schedule/
│   ├── power_schedule.py
│   └── path_power_schedule.py
└── utils/
    ├── coverage.py
    ├── mutator.py
    ├── object_utils.py
    └── seed.py
```

### 3.2 当前可用能力

- `main.py` 已支持选择样例、加载语料库、启动 Fuzzer、保存最终结果。
- `GreyBoxFuzzer` 已实现基础灰盒流程：取 seed、变异、运行、统计覆盖率和 crash。
- `FunctionCoverageRunner` 已能执行目标 Python 函数并采集覆盖率。
- `PowerSchedule` 已提供基础等权重调度。
- `object_utils` 已提供对象序列化、反序列化和对象 MD5 工具。

### 3.3 主要缺口

- `path_grey_box_fuzzer.py` 中路径统计逻辑尚未实现。
- `path_power_schedule.py` 中路径频率调度尚未实现。
- `mutator.py` 虽已有若干策略，但需要补齐稳定性、边界处理和策略覆盖。
- 缺少新的调度策略。
- 当前只在运行结束后保存结果，没有对 seed 或 crash 进行运行中持久化。
- 缺少统一的命令行参数、测试方式和验收标准。

## 4. 总体设计

### 4.1 核心流程

```text
读取初始 corpus
    ↓
选择 seed
    ↓
执行多次 mutate
    ↓
runner 执行目标函数并采集 coverage
    ↓
根据 coverage 生成路径标识 path_id
    ↓
发现新覆盖或 crash 时更新统计
    ↓
持久化有价值 seed / crash / 中间结果
    ↓
schedule 根据 seed 特征重新分配 energy
```

### 4.2 模块边界

- `utils/mutator.py`：只负责输入变异，不依赖 runner、coverage 或 schedule。
- `fuzzer/path_grey_box_fuzzer.py`：负责路径统计、路径时间、路径数量和将路径信息绑定到 seed。
- `schedule/path_power_schedule.py`：只负责根据路径频率为 seed 分配 energy。
- 新增调度策略：只依赖 `Seed` 对象已有字段，避免与路径调度耦合。
- 持久化逻辑：优先作为 Fuzzer 的辅助能力接入，不改变调度算法。

## 5. 关键接口约定

### 5.1 Seed 扩展字段

建议在 `Seed` 对象中扩展以下字段：

```python
seed.path_id: str | None
seed.created_at: float
seed.saved_path: str | None
```

其中 `path_id` 用于路径频率调度，`saved_path` 用于记录 seed 是否已经落盘。

### 5.2 路径标识

路径标识建议基于单次执行覆盖率生成：

```python
path = tuple(sorted(runner.coverage()))
path_id = get_md5_of_object(path)
```

这样可以避免直接使用大对象作为字典 key，也方便持久化。

### 5.3 PathPowerSchedule 接口

建议提供：

```python
class PathPowerSchedule(PowerSchedule):
    def update_frequency(self, path_id: str) -> None:
        ...

    def assign_energy(self, population: Sequence[Seed]) -> None:
        ...
```

`PathGreyBoxFuzzer` 每次执行后调用 `update_frequency(path_id)`，调度器在选择 seed 前调用 `assign_energy(population)`。

### 5.4 新调度策略接口

新增策略继承 `PowerSchedule`，保持：

```python
def assign_energy(self, population: List[Seed]) -> None:
    ...
```

不修改 `choose()` 的调用方式，保证可以与现有主流程兼容。

### 5.5 持久化接口

建议复用 `object_utils`：

```python
dump_object(path, seed)
load_object(path)
get_md5_of_object(seed)
```

推荐保存路径：

```text
_result/
├── seeds/
├── crashes/
├── snapshots/
└── Sample-*.pkl
```

## 6. 任务分工

### 6.1 组员 A：输入变异器

负责文件：

- `simple_fuzzer/utils/mutator.py`

工作内容：

1. 检查现有变异策略，修复空字符串、短字符串、非 ASCII 输入导致的异常。
2. 至少保证以下策略可用：
   - 随机插入字符
   - 随机删除字符或字节
   - 随机替换字符或字节
   - bit flip
   - arithmetic inc/dec
   - interesting values
   - 随机块插入、替换或交换
3. 保证所有 mutator 输入为 `str`，输出也为 `str`。
4. 避免 mutation 后输入无限膨胀，建议设置单次输入最大长度，例如 4096。
5. 增加简单自测脚本或测试用例，覆盖空串、单字符、普通字符串、长字符串。

验收标准：

- `Mutator().mutate(inp)` 连续运行 1000 次不抛异常。
- mutation 结果存在多样性，不总是返回原输入。
- 对 `sample1` 至 `sample4` 的短跑不因 mutator 自身异常中断。

预计工作量：

- 开发：1.0 天
- 自测与修复：0.5 天
- 合计：1.5 人日

### 6.2 组员 B：路径灰盒 Fuzzer

负责文件：

- `simple_fuzzer/fuzzer/path_grey_box_fuzzer.py`
- 必要时修改 `simple_fuzzer/utils/seed.py`

工作内容：

1. 在 `PathGreyBoxFuzzer` 中维护路径统计字段：
   - `seen_paths`
   - `last_path_time`
   - `total_paths`
2. 每次运行后根据 `runner.coverage()` 生成 `path_id`。
3. 新路径出现时更新 `seen_paths`、`last_path_time`、`total_paths`。
4. 将 `path_id` 绑定到新加入 population 的 seed。
5. 修复状态打印中的空字段，使路径数量和最近新路径时间能正确显示。
6. 与组员 C 对齐 `PathPowerSchedule.update_frequency(path_id)` 调用方式。

验收标准：

- 运行时 `Total Paths` 能增长。
- `Last New Path` 能显示真实时间差。
- 每个进入 population 的 seed 都有可用于调度的路径信息。
- 不破坏 `GreyBoxFuzzer` 原有覆盖率和 crash 统计逻辑。

预计工作量：

- 开发：1.5 天
- 联调：0.5 天
- 合计：2.0 人日

### 6.3 组员 C：路径频率调度

负责文件：

- `simple_fuzzer/schedule/path_power_schedule.py`

工作内容：

1. 实现路径频率字典：

```python
self.path_frequency: Dict[str, int]
```

2. 实现 `update_frequency(path_id)`，每次路径被执行后频率加 1。
3. 实现 `assign_energy(population)`：
   - 路径越少见，能量越高。
   - 没有 `path_id` 的 seed 给默认能量。
   - 所有 seed 能量必须大于 0。
4. 处理除零、空 population、极端频率差异等边界情况。
5. 保持与 `PowerSchedule.choose()` 兼容。

推荐能量公式：

```python
frequency = max(1, self.path_frequency.get(seed.path_id, 1))
seed.energy = 1.0 / frequency
```

如果希望更贴近“指数反比”，可以使用：

```python
seed.energy = 2.0 ** (-frequency)
```

但需注意频率过高时能量过小，建议设置最小值，例如 `1e-6`。

验收标准：

- 同一路径频率增加后，该路径 seed 被选中的概率下降。
- 罕见路径 seed 的 energy 高于高频路径 seed。
- `normalized_energy()` 不触发 `assert sum_energy != 0`。

预计工作量：

- 开发：1.0 天
- 与 B 联调：0.5 天
- 合计：1.5 人日

### 6.4 组员 D：新增调度策略与命令行选择

负责文件：

- `simple_fuzzer/schedule/size_power_schedule.py`
- 或 `simple_fuzzer/schedule/coverage_power_schedule.py`
- `simple_fuzzer/main.py`
- `PJ2 - 模糊测试（Fuzzing）测试报告.pdf`

工作内容：

1. 新增至少一种调度策略。
2. 推荐优先实现 `SizePowerSchedule`：
   - 输入越短，执行更快，energy 越高。
   - 对空字符串和超长字符串做边界处理。
3. 可选实现 `CoverageSizePowerSchedule`：
   - 单个 seed 覆盖行越多，energy 越高。
4. 在 `main.py` 中新增 `--schedule` 参数：

```text
--schedule path
--schedule size
--schedule coverage
```

5. 保持默认行为为 `path`，避免影响原实验入口。
6. 负责执行 schedule 相关集成测试，记录命令、输出摘要和结果文件路径。
7. 担任测试报告负责人，汇总 A/B/C/E 提供的测试证据，整理为测试报告 PDF。
8. 测试报告需包含运行环境、测试命令、样例参数、覆盖率、路径数量、crash 统计和关键日志或截图。

验收标准：

- `python main.py --sample 1 --run-time 5 --schedule path` 可运行。
- `python main.py --sample 1 --run-time 5 --schedule size` 可运行。
- 新策略文件放在 `schedule` 包中，命名清晰。
- 新策略不依赖 `PathGreyBoxFuzzer` 的内部实现。
- 测试报告 PDF 内容完整，命令和结果可复现。

预计工作量：

- 开发：1.0 天
- 自测与接入：0.5 天
- 测试报告整理：1.0 天
- 合计：2.5 人日

### 6.5 组员 E：持久化与提交汇总

负责文件：

- `simple_fuzzer/utils/object_utils.py`
- `simple_fuzzer/fuzzer/grey_box_fuzzer.py`
- `simple_fuzzer/fuzzer/path_grey_box_fuzzer.py`
- `simple_fuzzer/main.py`
- 最终提交包目录或压缩包

工作内容：

1. 设计运行中持久化目录：

```text
_result/
├── seeds/
├── crashes/
└── snapshots/
```

2. 发现有价值 seed 时落盘：
   - 新覆盖 seed
   - 新路径 seed
   - crash 输入
3. 使用 `get_md5_of_object()` 或输入内容 hash 生成文件名，避免重复保存。
4. 增加 population 上限策略：
   - 内存中保留高价值 seed。
   - 低价值 seed 已落盘后可从内存中淘汰。
5. 保证最终 `Sample-*.pkl` 仍正常生成。
6. 向 D 提供持久化相关测试证据，包括结果目录截图或文件列表、seed/crash 文件数量和复现命令。
7. 向实验报告负责人提供持久化方案说明，说明保存对象、目录结构、去重方式和内存控制思路。
8. 检查最终提交包内容，确保代码、实验报告、测试报告 PDF 和必要结果文件齐全。
9. 负责最终提交包汇总，不负责单独主笔两份报告。

验收标准：

- 运行过程中 `_result/seeds/` 或 `_result/crashes/` 有文件生成。
- 长时间运行时 population 不无限增长。
- crash 去重逻辑不被破坏。
- 4 个 sample 都能至少短跑 10 秒完成。
- 最终提交包清单明确，无遗漏文件。

预计工作量：

- 开发：1.5 天
- 测试证据整理：0.5 天
- 提交包检查：0.5 天
- 合计：2.5 人日

### 6.6 报告与提交责任分配

报告不再集中压给 E。每名组员必须在对应功能完成后，完成自己负责的小节或测试材料；D 负责测试报告成稿，E 负责最终提交包汇总。

| 组员 | 报告/提交责任 | 截止时间 |
|---|---|---|
| A | 写实验报告中的“变异策略实现”小节，提供 mutator 自测命令与结果 | 2026-06-15 |
| B | 写实验报告中的“路径灰盒 Fuzzer 实现”小节，提供路径数量变化日志 | 2026-06-15 |
| C | 写实验报告中的“路径频率调度策略”小节，提供 energy 公式和调度器自测结果 | 2026-06-15 |
| D | 写“新增调度策略”小节，并主笔测试报告 PDF，汇总各模块测试证据 | 2026-06-18 |
| E | 写“持久化方案”小节，提供结果目录证据，汇总最终提交包清单 | 2026-06-20 |

最终提交内容建议包含：

- 完整代码实现：`simple_fuzzer/`。
- 实验报告：说明需求分析、总体设计、模块实现、遇到的问题和结果分析。
- 测试报告 PDF：说明环境、样例、运行参数、覆盖率、路径数量、crash 统计、日志或截图。
- 运行结果：至少包含关键 `_result/Sample-*.pkl`，可选附带代表性的 seeds/crashes 文件。
- 运行说明：写明如何运行不同 sample 与 schedule。

## 7. 开发排期

项目当前可用周期为 12 个自然日：2026-06-10 至 2026-06-21。考虑课程作业、调试和文档整理，实际编码应在 2026-06-15 前基本完成，2026-06-16 之后进入集成测试、材料整理和提交准备。

### 7.1 里程碑

| 日期 | 阶段 | 目标 |
|---|---|---|
| 2026-06-10 | 启动与任务确认 | 明确需求、模块边界、接口约定和压缩排期 |
| 2026-06-11 至 2026-06-12 | 第一轮开发 | A/C/D 完成初版，B 完成路径 Fuzzer 主结构，E 完成持久化方案 |
| 2026-06-13 至 2026-06-14 | 功能联调 | B/C 联调路径调度，D 接入 main 参数，E 接入 seed 与 crash 持久化 |
| 2026-06-15 | 功能集成 | main 参数、路径调度、新策略、持久化合并，完成代码层面初验 |
| 2026-06-16 至 2026-06-17 | 系统测试与材料收集 | 4 个 sample 短跑和中等时长测试，A/B/C/E 向 D 提交测试证据 |
| 2026-06-18 | 报告初稿 | A/B/C/E 完成实验报告各自小节，D 形成测试报告 PDF 初稿 |
| 2026-06-19 | 代码冻结与报告复核 | 只修 bug，不新增大功能；全员复核报告中自己负责的部分，E 检查提交包结构 |
| 2026-06-20 | 最终验收与提交包 | 完整运行、检查提交文件、补齐并导出测试报告 PDF |
| 2026-06-21 | 提交 | 完成最终提交 |

### 7.2 逐日计划

| 日期 | 计划 |
|---|---|
| 2026-06-10 | Leader 完成需求分析、开发文档和任务拆分；组员阅读对应文件并确认接口 |
| 2026-06-11 | A 完成 mutator 主要策略；B 定义 path_id 并完成路径统计字段；C 完成 path_frequency 框架；D 新建调度策略文件；E 设计持久化目录和去重方案 |
| 2026-06-12 | A 自测并修边界；B 完成 PathGreyBoxFuzzer 主逻辑；C 完成 energy 公式；D 完成新策略核心逻辑和 main 参数；E 接入 seed 保存点 |
| 2026-06-13 | B/C 联调 path schedule；D 测试不同 schedule；E 接入 crash 保存；全员修复第一轮联调问题 |
| 2026-06-14 | 完成路径调度、新策略、持久化合并，确保 sample 1 至 sample 4 均可短跑 |
| 2026-06-15 | 进行 10 秒、30 秒短跑测试；修复路径统计、energy 归一化、持久化重复文件等问题；A/B/C 完成实验报告对应小节初稿 |
| 2026-06-16 | 进行 60 秒测试，比较 path schedule 与新增 schedule；D 汇总 schedule 测试结果和 main 参数说明 |
| 2026-06-17 | 修复测试中发现的问题，补充必要注释和 README 运行说明；A/B/C/E 向 D 提交测试证据 |
| 2026-06-18 | D 完成测试报告 PDF 初稿；A/B/C/D/E 合并实验报告各自小节 |
| 2026-06-19 | 代码冻结，仅允许修复阻塞提交的问题；全员复核报告中自己负责的部分；E 检查提交包结构 |
| 2026-06-20 | 最终完整检查：代码、实验报告、测试报告 PDF、结果文件、提交包清单 |
| 2026-06-21 | 提交 |

## 8. 时间预估

### 8.1 人日预估

| 模块 | 负责人 | 预计人日 |
|---|---|---:|
| 变异器完善与报告小节 | A | 2.0 |
| 路径 Fuzzer 与报告小节 | B | 2.5 |
| 路径频率调度与报告小节 | C | 2.0 |
| 新增调度策略与测试报告 | D | 2.5 |
| 持久化与提交汇总 | E | 2.5 |
| 联调与公共修复 | 全员 | 1.5 |
| 最终复核 | 全员 | 1.0 |
| 总计 | 5 人 | 14.0 人日 |

### 8.2 缓冲安排

从 2026-06-10 到 2026-06-21 共 12 个自然日。实际开发、测试、报告和提交汇总预计 14.0 人日，需要 5 名组员并行推进；排期中保留约 2 天自然时间作为缓冲，主要用于：

- 路径统计与调度接口联调。
- sample 运行时暴露出的边界问题。
- 持久化文件过多、重复保存或路径错误。
- 最终报告、PDF、日志、截图和提交包整理。

## 9. 测试计划

### 9.1 单元级自测

变异器：

```bash
python - <<'PY'
from utils.mutator import Mutator
m = Mutator()
for inp in ["", "a", "123", "FDULAB", "<html></html>", "中文输入"]:
    for _ in range(1000):
        out = m.mutate(inp)
        assert isinstance(out, str)
print("mutator smoke test passed")
PY
```

调度器：

- 构造 3 个 seed，分别赋予不同路径频率。
- 调用 `assign_energy()`。
- 检查低频路径 seed 的 energy 更高。

持久化：

- 保存 seed。
- 重新读取 seed。
- 检查读取对象字段完整。

### 9.2 集成测试

每个样例至少执行：

```bash
python main.py --sample 1 --run-time 10 --schedule path
python main.py --sample 2 --run-time 10 --schedule path
python main.py --sample 3 --run-time 10 --schedule path
python main.py --sample 4 --run-time 10 --schedule path
```

新增 schedule 至少执行：

```bash
python main.py --sample 1 --run-time 10 --schedule size
python main.py --sample 3 --run-time 10 --schedule size
```

最终测试建议：

```bash
python main.py --sample 1 --run-time 60 --schedule path
python main.py --sample 2 --run-time 60 --schedule path
python main.py --sample 3 --run-time 60 --schedule path
python main.py --sample 4 --run-time 60 --schedule path
```

### 9.3 记录指标

测试报告中建议记录：

- Python 版本和运行系统。
- 运行命令。
- 样例编号。
- schedule 类型。
- run time。
- total execs。
- total paths。
- covered lines。
- unique crashes。
- `_result` 下生成的持久化文件数量。

## 10. 验收标准

代码层面：

- 所有 TODO 核心逻辑已完成。
- `mutator.py` 有多种可用变异策略。
- `PathGreyBoxFuzzer` 能统计路径数量。
- `PathPowerSchedule` 能基于路径频率分配 energy。
- 至少新增一种 schedule。
- 运行中能持久化 seed 或 crash。
- 4 个样例都能运行，不因框架异常中断。

提交层面：

- 代码实现完整。
- 实验报告完整。
- 测试报告 PDF 完整。
- 运行结果和关键日志可复现。

## 11. 风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| 变异后字符串解码异常 | Fuzzer 中断 | mutator 内统一处理编码和异常，保证返回 `str` |
| population 为空时调度失败 | 初始阶段崩溃 | 初始 seeds 先执行并加入 population，或在为空时回退随机 seed |
| path_id 过大或不可哈希 | 调度失败或内存增长 | 使用排序后的 coverage tuple 计算 MD5 |
| energy 过小导致归一化失败 | `choose()` 断言失败 | 设置最小能量 `1e-6` |
| 持久化文件重复过多 | 磁盘膨胀 | 使用 hash 去重 |
| 长时间运行内存增长 | 程序变慢或崩溃 | 限制 population 上限，并将低价值 seed 落盘 |
| 最后阶段仍在开发新功能 | 影响提交 | 2026-06-19 代码冻结 |

## 12. 代码规范

- 保持现有项目风格，避免引入不必要依赖。
- 函数名和类名清晰表达调度或变异策略。
- 不做大规模重构。
- 注释只写关键逻辑，例如路径 ID 生成、energy 公式、持久化去重。
- 新增参数必须有默认值，保证原命令能继续运行。
- 所有文件路径使用 `os.path.join()` 或等价跨平台写法。

## 13. 最终提交前检查清单

- [ ] `mutator.py` 多策略变异稳定。
- [ ] `path_grey_box_fuzzer.py` 无 TODO。
- [ ] `path_power_schedule.py` 无 TODO。
- [ ] `schedule` 包中存在新增调度策略。
- [ ] `main.py` 支持选择 schedule。
- [ ] `_result/seeds` 或 `_result/crashes` 能生成持久化文件。
- [ ] sample 1 至 sample 4 均完成短跑测试。
- [ ] 至少一个样例完成 60 秒测试。
- [ ] 覆盖率、路径数量、crash 数量有记录。
- [ ] 实验报告完成。
- [ ] 测试报告 PDF 完成。
- [ ] 2026-06-21 前完成提交。
