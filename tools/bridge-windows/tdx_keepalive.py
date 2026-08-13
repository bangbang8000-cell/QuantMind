"""
通达信 TQ 常驻服务 - 保持 17709 HTTP 服务持续监听（自愈版）

与旧版的区别：
  1. 任何异常都不再退出主循环（旧版异常即整体退出 → 17709 掉线）
  2. 每 30 秒轻量探活（get_match_stkinfo），不通则重连（close + initialize）
  3. 重连上限 3 次，连续失败则放弃本进程——靠 AutoRun + 通达信重启恢复

使用方法（同旧版）:
  1. 通达信 TQ 策略管理器 → 新建策略 → 粘贴本代码
  2. 点"运行"，保持策略运行状态
"""

import time
import traceback

from tqcenter import tq

PROBE_INTERVAL_SEC = 30       # 探活间隔
MAX_RECONNECTS = 3            # 连续重连上限（达到后放弃，等通达信重启）


def _probe() -> bool:
    """轻量探活：能取到任意匹配结果即视为 17709 会话正常。"""
    try:
        result = tq.get_match_stkinfo("茅台")
        value = result.get("Value") if isinstance(result, dict) else None
        if value:
            return True
        return result.get("ErrorId", "0") in ("0", "12") if isinstance(result, dict) else False
    except Exception as exc:
        print(f"[keepalive] 探活异常: {exc}")
        return False


def _reconnect() -> bool:
    """关闭旧会话并重新初始化。"""
    for attempt in range(MAX_RECONNECTS):
        try:
            tq.close()
        except Exception:
            pass
        try:
            tq.initialize(__file__)
            if _probe():
                print(f"[keepalive] 重连成功 (第 {attempt + 1} 次尝试)")
                return True
        except Exception as exc:
            print(f"[keepalive] 重连失败 ({attempt + 1}/{MAX_RECONNECTS}): {exc}")
        time.sleep(5)
    return False


def main():
    tq.initialize(__file__)
    print("TQ 常驻服务已启动 (自愈版), 17709 监听中...")
    print(f"探活间隔 {PROBE_INTERVAL_SEC}s, 重连上限 {MAX_RECONNECTS} 次")

    tick = 0
    while True:
        try:
            time.sleep(PROBE_INTERVAL_SEC)
            tick += 1
            if _probe():
                if tick % 10 == 0:  # 每 5 分钟打印一次心跳
                    print(f"TQ 常驻心跳 #{tick}")
                continue

            print(f"[keepalive] 会话探活失败, 尝试重连 (第 {tick} 轮)")
            if not _reconnect():
                print("[keepalive] 连续重连失败, 本进程放弃。"
                      "请重启通达信 (策略已设 AutoRun 会自动拉起)")
                break
        except KeyboardInterrupt:
            print("[keepalive] 收到停止信号")
            break
        except Exception:
            print("[keepalive] 主循环异常 (不退出, 继续守护):")
            traceback.print_exc()
            time.sleep(5)

    try:
        tq.close()
    except Exception:
        pass
    print("TQ 常驻服务已停止")


if __name__ == "__main__":
    main()
