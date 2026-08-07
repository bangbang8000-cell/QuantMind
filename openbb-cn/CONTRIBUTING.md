# 贡献指南

感谢您对 OPENBB-CN 项目的关注！我们欢迎任何形式的贡献。

## 如何贡献

### 1. 报告问题

如果您发现任何问题或有功能建议，请：

- 搜索现有 Issue 确认是否已有人报告
- 创建新的 Issue，包含：
  - 清晰的问题描述
  - 复现步骤
  - 环境信息（Python 版本、操作系统等）
  - 相关日志或截图

### 2. 提交代码

#### 开发流程

1. **Fork 仓库**
   ```bash
   git clone https://github.com/YOUR_USERNAME/OPENBB-CN.git
   cd OPENBB-CN
   ```

2. **创建分支**
   ```bash
   git checkout -b feature/your-feature-name
   # 或
   git checkout -b fix/your-bug-fix
   ```

3. **设置开发环境**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # 或
   venv\Scripts\activate  # Windows
   
   pip install -e ".[dev,providers,ai]"
   ```

4. **编写代码**
   - 遵循代码风格（black, isort）
   - 添加测试用例
   - 更新文档

5. **提交代码**
   ```bash
   git add .
   git commit -m "feat: add new feature"
   git push origin feature/your-feature-name
   ```

6. **创建 Pull Request**

#### 代码规范

- 使用 **black** 格式化代码（line length: 88）
- 使用 **isort** 排序 import
- 遵循 **PEP 8** 规范
- 所有新增函数/类必须有 **docstring**
- 新增代码需要添加 **类型注解**

```python
def example_function(arg1: str, arg2: int) -> dict:
    """
    函数描述
    
    Args:
        arg1: 参数1描述
        arg2: 参数2描述
    
    Returns:
        返回值描述
    """
    pass
```

### 3. 新增数据源 Provider

参考 `openbb_core/providers/` 目录下的现有 Provider 实现：

```python
from openbb_core.providers.base import BaseProvider

class MyProvider(BaseProvider):
    name = "myprovider"
    description = "我的数据源"
    
    def get_historical_data(self, symbol: str, **kwargs):
        # 实现获取历史数据的逻辑
        pass
    
    def get_realtime_quote(self, symbol: str, **kwargs):
        # 实现获取实时行情的逻辑
        pass
```

### 4. 新增功能扩展

参考 `openbb_core/extensions/` 目录下的现有扩展实现。

### 5. 文档贡献

- 更新 `docs/` 目录下的文档
- 为新功能添加使用示例
- 翻译文档（欢迎多语言贡献）

## 测试

运行测试：
```bash
# 运行所有测试
pytest

# 运行特定测试
pytest tests/test_stocks.py

# 带覆盖率
pytest --cov=openbb_core tests/
```

## 项目结构

```
OPENBB-CN/
├── openbb_core/              # 核心模块
│   ├── core.py              # 主类
│   ├── providers/           # 数据源 Providers
│   │   ├── base.py
│   │   ├── akshare_provider.py
│   │   └── easyquotation_provider.py
│   └── extensions/          # 功能扩展
│       ├── stocks.py
│       ├── technical.py
│       ├── fundamental.py
│       └── ai.py
├── tests/                   # 测试文件
├── docs/                    # 文档
└── docker/                  # Docker 配置
```

## 许可证

提交代码即表示您同意您的代码将遵循 GPL-3.0 许可证开源。

## 问题？

- 创建 GitHub Issue
- 加入社区讨论

感谢您的贡献！ 🎉
