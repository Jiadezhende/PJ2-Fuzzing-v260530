# PJ2 - 模糊测试（Fuzzing）测试报告

## 测试信息

| 项目 | 内容 |
|---|---|
| 课程名称 | 软件质量保障与测试 |
| 实验名称 | 模糊测试（Fuzzing） |
| 负责组员 | D |
| 测试日期 | 2026-06-11 |
| 测试范围 | SizePowerSchedule、CoverageSizePowerSchedule、--schedule CLI、集成测试 |

---

## 1. 测试环境

| 项目 | 内容 |
|---|---|
| 操作系统 | Windows 11 Pro 10.0.26200 |
| Python 版本 | 3.13 |
| 项目路径 | `simple_fuzzer/` |
| 被测样例 | sample1 ~ sample4 |

---

## 2. 单元测试

### 2.1 SizePowerSchedule

**测试用例**：构造 5 个不同长度的 seed，验证能量分配。

```python
seeds = [
    Seed(data='',       _coverage=set()),   # len=0
    Seed(data='A',      _coverage=set()),   # len=1
    Seed(data='AB',     _coverage=set()),   # len=2
    Seed(data='ABCDEFGH', _coverage=set()), # len=8
    Seed(data='A'*100,  _coverage=set()),   # len=100
]
schedule.assign_energy(seeds)
```

**输出**：

```
len=  0  energy=1.000000
len=  1  energy=1.000000
len=  2  energy=0.500000
len=  8  energy=0.125000
len=100  energy=0.010000
```

**验证项**：

| 验证项 | 结果 |
|---|---|
| 空字符串能量最高 (1.0) | ✅ 通过 |
| 长度越短能量越高 | ✅ 通过 |
| 长字符串不归零 (≥1e-6) | ✅ 通过 |
| `normalized_energy()` 之和 ≈ 1.0 | ✅ 通过 |
| `choose()` 返回 Seed 对象 | ✅ 通过 |
| 空 population 不抛异常 | ✅ 通过 |

### 2.2 CoverageSizePowerSchedule

**测试用例**：构造 5 个不同覆盖行数的 seed，验证能量分配。

```python
seeds = [
    Seed(data='a', _coverage={('f1', 1)}),                          # 1行
    Seed(data='b', _coverage={('f1', 1), ('f1', 2), ('f1', 3)}),    # 3行
    Seed(data='c', _coverage={('f1', 1), ('f1', 2)}),                # 2行
    Seed(data='d', _coverage=set()),                                  # 0行
    Seed(data='e', _coverage={('f1', i) for i in range(10)}),        # 10行
]
```

**输出**：

```
cov= 0  energy=0.0000
cov= 1  energy=0.1000
cov= 2  energy=0.2000
cov= 3  energy=0.3000
cov=10  energy=1.0000
```

**验证项**：

| 验证项 | 结果 |
|---|---|
| 覆盖行越多能量越高 | ✅ 通过 |
| 零覆盖种子 = 最小能量 (1e-6) | ✅ 通过 |
| `normalized_energy()` 之和 ≈ 1.0 | ✅ 通过 |
| `choose()` 返回 Seed 对象 | ✅ 通过 |
| 空 population 不抛异常 | ✅ 通过 |

---

## 3. 集成测试

### 3.1 所有策略 10 秒短跑

**测试命令**：

```bash
# PathPowerSchedule
python main.py --sample 1 --run-time 10 --schedule path
python main.py --sample 2 --run-time 10 --schedule path
python main.py --sample 3 --run-time 10 --schedule path
python main.py --sample 4 --run-time 10 --schedule path

# SizePowerSchedule
python main.py --sample 1 --run-time 10 --schedule size
python main.py --sample 3 --run-time 10 --schedule size

# CoverageSizePowerSchedule
python main.py --sample 1 --run-time 10 --schedule coverage
python main.py --sample 3 --run-time 10 --schedule coverage
```

### 3.2 测试结果汇总

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

---

## 4. 调度策略对比分析

### 4.1 汇总数据（Sample 1 & 3，三种策略对比）

#### Sample 1（数值计算类）

| 指标 | path | size | coverage |
|------|------|------|----------|
| Total Execs | 12,843 | 10,209 | 13,332 |
| Total Paths | 5 | 5 | 5 |
| Uniq Crashes | 6 | 6 | 6 |
| Covered Lines | 10 | 10 | 10 |

三种策略在 Sample 1 上最终覆盖率和崩溃数持平。coverage 策略执行量略高。

#### Sample 3（分支嵌套类）

| 指标 | path | size | coverage |
|------|------|------|----------|
| Total Execs | 123,164 | **137,918** | 128,754 |
| Total Paths | 4 | **5** | 4 |
| Uniq Crashes | 4 | **5** | 4 |
| Covered Lines | 6 | **8** | 6 |

**SizePowerSchedule 在 Sample 3 表现最优**：比 path 多发现 1 条路径、1 个崩溃、2 行覆盖，执行量高 12%。

原因是 Sample 3 的分支逻辑（`s[0] == 'F'`、`s[1] == 'D'`）对输入长度高度敏感，短输入在变异后更可能精准命中条件字符。

#### Sample 4（HTML 解析器）

| 指标 | path |
|------|------|
| Total Execs | 8,999 |
| Total Paths | 746 |
| Uniq Crashes | 0 |
| Covered Lines | 593 |

HTML 解析器代码量大（593 行覆盖），路径数远超其他 sample。execs 较低是因为单次执行开销大。无崩溃符合预期（`sample4` 不会抛出未捕获异常）。

### 4.2 策略适用场景总结

| 策略 | 反馈类型 | 计算开销 | 冷启动 | 适用场景 |
|------|----------|----------|--------|----------|
| PathPowerSchedule | 灰盒 | 中 (MD5+dict) | 差 | 路径分支多、需要长期运行的场景 |
| SizePowerSchedule | 黑盒 | 低 (len()) | 好 | 长度敏感目标、快速冒烟测试 |
| CoverageSizePowerSchedule | 灰盒 | 低 (len(coverage)) | 好 | 代码量大、分支深的目标 |

---

## 5. CLI 参数测试

### 5.1 --help 输出

```
usage: main.py [-h] [--sample {1,2,3,4}] [--run-time RUN_TIME]
               [--schedule {path,size,coverage}] [--output-dir OUTPUT_DIR] [--quiet]

options:
  --sample {1,2,3,4}     Target sample program to fuzz
  --run-time RUN_TIME    Fuzzing duration in seconds
  --schedule {path,size,coverage}
                         Scheduling strategy
  --output-dir OUTPUT_DIR
                         Directory used to persist the run result
  --quiet                Disable the status table output
```

### 5.2 默认行为

```bash
python main.py --sample 1 --run-time 10
```

默认使用 `--schedule path`，不传 `--schedule` 参数也可正常运行。

### 5.3 非法参数拒绝

```
python main.py --schedule invalid
# error: argument --schedule: invalid choice: 'invalid' (choose from 'path', 'size', 'coverage')
```

---

## 6. 发现的问题

| # | 问题 | 影响 | 状态 |
|---|------|------|------|
| 1 | `PathGreyBoxFuzzer.__init__` 接收 `PathPowerSchedule` 类型提示，但实际传入 `PowerSchedule` 子类 | 不影响运行（Python 鸭子类型），但 IDE 可能报警 | 已知，非 D 职责 |
| 2 | 建议后续增加 `--schedule rare-line` 选项 | 组员 C 已有 Rare-Line 基础，可扩展 | 后续方向 |

---

## 7. 结论

1. **SizePowerSchedule** 和 **CoverageSizePowerSchedule** 两种新增调度策略均通过单元测试和集成测试。
2. `--schedule` CLI 参数支持 `path`/`size`/`coverage` 三种策略切换，默认 `path` 保持向后兼容。
3. **关键发现**：SizePowerSchedule 在 Sample 3（分支嵌套类目标）上表现优于 PathPowerSchedule，证明了不同调度策略的互补性。
4. 所有 4 个 sample 均能完成 10 秒短跑，框架稳定性良好。
