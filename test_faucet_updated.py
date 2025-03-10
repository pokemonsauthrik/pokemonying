import requests
import json
import time
import sys
from bs4 import BeautifulSoup

# 测试不同方法获取测试币

def test_api_endpoints():
    print("测试不同的API端点...")
    base_urls = [
        'https://testnet-faucet.autheo.com',
        'https://testnet-faucet.autheo.com/api',
        'https://testnet-faucet.autheo.com/v1/api',
        'https://testnet-faucet.autheo.com/faucet'
    ]
    
    endpoints = [
        '/claim',
        '/faucet',
        '/request',
        '/drip'
    ]
    
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://testnet-faucet.autheo.com',
        'Referer': 'https://testnet-faucet.autheo.com/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    data = {
        'address': '0x50CF84E8348bf31C95d0E29c673CB66863ECA76F',
        'chain': 'autheo'
    }
    
    for base_url in base_urls:
        for endpoint in endpoints:
            url = f"{base_url}{endpoint}"
            try:
                print(f"\n尝试 POST 请求到: {url}")
                response = requests.post(url, headers=headers, json=data, timeout=10)
                print(f"状态码: {response.status_code}")
                print(f"响应: {response.text[:200]}..." if len(response.text) > 200 else f"响应: {response.text}")
            except Exception as e:
                print(f"请求失败: {str(e)}")

def analyze_website_structure():
    print("\n分析网站结构...")
    try:
        response = requests.get('https://testnet-faucet.autheo.com', timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            scripts = soup.find_all('script')
            
            print(f"找到 {len(scripts)} 个脚本标签")
            
            # 查找可能包含API端点的JavaScript文件
            js_urls = []
            for script in scripts:
                if script.has_attr('src') and script['src'].startswith('/static/js/'):
                    js_urls.append(f"https://testnet-faucet.autheo.com{script['src']}")
            
            print(f"找到 {len(js_urls)} 个JavaScript文件:")
            for url in js_urls:
                print(f"  - {url}")
                
            # 下载并分析第一个JS文件
            if js_urls:
                js_response = requests.get(js_urls[0], timeout=10)
                if js_response.status_code == 200:
                    js_content = js_response.text
                    
                    # 查找可能的API端点
                    api_candidates = []
                    for line in js_content.split('\n'):
                        if '/api/' in line and 'claim' in line.lower():
                            api_candidates.append(line)
                    
                    print(f"\n找到 {len(api_candidates)} 个可能的API端点:")
                    for i, candidate in enumerate(api_candidates[:10]):  # 只显示前10个
                        print(f"  {i+1}. {candidate.strip()}")
        else:
            print(f"获取网站失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"分析失败: {str(e)}")

def test_with_2captcha_simulation():
    print("\n模拟使用2captcha服务...")
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://testnet-faucet.autheo.com',
        'Referer': 'https://testnet-faucet.autheo.com/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # 模拟2captcha返回的验证码
    simulated_captcha = "03AGdBq24PK3C0J8RRjL9M5Iq6Hn6YFzZ7KZ6Hn6YFzZ7K"

    # 尝试不同的API端点
    endpoints = [
        'https://testnet-faucet.autheo.com/api/claim',
        'https://testnet-faucet.autheo.com/api/faucet/claim',
        'https://testnet-faucet.autheo.com/api/faucet'
    ]
    
    for endpoint in endpoints:
        data = {
            'address': '0x50CF84E8348bf31C95d0E29c673CB66863ECA76F',
            'chain': 'autheo',
            'g-recaptcha-response': simulated_captcha
        }
        
        try:
            print(f"\n尝试请求: {endpoint}")
            response = requests.post(endpoint, headers=headers, json=data, timeout=10)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text}")
        except Exception as e:
            print(f"请求失败: {str(e)}")

def suggest_alternative_solutions():
    print("\n建议替代解决方案:")
    print("1. 使用其他验证码解决服务:")
    print("   - 尝试2captcha.com (与anticaptcha类似但可能有不同的成功率)")
    print("   - 尝试capsolver.com (专门针对复杂验证码)")
    print("   - 尝试使用浏览器自动化工具如Selenium或Playwright结合验证码服务")
    
    print("\n2. 寻找替代水龙头:")
    print("   - 查找其他官方或社区运营的Autheo测试网水龙头")
    print("   - 联系Autheo团队获取测试币")
    print("   - 在Discord或Telegram社区请求测试币")
    
    print("\n3. 优化当前验证码解决方案:")
    print("   - 增加更多重试次数和等待时间")
    print("   - 尝试不同的anticaptcha API参数设置")
    print("   - 检查anticaptcha账户余额和状态")

def main():
    # 测试不同的API端点
    test_api_endpoints()
    
    # 分析网站结构
    analyze_website_structure()
    
    # 测试模拟2captcha服务
    test_with_2captcha_simulation()
    
    # 建议替代解决方案
    suggest_alternative_solutions()

if __name__ == "__main__":
    main()