"""真人节奏模拟器 —— 降低自动化风控感知

原理：
1. 随机延迟（2-8s）+ 高斯抖动，模拟人思考 + 输入节奏
2. 动作间隔 5-15s，避免被识别为脚本
3. 偶尔插入长延迟（15-30s），模拟"看眼手机/喝口水"
"""
import random
import time
from contextlib import contextmanager


def human_delay(min_s: float = 2.0, max_s: float = 8.0, label: str = ""):
    """基础延迟：min~max 秒 + 高斯抖动"""
    base = random.uniform(min_s, max_s)
    jitter = random.gauss(0, 0.4)
    actual = max(0.3, base + jitter)
    if label:
        print(f"  ⏱ {label}: 等待 {actual:.1f}s")
    time.sleep(actual)


def micro_pause():
    """微停顿（0.3-1.2s），模拟鼠标悬停/眼睛扫过"""
    time.sleep(random.uniform(0.3, 1.2))


def long_pause(probability: float = 0.08):
    """偶尔长停顿（15-30s），模拟人走开/看手机。
    probability: 每次调用触发的概率"""
    if random.random() < probability:
        actual = random.uniform(15, 30)
        print(f"  ☕ 长停顿 {actual:.0f}s（模拟人走开）")
        time.sleep(actual)


@contextmanager
def action(name: str = ""):
    """动作上下文管理器：自动加延迟 + 长停顿概率触发"""
    if name:
        print(f"  ▶ {name}")
    micro_pause()
    try:
        yield
    finally:
        human_delay(2.0, 6.0, f"{name} 后")
        long_pause(probability=0.05)


def typing_delay(text_length: int) -> float:
    """根据文本长度返回合理的输入耗时"""
    # 人输入速度：80-150 字/分钟（中文）/ 200 字/分钟（英文）
    cjk_count = sum(1 for c in text_length if '\u4e00' <= c <= '\u9fff') if isinstance(text_length, str) else text_length
    base = cjk_count / 100 * 60  # 秒
    jitter = random.gauss(0, 1.5)
    return max(2.0, base + jitter)