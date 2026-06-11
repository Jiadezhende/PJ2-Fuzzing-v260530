# 实验报告 - 变异策略实现（组员 A）

> 本节对应实验报告中的「变异策略实现」小节，最终合稿时由报告主笔合并。
> 对应文件：`simple_fuzzer/utils/mutator.py`
> 自测脚本：`simple_fuzzer/tests/test_mutator.py`

## 1. 设计目标

变异器是灰盒模糊测试的输入引擎，目标是从已有 seed 出发产生**多样化且稳定**的
测试输入。具体到本模块需要做到：

1. 覆盖实验说明要求的全部基础变异策略。
2. 对空串、短串、非 ASCII 输入等边界输入**永不抛异常**。
3. 所有 mutator 输入为 `str`，输出也为 `str`。
4. 避免变异后输入无限膨胀（单次输出长度设上限）。
5. 模块自包含，不依赖 runner / coverage / schedule，便于独立自测。

## 2. 变异策略清单

`Mutator` 聚合 9 个模块级策略函数，覆盖实验说明的全部必需项：

| 策略函数 | 说明 | 必需项 |
|---|---|---|
| `insert_random_character` | 随机位置插入一个可打印 ASCII 字符 | 随机插入字符 |
| `delete_random_bytes` | 删除相邻 N(1/2/4) 字节 | 随机删除字符/字节 ✨新增 |
| `replace_random_bytes` | 将相邻 N 字节替换为随机可打印 ASCII | 随机替换字符/字节 ✨新增 |
| `flip_random_bits` | 翻转相邻 N(1/2/4) 位 | bit flip |
| `arithmetic_random_bytes` | 相邻 N 字节加减 [-35,35]（模 256） | arithmetic inc/dec |
| `interesting_random_bytes` | 相邻 N 字节替换为 interesting value | interesting values |
| `havoc_random_insert` | 随机插入一段（75% 取自原文 / 25% 随机字节） | 随机块插入 |
| `havoc_random_replace` | 随机替换一段（75% 取自原文 / 25% 随机字节） | 随机块替换 |
| `random_block_swap` | 交换两段相邻字节块 | 随机块交换 |

> ✨ 标注的两项是本轮新增。原代码缺少「随机删除」与普通「随机替换」，
> 仅有 interesting-value 替换和块替换，故补齐。

字节级策略统一通过 `bytearray(s.encode('utf-8'))` 操作，
再以 `.decode('utf-8', errors='ignore')` 还原为 `str`，
天然处理多字节 UTF-8 被切断的情况，不会抛解码异常。

## 3. 健壮性与长度控制

核心改动集中在 `Mutator.mutate()`，把健壮性收口在统一入口，
而不是散落在每个策略里（符合「不重复」的代码规范）：

```python
MAX_INPUT_LENGTH = 4096

def mutate(self, inp: str) -> str:
    # 保证输入为 str
    if not isinstance(inp, str):
        inp = str(inp)

    mutator = random.choice(self.mutators)
    try:
        result = mutator(inp)
    except Exception:
        result = inp  # 任意策略异常时回退原输入，保证 mutate 永不抛异常

    # 保证输出为 str，并截断防止输入无限膨胀
    if not isinstance(result, str):
        result = inp
    if len(result) > MAX_INPUT_LENGTH:
        result = result[:MAX_INPUT_LENGTH]
    return result
```

设计要点：

- **输入归一**：非 `str` 入参强制 `str(inp)`，对接口契约容错。
- **异常兜底**：任意策略抛异常时回退原输入，保证连续运行不中断。
- **类型保证**：输出非 `str` 时回退原输入，满足 `str → str` 约定。
- **长度上限**：`MAX_INPUT_LENGTH = 4096`。`create_candidate()` 会叠加最多
  32 次变异，含多个插入类策略，不设上限输入会无限膨胀、拖慢覆盖率采集；
  统一在出口截断即可。

## 4. 边界情况

| 场景 | 处理 |
|---|---|
| 空串 `""` | 各字节级策略 `if not s: return s`；插入类仍可产出（保证多样性） |
| 单字符 / 短串（不足 N 字节） | `delete`/`replace` 退化为操作 1 字节，其余策略 `len(data) < N` 时返回原串 |
| 非 ASCII（如「中文输入」） | `encode/decode(errors='ignore')`，切断的多字节序列被丢弃而非报错 |
| 超长串（> 4096） | `mutate()` 出口截断到 4096 |
| 非 str 入参（int/None/bytes） | `mutate()` 入口 `str(inp)` 归一 |
| 策略内部意外异常 | `try/except` 回退原输入 |

## 5. 自测结果

自测脚本 `simple_fuzzer/tests/test_mutator.py` 自包含（顶部插入 `sys.path`，
任意工作目录可跑），不依赖其它组员进度。覆盖四类断言：

```bash
$ cd simple_fuzzer && python3 tests/test_mutator.py
[PASS] 1000 次变异无异常，输出均为 str 且长度受控
[PASS] 多样性测试：200 次变异得到 194 种不同结果
[PASS] 策略可达性：共 9 个策略，必需策略齐全
[PASS] 非 str 输入被安全处理
mutator smoke test passed
```

测试输入集覆盖：`["", "a", "123", "FDULAB", "<html></html>", "中文输入", "x"*5000]`。

验收标准核对（开发文档 6.1）：

- ✅ `Mutator().mutate(inp)` 连续运行 1000 次不抛异常（7 类输入 × 1000 次）。
- ✅ mutation 结果存在多样性（200 次得到 194 种不同结果，非恒等返回）。
- ✅ sample1–4 短跑不因 mutator 自身异常中断（见下）。

集成 smoke（10 秒短跑，`--quiet`）：

```bash
python3 main.py --sample 1 --run-time 10 --quiet   # OK，10 covered lines / 6 crashes
python3 main.py --sample 2 --run-time 10 --quiet   # OK
python3 main.py --sample 3 --run-time 10 --quiet   # OK
python3 main.py --sample 4 --run-time 10 --quiet   # OK，数百 covered lines / 0 crashes
```

四个 sample 均跑满 10 秒、无 mutator 抛错，输出长度始终 ≤ 4096。

> 运行环境注意：本机 `python` 命令不存在，需用 `python3`。

## 6. 与其它模块的接口约定

- 与 fuzzer（`GreyBoxFuzzer.create_candidate`）：仅暴露 `Mutator().mutate(str) -> str`，
  接口签名不变，叠加变异逻辑（`trials` 次循环）保持原样。
- 本模块**不依赖** runner / coverage / schedule / seed，
  保证可独立自测，也不会影响 B/C/D/E 的并行开发。
