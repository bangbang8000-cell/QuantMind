#!/usr/bin/env python3
"""
OpenBB API Service 测试脚本

测试所有接口是否正常工作
"""
import requests
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8001"


def print_result(test_name: str, result: dict):
    """打印测试结果"""
    print(f"\n{'=' * 60}")
    print(f"测试: {test_name}")
    print(f"{'=' * 60}")
    print(json.dumps(result, indent=2, ensure_ascii=False))


def test_service_info():
    """测试服务信息"""
    response = requests.get(f"{BASE_URL}/")
    return response.json()


def test_health():
    """测试健康检查"""
    response = requests.get(f"{BASE_URL}/health")
    return response.json()


def test_equity_historical():
    """测试美股历史数据"""
    # 苹果公司 - 最近30天
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    response = requests.get(
        f"{BASE_URL}/equity/historical/AAPL",
        params={
            "start_date": start_date,
            "end_date": end_date,
        }
    )
    return response.json()


def test_equity_quote():
    """测试美股实时报价"""
    response = requests.get(f"{BASE_URL}/equity/quote/TSLA")
    return response.json()


def test_equity_profile():
    """测试公司信息"""
    response = requests.get(f"{BASE_URL}/equity/profile/MSFT")
    return response.json()


def test_equity_search():
    """测试股票搜索"""
    response = requests.get(
        f"{BASE_URL}/equity/search",
        params={"query": "apple", "limit": 3}
    )
    return response.json()


def test_macro_gdp():
    """测试 GDP 数据"""
    response = requests.get(
        f"{BASE_URL}/macro/gdp",
        params={"country": "united_states"}
    )
    return response.json()


def test_macro_cpi():
    """测试 CPI 数据"""
    response = requests.get(
        f"{BASE_URL}/macro/cpi",
        params={"country": "united_states"}
    )
    return response.json()


def test_crypto_historical():
    """测试加密货币历史数据"""
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    response = requests.get(
        f"{BASE_URL}/crypto/historical/BTC",
        params={
            "start_date": start_date,
            "end_date": end_date,
        }
    )
    return response.json()


def test_crypto_quote():
    """测试加密货币报价"""
    response = requests.get(f"{BASE_URL}/crypto/quote/ETH")
    return response.json()


def run_all_tests():
    """运行所有测试"""
    tests = [
        ("服务信息", test_service_info),
        ("健康检查", test_health),
        ("美股历史数据 (AAPL)", test_equity_historical),
        ("美股实时报价 (TSLA)", test_equity_quote),
        ("公司信息 (MSFT)", test_equity_profile),
        ("股票搜索 (apple)", test_equity_search),
        ("美国 GDP", test_macro_gdp),
        ("美国 CPI", test_macro_cpi),
        ("比特币历史数据", test_crypto_historical),
        ("以太坊报价", test_crypto_quote),
    ]

    print(f"\n{'#' * 60}")
    print("OpenBB API Service 测试")
    print(f"{'#' * 60}")
    print(f"服务地址: {BASE_URL}")
    print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    success_count = 0
    total_count = len(tests)

    for test_name, test_func in tests:
        try:
            result = test_func()
            print_result(test_name, result)

            if result.get("status") == "success" or "service" in result:
                success_count += 1
                print("✅ 测试通过")
            else:
                print(f"❌ 测试失败: {result.get('message', '未知错误')}")

        except Exception as e:
            print_result(test_name, {"error": str(e)})
            print(f"❌ 测试异常: {e}")

    # 汇总
    print(f"\n{'#' * 60}")
    print(f"测试完成: {success_count}/{total_count} 通过")
    print(f"成功率: {success_count/total_count*100:.1f}%")
    print(f"{'#' * 60}\n")


if __name__ == "__main__":
    print("等待服务启动...")
    print("请确保已运行: ./start.sh")
    print("按 Enter 键开始测试...")
    input()

    run_all_tests()
