"""
组员 A：mutator 自测脚本

验收点：
1. Mutator().mutate(inp) 连续运行 1000 次不抛异常，且输出始终为 str、长度受控。
2. mutation 结果存在多样性，不总是返回原输入。
3. 必需变异策略齐全（含随机删除、随机替换等）。

运行方式（任意工作目录均可）：
    python tests/test_mutator.py
"""

import os
import sys

# 将 simple_fuzzer/ 加入 sys.path，使 `from utils.mutator import Mutator` 在任意目录可用
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.mutator import Mutator, MAX_INPUT_LENGTH


# 覆盖空串、单字符、普通字符串、长字符串、非 ASCII 输入
TEST_INPUTS = ["", "a", "123", "FDULAB", "<html></html>", "中文输入", "x" * 5000]


def test_no_exception_and_str_and_bounded():
    """连续 1000 次变异不抛异常，输出为 str，且长度不超过上限"""
    m = Mutator()
    for inp in TEST_INPUTS:
        for _ in range(1000):
            out = m.mutate(inp)
            assert isinstance(out, str), f"输出不是 str: {type(out)!r} (input={inp!r})"
            assert len(out) <= MAX_INPUT_LENGTH, f"输出超长 {len(out)} > {MAX_INPUT_LENGTH}"
    print("[PASS] 1000 次变异无异常，输出均为 str 且长度受控")


def test_diversity():
    """对普通字符串多次变异，结果应具备多样性，不总是返回原输入"""
    m = Mutator()
    inp = "FDULAB-fuzzing-2026"
    outputs = {m.mutate(inp) for _ in range(200)}
    assert len(outputs) > 1, "变异结果缺乏多样性"
    assert any(o != inp for o in outputs), "变异总是返回原输入"
    print(f"[PASS] 多样性测试：200 次变异得到 {len(outputs)} 种不同结果")


def test_strategy_coverage():
    """必需策略齐全（含新增的 delete / replace）"""
    m = Mutator()
    names = {fn.__name__ for fn in m.mutators}
    required = {
        "insert_random_character",
        "delete_random_bytes",
        "replace_random_bytes",
        "flip_random_bits",
        "arithmetic_random_bytes",
        "interesting_random_bytes",
        "havoc_random_insert",
        "havoc_random_replace",
        "random_block_swap",
    }
    missing = required - names
    assert not missing, f"缺少策略: {missing}"
    assert len(m.mutators) >= 9, f"策略数量不足: {len(m.mutators)}"
    print(f"[PASS] 策略可达性：共 {len(m.mutators)} 个策略，必需策略齐全")


def test_non_str_input_coerced():
    """非 str 输入应被强制转为 str，不抛异常"""
    m = Mutator()
    for inp in [123, None, b"bytes"]:
        out = m.mutate(inp)
        assert isinstance(out, str), f"非 str 输入未返回 str: {type(out)!r}"
    print("[PASS] 非 str 输入被安全处理")


def main():
    test_no_exception_and_str_and_bounded()
    test_diversity()
    test_strategy_coverage()
    test_non_str_input_coerced()
    print("mutator smoke test passed")


if __name__ == "__main__":
    main()
