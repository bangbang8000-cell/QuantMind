"""
AI 助手扩展
集成国产大模型 (MiniMax, GLM, Qwen, DeepSeek) 提供智能投研功能
"""

import os
import json
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class LLMConfig:
    """大模型配置"""
    provider: str
    model: str
    api_key: str
    base_url: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048


class BaseLLM(ABC):
    """大模型基类"""
    
    @abstractmethod
    def chat(self, message: str, **kwargs) -> str:
        """发送对话请求"""
        pass
    
    @abstractmethod
    def chat_with_tools(self, message: str, tools: List[dict], **kwargs) -> dict:
        """发送带工具调用的对话请求"""
        pass


class MiniMaxLLM(BaseLLM):
    """MiniMax 大模型"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url or "https://api.minimax.chat"
                )
            except ImportError:
                raise ImportError("openai package is required for MiniMax LLM")
        return self._client
    
    def chat(self, message: str, **kwargs) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": message}],
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        return response.choices[0].message.content
    
    def chat_with_tools(self, message: str, tools: List[dict], **kwargs) -> dict:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": message}],
            tools=tools,
            tool_choice="auto",
            temperature=kwargs.get("temperature", self.config.temperature),
        )
        
        msg = response.choices[0].message
        return {
            "content": msg.content,
            "tool_calls": msg.tool_calls if hasattr(msg, "tool_calls") else None
        }


class GLMLLM(BaseLLM):
    """智谱 GLM 大模型"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from zhipuai import ZhipuAI
                self._client = ZhipuAI(api_key=self.config.api_key)
            except ImportError:
                raise ImportError("zhipuai package is required for GLM")
        return self._client
    
    def chat(self, message: str, **kwargs) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": message}],
            temperature=kwargs.get("temperature", self.config.temperature),
        )
        return response.choices[0].message.content
    
    def chat_with_tools(self, message: str, tools: List[dict], **kwargs) -> dict:
        # GLM 的工具调用实现
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": message}],
            tools=tools,
        )
        
        msg = response.choices[0].message
        return {
            "content": msg.content,
            "tool_calls": msg.tool_calls if hasattr(msg, "tool_calls") else None
        }


class QwenLLM(BaseLLM):
    """阿里 Qwen 大模型"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                import dashscope
                dashscope.api_key = self.config.api_key
                self._client = dashscope
            except ImportError:
                raise ImportError("dashscope package is required for Qwen")
        return self._client
    
    def chat(self, message: str, **kwargs) -> str:
        client = self._get_client()
        response = client.Generation.call(
            model=self.config.model,
            prompt=message,
            temperature=kwargs.get("temperature", self.config.temperature),
        )
        if response.status_code == 200:
            return response.output.text
        else:
            raise RuntimeError(f"Qwen API error: {response.message}")
    
    def chat_with_tools(self, message: str, tools: List[dict], **kwargs) -> dict:
        # Qwen 的工具调用实现
        raise NotImplementedError("Qwen tool calling not yet implemented")


class DeepSeekLLM(BaseLLM):
    """DeepSeek 大模型"""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self._client = None
    
    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url or "https://api.deepseek.com"
                )
            except ImportError:
                raise ImportError("openai package is required for DeepSeek")
        return self._client
    
    def chat(self, message: str, **kwargs) -> str:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": message}],
            temperature=kwargs.get("temperature", self.config.temperature),
            max_tokens=kwargs.get("max_tokens", self.config.max_tokens),
        )
        return response.choices[0].message.content
    
    def chat_with_tools(self, message: str, tools: List[dict], **kwargs) -> dict:
        client = self._get_client()
        response = client.chat.completions.create(
            model=self.config.model,
            messages=[{"role": "user", "content": message}],
            tools=tools,
        )
        
        msg = response.choices[0].message
        return {
            "content": msg.content,
            "tool_calls": msg.tool_calls if hasattr(msg, "tool_calls") else None
        }


class AIExtension:
    """
    AI 助手扩展
    
    支持的模型:
    - MiniMax (minimaxi)
    - GLM (zhipuai)
    - Qwen (qwen)
    - DeepSeek (deepseek)
    
    核心功能:
    - 财报解读
    - 智能选股
    - K线分析
    - 量化策略编写
    - 风险提示
    """
    
    # 默认模型配置
    DEFAULT_MODELS = {
        "minimaxi": {
            "model": "MiniMax-Text-01",
            "base_url": "https://api.minimax.chat/v1",
        },
        "zhipuai": {
            "model": "glm-4-flash",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
        },
        "qwen": {
            "model": "qwen-plus",
            "base_url": "https://dashscope.aliyuncs.com/api/v1",
        },
        "deepseek": {
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
        },
    }
    
    def __init__(self, openbb_instance):
        self.openbb = openbb_instance
        self._llm: Optional[BaseLLM] = None
        self._current_provider: str = "minimaxi"
        self._tools = self._define_tools()
    
    def set_provider(
        self,
        provider: str,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs
    ):
        """
        设置大模型 Provider
        
        Args:
            provider: 提供商 (minimaxi/zhipuai/qwen/deepseek)
            api_key: API Key (如果环境变量未设置)
            model: 模型名称 (可选)
            **kwargs: 其他参数
        """
        api_key = api_key or self._get_api_key(provider)
        
        if not api_key:
            raise ValueError(
                f"API key not found for {provider}. "
                f"Please set {provider.upper()}_API_KEY environment variable "
                f"or pass api_key parameter."
            )
        
        config = LLMConfig(
            provider=provider,
            model=model or self.DEFAULT_MODELS[provider]["model"],
            api_key=api_key,
            base_url=kwargs.get("base_url") or self.DEFAULT_MODELS[provider].get("base_url"),
        )
        
        if provider == "minimaxi":
            self._llm = MiniMaxLLM(config)
        elif provider == "zhipuai":
            self._llm = GLMLLM(config)
        elif provider == "qwen":
            self._llm = QwenLLM(config)
        elif provider == "deepseek":
            self._llm = DeepSeekLLM(config)
        else:
            raise ValueError(f"Unknown provider: {provider}")
        
        self._current_provider = provider
    
    def chat(self, message: str, **kwargs) -> str:
        """
        发送对话请求
        
        Args:
            message: 用户消息
            **kwargs: 其他参数 (temperature, max_tokens 等)
        
        Returns:
            str: AI 回复
        """
        if self._llm is None:
            self.set_provider(self._current_provider)
        
        return self._llm.chat(message, **kwargs)
    
    def analyze_stock(
        self,
        symbol: str,
        analysis_type: str = "comprehensive",
        **kwargs
    ) -> dict:
        """
        智能股票分析
        
        Args:
            symbol: 股票代码
            analysis_type: 分析类型
                - comprehensive: 全面分析
                - technical: 技术分析
                - fundamental: 基本面分析
                - risk: 风险评估
        
        Returns:
            dict: 分析结果
        """
        # 获取股票数据
        quote = self.openbb.stocks.quote(symbol)
        historical = self.openbb.stocks.historical(symbol, period="monthly")
        
        # 构建提示词
        if analysis_type == "technical":
            prompt = self._build_technical_prompt(symbol, historical)
        elif analysis_type == "fundamental":
            prompt = self._build_fundamental_prompt(symbol, quote)
        elif analysis_type == "risk":
            prompt = self._build_risk_prompt(symbol, historical, quote)
        else:
            prompt = self._build_comprehensive_prompt(symbol, historical, quote)
        
        # 发送分析请求
        response = self.chat(prompt, **kwargs)
        
        return {
            "symbol": symbol,
            "analysis_type": analysis_type,
            "result": response,
            "data": {
                "quote": quote,
                "historical": historical.tail(30).to_dict()
            }
        }
    
    def explain_financial_report(
        self,
        symbol: str,
        statement_type: str = "income_statement",
        **kwargs
    ) -> str:
        """
        财报解读
        
        Args:
            symbol: 股票代码
            statement_type: 报表类型
        
        Returns:
            str: 解读结果
        """
        # 获取财报数据
        if statement_type == "balance_sheet":
            df = self.openbb.fundamental.balance_sheet(symbol)
        elif statement_type == "income_statement":
            df = self.openbb.fundamental.income_statement(symbol)
        elif statement_type == "cash_flow":
            df = self.openbb.fundamental.cash_flow(symbol)
        else:
            df = self.openbb.fundamental.income_statement(symbol)
        
        # 构建提示词
        prompt = f"""
请分析以下{self._get_statement_name(statement_type)}数据：

股票代码: {symbol}

数据摘要:
{df.head(5).to_string()}

请从以下角度进行解读：
1. 关键指标解读
2. 同比/环比变化分析
3. 潜在风险提示
4. 投资建议
"""
        
        return self.chat(prompt, **kwargs)
    
    def screen_stocks(
        self,
        criteria: str,
        **kwargs
    ) -> dict:
        """
        智能选股
        
        Args:
            criteria: 选股条件描述 (自然语言)
        
        Returns:
            dict: 选股结果和理由
        
        Example:
            obb.ai.screen_stocks("市盈率低于20的科技股")
        """
        # 获取可选的交易标的信息
        market_info = self._get_market_info()
        
        prompt = f"""
请根据以下选股条件，从中国A股市场中筛选符合条件的股票：

选股条件: {criteria}

市场概况:
{market_info}

请提供：
1. 符合条件的目标股票列表（含代码和名称）
2. 筛选逻辑说明
3. 每只股票的简要推荐理由
4. 风险提示

注意：请确保筛选逻辑合理，数据引用准确。
"""
        
        response = self.chat(prompt, **kwargs)
        
        return {
            "criteria": criteria,
            "result": response,
        }
    
    def generate_strategy(
        self,
        description: str,
        language: str = "python",
        **kwargs
    ) -> dict:
        """
        生成量化策略代码
        
        Args:
            description: 策略描述
            language: 编程语言 (python/pandas/numpy)
        
        Returns:
            dict: 策略代码和说明
        """
        prompt = f"""
请生成一个量化交易策略的{language}代码。

策略描述: {description}

要求：
1. 代码完整可运行
2. 包含详细的注释说明
3. 使用清晰的变量命名
4. 包含必要的错误处理
5. 策略逻辑明确

代码框架参考（可选用）：
- pandas 处理数据
- numpy 进行数值计算
- backtrader/backtesting.py 进行回测（如需要）

请直接输出代码和策略说明。
"""
        
        response = self.chat(prompt, **kwargs)
        
        return {
            "description": description,
            "language": language,
            "code": response,
        }
    
    def news_sentiment(
        self,
        keyword: str,
        days: int = 7,
        **kwargs
    ) -> dict:
        """
        新闻舆情分析
        
        Args:
            keyword: 关键词 (股票代码或名称)
            days: 分析天数
        
        Returns:
            dict: 舆情分析结果
        """
        prompt = f"""
请分析最近{days}天关于"{keyword}"的新闻舆情。

请从以下角度分析：
1. 整体情绪倾向（正面/负面/中性）
2. 主要话题和事件
3. 对股价的可能影响
4. 风险提示

请给出综合性的舆情报告。
"""
        
        response = self.chat(prompt, **kwargs)
        
        return {
            "keyword": keyword,
            "days": days,
            "result": response,
        }
    
    def _define_tools(self) -> List[dict]:
        """定义可用的工具函数"""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_stock_quote",
                    "description": "获取股票实时行情",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "股票代码"}
                        },
                        "required": ["symbol"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_historical_data",
                    "description": "获取股票历史数据",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "股票代码"},
                            "period": {"type": "string", "description": "周期 (daily/weekly/monthly)"}
                        },
                        "required": ["symbol"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_financial_data",
                    "description": "获取财务报表数据",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "股票代码"},
                            "statement_type": {
                                "type": "string",
                                "enum": ["balance_sheet", "income_statement", "cash_flow"],
                                "description": "报表类型"
                            }
                        },
                        "required": ["symbol"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_technical_indicators",
                    "description": "获取技术指标",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "股票代码"},
                            "indicator": {
                                "type": "string",
                                "description": "指标类型 (ma/macd/kdj/rsi/boll)"
                            }
                        },
                        "required": ["symbol"]
                    }
                }
            }
        ]
    
    def _build_technical_prompt(self, symbol: str, historical) -> str:
        """构建技术分析提示词"""
        return f"""
请分析以下股票的技术面：

股票代码: {symbol}

最近30个交易日数据：
{historical.tail(30).to_string()}

请分析：
1. 趋势判断（上升/下降/震荡）
2. 关键支撑位和阻力位
3. 技术指标信号（MA、MACD、KDJ等）
4. 短期操作建议
"""
    
    def _build_fundamental_prompt(self, symbol: str, quote) -> str:
        """构建基本面分析提示词"""
        return f"""
请分析以下股票的基本面：

股票代码: {symbol}

当前行情：
{json.dumps(quote, ensure_ascii=False, indent=2)}

请分析：
1. 估值水平（PE、PB等）
2. 盈利能力
3. 财务健康状况
4. 投资价值评估
"""
    
    def _build_risk_prompt(self, symbol: str, historical, quote) -> str:
        """构建风险评估提示词"""
        return f"""
请评估以下股票的风险：

股票代码: {symbol}

历史数据：
{historical.tail(20).to_string()}

当前行情：
{json.dumps(quote, ensure_ascii=False, indent=2)}

请评估：
1. 市场风险
2. 流动性风险
3. 波动性风险
4. 潜在风险因素
5. 风险控制建议
"""
    
    def _build_comprehensive_prompt(self, symbol: str, historical, quote) -> str:
        """构建综合分析提示词"""
        return f"""
请对以下股票进行全面分析：

股票代码: {symbol}

历史数据（最近30日）：
{historical.tail(30).to_string()}

当前行情：
{json.dumps(quote, ensure_ascii=False, indent=2)}

请提供：
1. 技术面分析
2. 基本面分析
3. 消息面影响
4. 综合评级（买入/持有/卖出）
5. 目标价位
6. 风险提示
"""
    
    def _get_market_info(self) -> str:
        """获取市场概况"""
        try:
            overview = self.openbb.stocks.market_overview()
            return json.dumps(overview, ensure_ascii=False, indent=2)
        except Exception:
            return "市场数据暂时无法获取"
    
    def _get_statement_name(self, statement_type: str) -> str:
        """获取报表类型中文名"""
        names = {
            "balance_sheet": "资产负债表",
            "income_statement": "利润表",
            "cash_flow": "现金流量表"
        }
        return names.get(statement_type, "财务报表")
    
    def _get_api_key(self, provider: str) -> Optional[str]:
        """从环境变量获取 API Key"""
        env_vars = {
            "minimaxi": ["MINIMAX_API_KEY", "MINIMAX_API_KEY"],
            "zhipuai": ["ZHIPUAI_API_KEY", "ZHIPU_API_KEY"],
            "qwen": ["DASHSCOPE_API_KEY", "QWEN_API_KEY"],
            "deepseek": ["DEEPSEEK_API_KEY"],
        }
        
        for var in env_vars.get(provider, []):
            key = os.environ.get(var)
            if key:
                return key
        
        return None
