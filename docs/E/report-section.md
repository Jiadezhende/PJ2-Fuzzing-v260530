# 实验报告 - 持久化方案与提交汇总（组员 E）

> 本节对应实验报告中的「持久化与框架优化」小节，最终合稿时由报告主笔合并。
> 对应文件：
> `simple_fuzzer/fuzzer/grey_box_fuzzer.py`、
> `simple_fuzzer/fuzzer/path_grey_box_fuzzer.py`、
> `simple_fuzzer/main.py`、
> `simple_fuzzer/utils/seed.py`
> 自测脚本：`simple_fuzzer/tests/test_persistence.py`

## 1. 设计目标

本模块负责把 fuzz 过程中产生的有价值中间结果落盘，避免所有信息只保存在内存中。
具体目标如下：

1. 发现新覆盖、新路径或 crash 时及时保存对应对象。
2. 保存周期性 snapshot 与最终 snapshot，便于复现实验过程和统计结果。
3. 使用 hash 文件名去重，避免同一 seed 或 crash 反复写入。
4. 控制内存中 `population` 的规模，防止长时间运行时 seed 持续累积。
5. 保持原有 `Sample-*.pkl` 结果输出不变，不影响其它组员实现。

## 2. 目录结构

运行时输出目录由 `main.py` 的 `--output-dir` 参数决定，默认是 `_result`。
本模块在该目录下维护如下结构：

```text
_result/
├── seeds/          # 新覆盖 seed / 新路径 seed
├── crashes/        # 去重后的 crash 记录
├── snapshots/      # 周期性快照和 final 快照
└── Sample-*.pkl    # 原有最终结果文件
```

`main.py` 将命令行参数传入 fuzzer：

```python
grey_fuzzer = PathGreyBoxFuzzer(
    seeds=seeds,
    schedule=PathPowerSchedule(),
    is_print=not args.quiet,
    output_dir=args.output_dir,
)
```

这样既保持默认行为兼容，也允许测试时使用独立目录，例如
`--output-dir _result_smoke`。

## 3. Seed 持久化

在 `GreyBoxFuzzer.run()` 中，如果当前输入带来了新的全局覆盖，且执行结果为
`PASS`，则创建 `Seed` 并保存：

```python
seed = Seed(self.inp, runner.coverage())
self.population.append(seed)
self.persist_seed(seed, "new_coverage")
```

在 `PathGreyBoxFuzzer.run()` 中，如果当前输入触发了此前未见过的路径，而它没有
因为新覆盖被保存，则额外以 `new_path` 的原因保存：

```python
seed = Seed(self.inp, coverage)
seed.path_id = path_id
self.population.append(seed)
self.persist_seed(seed, "new_path")
```

每个 seed 会记录以下持久化信息：

| 字段 | 说明 |
|---|---|
| `data` | 原始输入 |
| `coverage` | 本次执行覆盖到的代码行集合 |
| `path_id` | 路径标识，由路径覆盖集合 hash 得到 |
| `saved_path` | seed 落盘路径 |
| `saved_reason` | 保存原因，如 `new_coverage` 或 `new_path` |
| `saved_at` | 保存时间 |

## 4. Crash 持久化

`FunctionCoverageRunner` 将异常栈的 MD5 作为 crash id。`GreyBoxFuzzer.run()`
发现 `Runner.FAIL` 后保存 crash 记录：

```python
record = {
    "input": self.inp,
    "crash_id": crash_id,
    "coverage": coverage,
    "total_execs": self.total_execs,
    "created_at": time.time(),
}
```

crash 文件保存到：

```text
_result/crashes/<hash>.pkl
```

其中 `<hash>` 来自 `get_md5_of_object(crash_id)`。同一个 crash id 只保存一次，
避免同类异常在长时间 fuzz 中反复占用磁盘和内存。

## 5. Snapshot 持久化

为了记录长时间运行的中间状态，fuzzer 支持周期性 snapshot：

```python
snapshot_interval = 1000
```

每执行约 1000 次输入后，保存一个周期快照。`main.py` 在 fuzz 结束后额外保存
`final` 快照：

```python
grey_fuzzer.persist_snapshot("final")
```

snapshot 内容包括：

| 字段 | 说明 |
|---|---|
| `reason` | `periodic` 或 `final` |
| `timestamp` | 快照时间 |
| `total_execs` | 当前总执行次数 |
| `covered_line` | 全局覆盖行集合 |
| `unique_crashes` | 去重 crash id 集合 |
| `population_size` | 当前内存中的 seed 数量 |
| `persisted_seed_count` | 已落盘 seed 数量 |
| `persisted_crash_count` | 已落盘 crash 数量 |
| `total_paths` | 已发现路径数量 |
| `seen_paths` | 路径 id 集合 |
| `path_frequency` | 路径频率字典 |

## 6. 去重与内存控制

### 6.1 去重方式

seed 使用输入内容的 MD5 作为文件名：

```python
seed_id = get_md5_of_object(seed.data)
```

crash 使用 crash id 的 MD5 作为文件名：

```python
crash_key = get_md5_of_object(crash_id)
```

这样同一个输入或同一种 crash 多次出现时会覆盖同名文件或直接跳过，避免重复文件
持续增长。

### 6.2 内存控制

内存中的 `population` 设置上限，默认沿用 `PowerSchedule.MAX_SEEDS = 1000`。
当 seed 数量超过上限时，先让调度器重新分配 energy，再按如下优先级保留：

1. `energy` 更高的 seed。
2. 创建时间更新的 seed。

实现逻辑：

```python
self.schedule.assign_energy(self.population)
self.population.sort(key=lambda seed: (seed.energy, seed.created_at), reverse=True)
del self.population[self.max_population:]
```

这样长时间运行时，历史 seed 已经落盘，内存中只保留较高价值的一部分。

## 7. 自测结果

新增自测脚本 `simple_fuzzer/tests/test_persistence.py`，构造一个小型目标函数，
同时触发新覆盖和 crash，并检查三个目录均生成文件：

```bash
python tests/test_persistence.py
persistence smoke test passed
```

测试断言：

- `_result/seeds/*.pkl` 至少生成 1 个文件。
- `_result/crashes/*.pkl` 至少生成 1 个文件。
- `_result/snapshots/*.pkl` 至少生成 1 个文件。
- `len(fuzzer.population) <= fuzzer.max_population`。

同时保留原有变异器测试：

```bash
python tests/test_mutator.py
mutator smoke test passed
```

## 8. 集成验证

完整入口使用如下命令验证：

```bash
python main.py --sample 1 --run-time 10 --quiet --output-dir _result
python main.py --sample 2 --run-time 10 --quiet --output-dir _result
python main.py --sample 3 --run-time 10 --quiet --output-dir _result
python main.py --sample 4 --run-time 10 --quiet --output-dir _result
```

运行后检查目录：

```bash
dir /s _result
```

本机一次 4 个 sample 的 10 秒短跑结果如下：

| 产物 | 数量 |
|---|---:|
| `Sample-*.pkl` | 4 |
| `seeds/*.pkl` | 1355 |
| `crashes/*.pkl` | 13 |
| `snapshots/*.pkl` | 57 |

说明最终结果文件、新覆盖/新路径 seed、crash 记录和运行快照均已正确落盘。

## 9. 与其它模块的接口约定

- 与 A（mutator）：本模块不改变 `Mutator().mutate(str) -> str` 接口，只保存
  mutator 产生并被 runner 执行后的有价值输入。
- 与 B（`PathGreyBoxFuzzer`）：复用 B 生成的 `path_id` 与路径统计字段，在新路径
  出现时保存 seed，并将 `total_paths`、`seen_paths` 写入 snapshot。
- 与 C（`PathPowerSchedule`）：内存裁剪时调用 `assign_energy()` 获取 seed 价值，
  不改变路径频率调度公式。
- 与 D（测试报告）：提供 `_result` 目录文件数量、运行命令和持久化结构说明，供测试
  报告合稿使用。
