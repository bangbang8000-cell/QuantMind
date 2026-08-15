"""
通达信 TQ 常驻服务 - 保持 17709 HTTP 服务持续监听（自愈版）

与旧版的区别：
  1. 任何异常都不再退出主循环（旧版异常即整体退出 → 17709 掉线）
  2. 探活直接用 HTTP 探测 17709（与桥同一方式），不做进程内调用——
     进程内 get_match_stkinfo 在重建会话后可能短暂不可用, 会误判
  3. 17709 掉线才重连（close + initialize）, 上限 3 次
  4. 配合 py_strategy.cfg AutoRun0=1: 通达信重启自动拉起本策略

使用方法（同旧版）:
  1. 通达信 TQ 策略管理器 → 新建策略 → 粘贴本代码
  2. 点"运行"，保持策略运行状态
"""

import json
import time
import traceback
import urllib.request

from tqcenter import tq

PROBE_INTERVAL_SEC = 30       # 探活间隔
MAX_RECONNECTS = 3            # 连续重连上限（达到后放弃，等通达信重启）
TDX_RPC_URL = "http://127.0.0.1:17709/"


def _probe_http() -> bool:
    """HTTP 探测 17709 JSON-RPC（与桥同一方式, 短超时不重试）。"""
    body = json.dumps({"id": 1, "method": "get_match_stkinfo",
                       "params": {"key_word": "茅台"}}).encode("utf-8")
    try:
        req = urllib.request.Request(
            TDX_RPC_URL, data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        return "error" not in result
    except Exception:
        return False


def _reconnect() -> bool:
    """关闭旧会话并重新初始化（重新拉起 17709）。"""
    for attempt in range(MAX_RECONNECTS):
        try:
            tq.close()
        except Exception:
            pass
        try:
            tq.initialize(__file__)
        except Exception as exc:
            print(f"[keepalive] 初始化失败 ({attempt + 1}/{MAX_RECONNECTS}): {exc}")
            time.sleep(5)
            continue
        time.sleep(2)
        if _probe_http():
            print(f"[keepalive] 重连成功 (第 {attempt + 1} 次尝试)")
            return True
        print(f"[keepalive] 重连后 17709 仍不可达 ({attempt + 1}/{MAX_RECONNECTS})")
    return False


def main():
    tq.initialize(__file__)
    print("TQ 常驻服务已启动 (自愈版 v2), 17709 监听中...")
    print(f"探活间隔 {PROBE_INTERVAL_SEC}s, 重连上限 {MAX_RECONNECTS} 次")

    tick = 0
    while True:
        try:
            time.sleep(PROBE_INTERVAL_SEC)
            tick += 1
            if _probe_http():
                if tick % 10 == 0:  # 每 5 分钟打印一次心跳
                    print(f"TQ 常驻心跳 #{tick}")
                continue

            print(f"[keepalive] 17709 探活失败, 尝试重连 (第 {tick} 轮)")
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

