# 给组员 B 的接口约定备忘（C → B）

> 本备忘仅用于 B/C 联调期间对齐接口，避免后续合并时返工。
> 我（C）这边的实现已经完成并自测通过：`simple_fuzzer/schedule/path_power_schedule.py`。

## 1. 我对 seed 的期望

```python
seed.path_id: str | None
```

- 类型：`str`（建议是 MD5 hex），或者 `None`。
- 没有这个属性也不会崩 —— 我用 `getattr(seed, "path_id", None)` 取，
  缺失时 fallback 到 energy = 1.0。
- 但只有在 seed 真的有 `path_id` 时，路径频率调度才真正生效。

请按开发文档 5.2 的方式生成：

```python
from utils.object_utils import get_md5_of_object

path = tuple(sorted(runner.coverage()))
path_id = get_md5_of_object(path)
```

注意 `runner.coverage()` 在某些情况下可能是 `None`（例如目标函数抛异常前
什么都没采集到）—— 请在 B 这边判一下，避免传 `None` 给 `tuple(sorted(...))`。

## 2. 我对 fuzzer 的期望

`PathGreyBoxFuzzer.run` 每次执行后调用一次：

```python
self.schedule.update_frequency(path_id)
```

- 即使 `path_id is None` 也可以安全调用（我内部会 return）。
- 频率应在**每次 run** 后累加，不是只在新路径出现时累加 ——
  否则高频路径永远停在 1，体现不出"被冷却"的效果。

## 3. 我已经做的兼容处理

| B 的状态 | C 的行为 |
|---|---|
| B 还没改任何东西 | seed 都没有 path_id，全部走 fallback 给 energy=1.0，等价于均匀调度 |
| B 给 seed 设了 path_id 但忘了调 update_frequency | 所有 path_id 频率都是 1，能量都是 0.5，等价于均匀调度 |
| B 全部接入 | 路径频率反比能量公式真正生效 |

所以 B 可以分两步合并：先把 `seed.path_id` 加上，再补 `update_frequency` 调用，
中间任何状态都不会让 fuzzer 崩。

## 4. 建议 B 在 PathGreyBoxFuzzer.run 里的接入位置

伪代码（不是最终实现，仅供参考，B 自行决定细节）：

```python
def run(self, runner):
    result, outcome = super().run(runner)

    cov = runner.coverage()
    path_id = None
    if cov:
        path_id = get_md5_of_object(tuple(sorted(cov)))

    # —— C 关心的两件事 ——
    self.schedule.update_frequency(path_id)
    # 给 super().run 里刚加入 population 的 seed 补上 path_id
    if self.population and outcome == Runner.PASS:
        last = self.population[-1]
        if not getattr(last, "path_id", None):
            last.path_id = path_id

    # —— 接下来是 B 自己的路径统计字段 ——
    # seen_paths / last_path_time / total_paths

    return result, outcome
```

注意 `super().run` 里只在**新覆盖**时才往 population 加 seed，
所以判 `len(self.population)` 变化或者 `outcome == PASS` 都行。
B 自己的 `seen_paths` 字段更准确，可以直接用那个判。

## 5. print_stats 的列我没碰

`Total Paths` 和 `Last New Path` 两列是 B 的字段（`total_paths` /
`last_path_time`），我这边的能量公式不需要它们，请按 B 自己的设计填。

## 6. 验证联调成功的快速方法

B 接入后跑：

```bash
python main.py --sample 1 --run-time 10 --quiet
```

然后在调度器上加一行临时打印 `print(self.path_frequency)`，
应该能看到：

- 字典非空。
- 大多数 path_id 频率都 ≥ 2（说明 update_frequency 在每次 run 后都调了）。
- 高频路径多的话 energy 会被压到 1e-6 floor —— 这是预期，不是 bug。

有问题随时找我。
