import sys
import os
import time
import json
import pickle
import requests
from datetime import datetime, timedelta
from anticaptchaofficial.recaptchav2proxyless import recaptchaV2Proxyless as recaptchav2

# 导入Faucet.py中的类
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from Faucet import WalletProxyPair, DATA_FILE

# 测试地址和代理
TEST_ADDRESS = "0x50CF84E8348bf31C95d0E29c673CB66863ECA76F"
TEST_PROXY = "http://127.0.0.1:7890"

# Anti-captcha API密钥 - 请替换为您的密钥
ANTI_CAPTCHA_KEY = "your_anti_captcha_key_here"

def test_wallet_proxy_pair():
    print("\n测试WalletProxyPair类的功能...")
    
    # 创建测试对象
    pair = WalletProxyPair(TEST_ADDRESS, {"http": TEST_PROXY, "https": TEST_PROXY})
    
    # 测试初始状态
    print(f"初始状态: 可领取状态 = {pair.can_claim()}")
    print(f"初始下次可领取时间: {pair.get_next_claim_time_str()}")
    
    # 测试添加领取记录
    pair.add_claim()
    print(f"添加一次领取后: 可领取状态 = {pair.can_claim()}")
    print(f"领取次数: {len(pair.last_claim_times)}")
    
    # 测试添加第二次领取记录
    pair.add_claim()
    print(f"添加第二次领取后: 可领取状态 = {pair.can_claim()}")
    print(f"领取次数: {len(pair.last_claim_times)}")
    print(f"下次可领取时间: {pair.get_next_claim_time_str()}")
    
    # 测试时间计算
    # 模拟24小时前的领取记录
    old_time = datetime.now() - timedelta(hours=25)
    pair.last_claim_times = [old_time, datetime.now()]
    print(f"模拟一条24小时前的记录后: 可领取状态 = {pair.can_claim()}")
    print(f"领取次数: {len(pair.last_claim_times)}")
    
    # 调用can_claim会清理过期记录
    pair.can_claim()
    print(f"调用can_claim后: 领取次数 = {len(pair.last_claim_times)}")
    
    return pair

def test_solve_captcha():
    print("\n测试验证码解决功能...")
    
    if not ANTI_CAPTCHA_KEY or ANTI_CAPTCHA_KEY == "your_anti_captcha_key_here":
        print("请提供有效的Anti-captcha API密钥进行测试")
        return None
    
    solver = recaptchav2()
    solver.set_verbose(1)
    solver.set_key(ANTI_CAPTCHA_KEY)
    solver.set_website_url("https://testnet-faucet.autheo.com")
    solver.set_website_key("6LfOA04pAAAAAL9ttkwIz40hC63_7IsaU2MgcwVH")
    
    try:
        print("尝试解决验证码...")
        response = solver.solve_and_return_solution()
        if response != 0:
            print(f"验证码解决成功: {response[:30]}...")
            return response
        else:
            print(f"验证码解决失败: {solver.err_string}")
            return None
    except Exception as e:
        print(f"验证码解决出错: {str(e)}")
        return None

def test_get_test_token(captcha_response=None):
    print("\n测试领取测试币功能...")
    
    if not captcha_response:
        print("没有验证码响应，无法测试领取功能")
        return False
    
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://testnet-faucet.autheo.com',
        'Referer': 'https://testnet-faucet.autheo.com/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    json_data = {
        'address': TEST_ADDRESS,
        'chain': 'autheo',
        'g-recaptcha-response': captcha_response
    }

    try:
        print(f"尝试为地址 {TEST_ADDRESS} 领取测试币...")
        response = requests.post(
            'https://testnet-faucet.autheo.com/api/claim', 
            headers=headers, 
            json=json_data,
            proxies={"http": TEST_PROXY, "https": TEST_PROXY} if TEST_PROXY else None,
            verify=False,
            timeout=10
        )
        result = response.json()
        print(f'领水结果: {json.dumps(result, ensure_ascii=False)}')
        
        if 'hash' in result:
            print("领取成功!")
            return True
        elif 'error' in result and 'rate limit' in result['error'].lower():
            print("请求频率限制，请稍后再试")
            return False
        else:
            print("领取失败")
            return False
    except Exception as e:
        print(f"请求失败: {str(e)}")
        return False

def test_data_save_load():
    print("\n测试数据保存和加载功能...")
    
    # 创建测试数据
    test_pair = WalletProxyPair(TEST_ADDRESS, {"http": TEST_PROXY, "https": TEST_PROXY})
    test_pair.add_claim()
    test_pair.balance = 1.234567
    
    test_data = {
        'api_key': 'test_api_key',
        'proxies': TEST_PROXY,
        'addresses': TEST_ADDRESS,
        'wallet_proxy_pairs': [test_pair]
    }
    
    # 保存测试数据
    try:
        # 备份现有数据
        backup_data = None
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'rb') as f:
                backup_data = pickle.load(f)
        
        # 保存测试数据
        with open(DATA_FILE, 'wb') as f:
            pickle.dump(test_data, f)
        print("测试数据已保存")
        
        # 加载并验证
        with open(DATA_FILE, 'rb') as f:
            loaded_data = pickle.load(f)
        
        print(f"加载的API密钥: {loaded_data.get('api_key')}")
        print(f"加载的代理: {loaded_data.get('proxies')}")
        print(f"加载的地址: {loaded_data.get('addresses')}")
        
        loaded_pairs = loaded_data.get('wallet_proxy_pairs', [])
        if loaded_pairs:
            pair = loaded_pairs[0]
            print(f"加载的钱包地址: {pair.address}")
            print(f"加载的余额: {pair.balance}")
            print(f"加载的领取次数: {len(pair.last_claim_times)}")
        
        # 恢复备份
        if backup_data:
            with open(DATA_FILE, 'wb') as f:
                pickle.dump(backup_data, f)
            print("已恢复原始数据")
        
        return True
    except Exception as e:
        print(f"数据保存/加载测试失败: {str(e)}")
        return False

def main():
    print("开始测试水龙头脚本改进...")
    
    # 测试WalletProxyPair类
    test_wallet_proxy_pair()
    
    # 测试数据保存和加载
    test_data_save_load()
    
    # 测试验证码解决
    captcha_response = test_solve_captcha()
    
    # 如果验证码解决成功，测试领取测试币
    if captcha_response:
        test_get_test_token(captcha_response)
    
    print("\n测试完成!")

if __name__ == "__main__":
    main()