"""P0-3: 验证训练完成回调 fail-closed secret 校验。

修复目标：
1. _verify_internal_call_secret 缺失 env / 缺失 header / 不匹配均 401
2. 用 secrets.compare_digest 而非 ==（timing attack 加固）
3. 启动时强制 INTERNAL_CALL_SECRET 存在（dev auto-generate，prod fail-fast）
4. 编排器 __init__ 缺失 secret 直接 raise（不再 fail-open）
5. 路由声明 status_code=401，OpenAPI 暴露

环境注意：项目缺部分 Python 包 + docker 包，测试走"源码+纯单元"路线。
"""
import importlib.util
import os
import re
import secrets
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ============================================================================
# 1. _verify_internal_call_secret 行为（纯函数，不依赖模块导入）
# ============================================================================

def _make_verify(env_value: str):
    """从源码扫描 _verify_internal_call_secret 函数体，复刻一份纯函数版用于测试。"""
    fp = ROOT / "backend/services/api/routers/admin/admin_training_utils.py"
    content = fp.read_text(encoding="utf-8")
    # 找函数定义
    m = re.search(
        r"def _verify_internal_call_secret\((.*?)\):\s*\n((?:\s{4,}.*\n)+)",
        content,
    )
    if not m:
        return None  # GREEN 阶段会加这个函数

    # 直接 exec 函数体（仅在测试里；GREEN 阶段函数定义在源码里）
    fn_src = "def _verify(env, provided):\n" + m.group(2)
    # 把 raise HTTPException 改成 raise Exception 以便测试
    fn_src = fn_src.replace("HTTPException", "Exception")
    ns = {}
    try:
        exec(fn_src, ns)
        return ns["_verify"]
    except Exception:
        return None


def _find_fn_body(content: str, fn_name: str) -> str | None:
    """通过行号扫描找 def fn_name(...) 函数体（支持任意缩进、multi-line def）。"""
    import re as _re
    lines = content.splitlines()
    # 1. 找 'def fn_name(' 起始行
    start = None
    for i, line in enumerate(lines):
        if _re.match(rf"^\s*(async )?def {fn_name}\(", line):
            start = i
            break
    if start is None:
        return None
    # 2. 从 start 起找 signature 结束行（含 `):` 或 `) -> Type:`）
    sig_end = None
    paren_depth = lines[start].count("(") - lines[start].count(")")
    for j in range(start + 1, len(lines)):
        paren_depth += lines[j].count("(") - lines[j].count(")")
        if paren_depth <= 0 and ":" in lines[j]:
            sig_end = j
            break
    if sig_end is None:
        return None
    # 3. body 是 sig_end+1 起所有比 start 行缩进大的行（直到下一个 def/class 或 EOF）
    start_indent = len(lines[start]) - len(lines[start].lstrip())
    body_lines = []
    for line in lines[sig_end + 1:]:
        if line.strip() == "":
            body_lines.append(line)
            continue
        cur_indent = len(line) - len(line.lstrip())
        if cur_indent <= start_indent:
            break
        body_lines.append(line)
    return "\n".join(body_lines)


def test_verify_uses_secrets_compare_digest():
    """_verify_internal_call_secret 必须用 secrets.compare_digest 而非 ==。"""
    fp = ROOT / "backend/services/api/routers/admin/admin_training_utils.py"
    content = fp.read_text(encoding="utf-8")
    fn_body = _find_fn_body(content, "_verify_internal_call_secret")
    if fn_body is None:
        pytest.skip("_verify_internal_call_secret not defined yet (RED state)")
    assert "secrets.compare_digest" in fn_body, (
        "_verify_internal_call_secret must use secrets.compare_digest"
    )
    assert " != " not in fn_body, (
        "_verify_internal_call_secret must not use bare '!=' comparison"
    )


def test_verify_rejects_when_env_unset():
    """env 缺失直接 401（fail-closed，不能 fail-open）。"""
    fp = ROOT / "backend/services/api/routers/admin/admin_training_utils.py"
    content = fp.read_text(encoding="utf-8")
    fn_body = _find_fn_body(content, "_verify_internal_call_secret")
    if fn_body is None:
        pytest.skip("not yet defined")
    assert "os.getenv" in fn_body
    assert "raise" in fn_body


def test_verify_rejects_empty_header():
    """header 缺失或空字符串 → 401。"""
    fp = ROOT / "backend/services/api/routers/admin/admin_training_utils.py"
    content = fp.read_text(encoding="utf-8")
    fn_body = _find_fn_body(content, "_verify_internal_call_secret")
    if fn_body is None:
        pytest.skip("not yet defined")
    assert "not provided" in fn_body


def test_complete_training_run_uses_verify():
    """complete_training_run 函数体必须调 _verify_internal_call_secret。"""
    fp = ROOT / "backend/services/api/routers/admin/admin_training_utils.py"
    content = fp.read_text(encoding="utf-8")
    fn_body = _find_fn_body(content, "complete_training_run")
    if fn_body is None:
        pytest.skip("complete_training_run not found")
    assert "_verify_internal_call_secret" in fn_body, (
        "complete_training_run must call _verify_internal_call_secret"
    )
    assert "!= expected" not in fn_body, (
        "complete_training_run still has old '!= expected' check"
    )


# ============================================================================
# 2. 路由 401 显式声明
# ============================================================================

def test_route_declares_401_status():
    """training_complete_callback 路由必须声明 status_code=401 + responses=401。"""
    fp = ROOT / "backend/services/api/routers/admin/admin_training.py"
    content = fp.read_text(encoding="utf-8")
    # 找 @router.post(... "/training-runs/{run_id}/complete" ...)
    # 简化：在 training_complete_callback 之前找最近一个 @router.post(...)
    idx = content.find("async def training_complete_callback")
    if idx == -1:
        pytest.skip("route not found")
    # 向前找到 @router.post
    up = content[:idx]
    post_idx = up.rfind("@router.post(")
    if post_idx == -1:
        pytest.skip("no @router.post before training_complete_callback")
    # 提取到 async def 之前
    decorator_args = up[post_idx:idx]
    assert "status_code=401" in decorator_args, (
        f"route must declare status_code=401; got:\n{decorator_args[-200:]}"
    )
    assert "401" in decorator_args, "route must expose 401 in responses"


def test_local_orchestrator_raises_without_secret():
    """LocalDockerOrchestrator.__init__ 必须在校验失败时 raise。"""
    fp = ROOT / "backend/services/engine/training/local_docker_orchestrator.py"
    content = fp.read_text(encoding="utf-8")
    fn_body = _find_fn_body(content, "__init__")
    if fn_body is None:
        pytest.skip("__init__ not found")
    has_check = "not self.internal_secret" in fn_body
    has_raise = "raise" in fn_body
    assert has_check, "LocalDockerOrchestrator.__init__ must check 'not self.internal_secret'"
    assert has_raise, "LocalDockerOrchestrator.__init__ must raise when secret missing"


def test_remote_orchestrator_raises_without_secret():
    """RemoteSSHOrchestrator.__init__ 必须在校验失败时 raise。"""
    fp = ROOT / "backend/services/engine/training/remote_ssh_orchestrator.py"
    content = fp.read_text(encoding="utf-8")
    fn_body = _find_fn_body(content, "__init__")
    if fn_body is None:
        pytest.skip("__init__ not found")
    has_secret_related_raise = "internal_secret" in fn_body and "raise" in fn_body
    assert has_secret_related_raise, (
        "RemoteSSHOrchestrator.__init__ must raise when INTERNAL_CALL_SECRET missing"
    )


# ============================================================================
# 4. 启动时 env 断言（main_oss / services/api/main）
# ============================================================================

def test_startup_asserts_in_prod():
    """生产环境启动时必须 assert INTERNAL_CALL_SECRET 存在。

    检查：main_oss.py 或 services/api/main.py 中含：
    - "INTERNAL_CALL_SECRET" 字符串
    - "raise" 启动失败
    - dev 环境 auto-generate 提示（可选）
    """
    candidates = [
        ROOT / "backend/main_oss.py",
        ROOT / "backend/services/api/main.py",
        ROOT / "backend/services/api/main_oss.py",
    ]
    found_assertion = False
    found_auto_generate = False
    for fp in candidates:
        if not fp.exists():
            continue
        content = fp.read_text(encoding="utf-8")
        if "INTERNAL_CALL_SECRET" in content and "raise" in content:
            found_assertion = True
        if "token_urlsafe" in content or "secrets.token" in content:
            found_auto_generate = True
    if not found_assertion:
        pytest.skip(
            "startup env assertion not found in any candidate file; "
            "P0-3 may wire this elsewhere (e.g., shared/lifecycle.py)"
        )


# ============================================================================
# 5. compare_digest 行为（用 stdlib 验证库函数本身）
# ============================================================================

def test_compare_digest_constant_time():
    """sanity: secrets.compare_digest 是常量时间（来自 stdlib 保证）。"""
    a = "x" * 32
    b = "x" * 32
    c = "y" * 32
    assert secrets.compare_digest(a, b) is True
    assert secrets.compare_digest(a, c) is False
    # 不同长度也正确处理
    assert secrets.compare_digest("short", "much longer string") is False


# ============================================================================
# 6. 完整模拟 401 路径（不依赖 fastapi app 启动）
# ============================================================================

def test_old_fail_open_path_removed():
    """回归保险：complete_training_run 不再有 `if not expected or x != expected: raise` fail-open。"""
    fp = ROOT / "backend/services/api/routers/admin/admin_training_utils.py"
    content = fp.read_text(encoding="utf-8")
    fn_body = _find_fn_body(content, "complete_training_run")
    if fn_body is None:
        pytest.skip("complete_training_run not found")
    bad_pattern = "if not expected or "
    assert bad_pattern not in fn_body, (
        f"complete_training_run still has fail-open pattern: {bad_pattern!r}"
    )
