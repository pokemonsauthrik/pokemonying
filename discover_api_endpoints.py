import requests
import json
import time
import sys
from bs4 import BeautifulSoup
import re
import urllib3

# 禁用不安全请求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 测试地址
TEST_ADDRESS = "0x50CF84E8348bf31C95d0E29c673CB66863ECA76F"

# 模拟验证码响应
SIMULATED_CAPTCHA = "03AGdBq24PK3C0J8RRjL9M5Iq6Hn6YFzZ7KZ6Hn6YFzZ7K"

# 请求头
HEADERS = {
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Connection': 'keep-alive',
    'Content-Type': 'application/json',
    'Origin': 'https://testnet-faucet.autheo.com',
    'Referer': 'https://testnet-faucet.autheo.com/',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
}

def discover_js_api_endpoints():
    """通过分析JavaScript文件发现API端点"""
    print("\n深入分析JavaScript文件寻找API端点...")
    try:
        # 获取网站HTML
        response = requests.get('https://testnet-faucet.autheo.com', timeout=10, verify=False)
        if response.status_code != 200:
            print(f"获取网站失败，状态码: {response.status_code}")
            return []
            
        # 解析HTML找出所有JavaScript文件
        soup = BeautifulSoup(response.text, 'html.parser')
        scripts = soup.find_all('script')
        
        # 收集所有JavaScript文件URL
        js_urls = []
        for script in scripts:
            if script.has_attr('src'):
                # 处理相对路径
                src = script['src']
                if src.startswith('/'):
                    js_urls.append(f"https://testnet-faucet.autheo.com{src}")
                elif src.startswith('http'):
                    js_urls.append(src)
                else:
                    js_urls.append(f"https://testnet-faucet.autheo.com/{src}")
        
        print(f"找到 {len(js_urls)} 个JavaScript文件:")
        for url in js_urls:
            print(f"  - {url}")
        
        # 分析所有JavaScript文件寻找API端点
        api_endpoints = []
        for url in js_urls:
            try:
                print(f"\n分析: {url}")
                js_response = requests.get(url, timeout=10, verify=False)
                if js_response.status_code == 200:
                    js_content = js_response.text
                    
                    # 使用正则表达式查找API端点
                    # 查找形如 /api/xxx 的路径
                    api_patterns = [
                        r'"/api/([^"]+)"',
                        r'"/v1/api/([^"]+)"',
                        r'"/faucet/([^"]+)"',
                        r'\'/api/([^\']+)\'',
                        r'`/api/([^`]+)`',
                        r'fetch\("([^"]+)"\)',
                        r'axios\.post\("([^"]+)"',
                        r'axios\.get\("([^"]+)"'
                    ]
                    
                    for pattern in api_patterns:
                        matches = re.findall(pattern, js_content)
                        for match in matches:
                            # 构建完整URL
                            if match.startswith('http'):
                                api_endpoints.append(match)
                            elif match.startswith('/api/'):
                                api_endpoints.append(f"https://testnet-faucet.autheo.com{match}")
                            elif match.startswith('api/'):
                                api_endpoints.append(f"https://testnet-faucet.autheo.com/{match}")
                            elif 'claim' in match.lower() or 'faucet' in match.lower():
                                api_endpoints.append(f"https://testnet-faucet.autheo.com/api/{match}")
            except Exception as e:
                print(f"分析 {url} 失败: {str(e)}")
        
        # 去重并过滤
        api_endpoints = list(set(api_endpoints))
        filtered_endpoints = []
        for endpoint in api_endpoints:
            if 'claim' in endpoint.lower() or 'faucet' in endpoint.lower() or 'drip' in endpoint.lower() or 'request' in endpoint.lower():
                filtered_endpoints.append(endpoint)
        
        print(f"\n找到 {len(filtered_endpoints)} 个可能的API端点:")
        for i, endpoint in enumerate(filtered_endpoints):
            print(f"  {i+1}. {endpoint}")
            
        return filtered_endpoints
    except Exception as e:
        print(f"发现API端点失败: {str(e)}")
        return []

def test_api_endpoint(endpoint, with_captcha=True):
    """测试单个API端点"""
    print(f"\n测试API端点: {endpoint}")
    
    # 准备请求数据
    data = {
        'address': TEST_ADDRESS,
        'chain': 'autheo'
    }
    
    if with_captcha:
        data['g-recaptcha-response'] = SIMULATED_CAPTCHA
    
    # 尝试不同的请求方法
    methods = ['POST', 'GET']
    for method in methods:
        try:
            print(f"尝试 {method} 请求...")
            if method == 'POST':
                response = requests.post(endpoint, headers=HEADERS, json=data, timeout=10, verify=False)
            else:
                response = requests.get(endpoint, headers=HEADERS, params=data, timeout=10, verify=False)
            
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}..." if len(response.text) > 200 else f"响应: {response.text}")
            
            # 分析响应
            if response.status_code == 200:
                try:
                    result = response.json()
                    if 'hash' in result:
                        print("成功! 找到有效的API端点和请求方法!")
                        return True, method, endpoint
                except:
                    pass
        except Exception as e:
            print(f"{method} 请求失败: {str(e)}")
    
    return False, None, None

def test_api_variations():
    """测试API端点的各种变体"""
    print("\n测试API端点变体...")
    
    # 基础URL
    base_urls = [
        'https://testnet-faucet.autheo.com',
        'https://testnet-faucet.autheo.com/api',
        'https://testnet-faucet.autheo.com/v1/api',
        'https://testnet-faucet.autheo.com/faucet',
        'https://testnet-faucet.autheo.com/api/faucet'
    ]
    
    # 端点路径
    endpoints = [
        '/claim',
        '/faucet/claim',
        '/request',
        '/drip',
        '/faucet',
        '/get',
        '/token',
        '/testnet'
    ]
    
    # 测试所有组合
    for base_url in base_urls:
        for endpoint in endpoints:
            url = f"{base_url}{endpoint}"
            success, method, _ = test_api_endpoint(url)
            if success:
                return success, method, url
    
    return False, None, None

def test_request_parameters():
    """测试不同的请求参数组合"""
    print("\n测试不同的请求参数组合...")
    
    # 使用已知的API端点
    endpoint = 'https://testnet-faucet.autheo.com/api/claim'
    
    # 测试不同的参数组合
    parameter_sets = [
        # 基本参数
        {'address': TEST_ADDRESS, 'chain': 'autheo', 'g-recaptcha-response': SIMULATED_CAPTCHA},
        # 尝试不同的参数名
        {'wallet': TEST_ADDRESS, 'chain': 'autheo', 'g-recaptcha-response': SIMULATED_CAPTCHA},
        {'address': TEST_ADDRESS, 'network': 'autheo', 'g-recaptcha-response': SIMULATED_CAPTCHA},
        {'address': TEST_ADDRESS, 'chain': 'autheo', 'captcha': SIMULATED_CAPTCHA},
        {'address': TEST_ADDRESS, 'chain': 'autheo', 'recaptcha': SIMULATED_CAPTCHA},
        # 尝试不同的链名
        {'address': TEST_ADDRESS, 'chain': 'movement', 'g-recaptcha-response': SIMULATED_CAPTCHA},
        {'address': TEST_ADDRESS, 'chain': 'testnet', 'g-recaptcha-response': SIMULATED_CAPTCHA},
    ]
    
    for params in parameter_sets:
        print(f"\n测试参数: {params}")
        try:
            response = requests.post(endpoint, headers=HEADERS, json=params, timeout=10, verify=False)
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text[:200]}..." if len(response.text) > 200 else f"响应: {response.text}")
            
            # 分析响应
            if response.status_code == 200:
                try:
                    result = response.json()
                    if 'hash' in result:
                        print("成功! 找到有效的请求参数!")
                        return True, params
                except:
                    pass
        except Exception as e:
            print(f"请求失败: {str(e)}")
    
    return False, None

def main():
    print("开始发现有效的API端点和请求格式...")
    
    # 1. 从JavaScript文件中发现API端点
    js_endpoints = discover_js_api_endpoints()
    
    # 2. 测试从JavaScript中发现的端点
    for endpoint in js_endpoints:
        success, method, url = test_api_endpoint(endpoint)
        if success:
            print(f"\n成功! 找到有效的API端点: {url} 使用 {method} 方法")
            return
    
    # 3. 测试API端点变体
    success, method, url = test_api_variations()
    if success:
        print(f"\n成功! 找到有效的API端点: {url} 使用 {method} 方法")
        return
    
    # 4. 测试不同的请求参数
    success, params = test_request_parameters()
    if success:
        print(f"\n成功! 找到有效的请求参数: {params}")
        return
    
    print("\n未能找到有效的API端点或请求格式。建议尝试以下方法:")
    print("1. 使用浏览器开发者工具监控网络请求，直接观察实际请求")
    print("2. 尝试使用Selenium或Playwright自动化浏览器操作")
    print("3. 联系Autheo团队获取正确的API文档")

if __name__ == "__main__":
    main()