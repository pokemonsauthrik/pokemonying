import sys
import requests
import urllib3
import json
import time
import os
from anticaptchaofficial.recaptchav3proxyless import recaptchaV3Proxyless

# 禁用不安全请求警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 测试地址
TEST_ADDRESS = "0x50CF84E8348bf31C95d0E29c673CB66863ECA76F"

# 请在此处填写您的Anti-captcha API密钥
ANTI_CAPTCHA_KEY = "80a912f8e62b16f4639a4a8bbdd4d474"

def test_solve_captcha():
    print("\n测试验证码解决功能...")
    
    if not ANTI_CAPTCHA_KEY:
        print("请提供有效的Anti-captcha API密钥进行测试")
        return None
    
    solver = recaptchaV3Proxyless()
    solver.set_verbose(1)
    solver.set_key(ANTI_CAPTCHA_KEY)
    solver.set_website_url("https://testnet-faucet.autheo.com")
    solver.set_website_key("6LfOA04pAAAAAL9ttkwIz40hC63_7IsaU2MgcwVH")
    solver.set_page_action('faucet_submit')
    solver.set_min_score(0.7)
    
    # 增加更多配置以提高成功率
    solver.set_soft_id(0)
    # 删除不存在的方法调用
    
    print(f"开始解决验证码，使用API密钥: {ANTI_CAPTCHA_KEY[:5]}...{ANTI_CAPTCHA_KEY[-5:] if len(ANTI_CAPTCHA_KEY) > 10 else ''}")
    print(f"目标网站: https://testnet-faucet.autheo.com, 验证码密钥: 6LfOA04pAAAAAL9ttkwIz40hC63_7IsaU2MgcwVH")
    
    try:
        # 增加重试次数和等待时间
        for attempt in range(3):
            print(f"尝试解决验证码 (尝试 {attempt+1}/3)...")
            
            # 检查API密钥是否为空
            if not ANTI_CAPTCHA_KEY or len(ANTI_CAPTCHA_KEY) < 10:
                print("错误: API密钥无效或为空")
                return None
            
            # 尝试解决验证码
            try:
                response = solver.solve_and_return_solution()
                
                # 检查响应
                if response != 0:
                    print(f"验证码解决成功! 响应长度: {len(response)}")
                    print(f"响应前30个字符: {response[:30]}...")
                    return response
                else:
                    error_msg = solver.err_string if hasattr(solver, 'err_string') else "未知错误"
                    print(f"验证码解决失败: {error_msg}")
                    
                    # 根据错误类型决定是否重试
                    if "ERROR_KEY_DOES_NOT_EXIST" in error_msg or "ERROR_ZERO_BALANCE" in error_msg:
                        print("API密钥无效或余额不足，无法继续尝试")
                        return None
                    elif "ERROR_NO_SLOT_AVAILABLE" in error_msg:
                        wait_time = 10
                        print(f"服务器繁忙，等待{wait_time}秒后重试...")
                        time.sleep(wait_time)
                    else:
                        wait_time = 5 * (attempt + 1)  # 逐渐增加等待时间
                        print(f"等待{wait_time}秒后重试...")
                        time.sleep(wait_time)
            except Exception as inner_e:
                print(f"解决验证码过程中出错: {str(inner_e)}")
                time.sleep(5)
        
        print("验证码解决失败，已达到最大重试次数")
        return None
    except Exception as e:
        print(f"验证码解决出错: {str(e)}")
        # 尝试获取更详细的错误信息
        if hasattr(e, "__dict__"):
            print(f"错误详情: {str(e.__dict__)}")
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

    # 尝试多个API端点
    endpoints = [
        'https://testnet-faucet.autheo.com/api/claim',
        'https://testnet-faucet.autheo.com/api/faucet/claim'
    ]
    
    json_data = {
        'address': TEST_ADDRESS,
        'chain': 'autheo',
        'g-recaptcha-response': captcha_response
    }

    for endpoint in endpoints:
        try:
            print(f"\n尝试请求: {endpoint}")
            print(f"请求数据: {json.dumps(json_data, ensure_ascii=False)}")
            
            response = requests.post(
                'https://faucet.movementlabs.xyz/api/claim',
                headers=headers, 
                json=json_data,
                verify=False,
                timeout=15
            )
            
            print(f"状态码: {response.status_code}")
            print(f"响应: {response.text}")
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if 'hash' in result:
                        print(f"领取成功! 交易哈希: {result['hash']}")
                        return True
                    elif 'error' in result:
                        print(f"API错误: {result['error']}")
                except json.JSONDecodeError:
                    print(f"无法解析JSON响应")
        except Exception as e:
            print(f"请求失败: {str(e)}")
    
    return False

def check_anticaptcha_balance():
    print("\n检查Anti-captcha账户余额...")
    
    if not ANTI_CAPTCHA_KEY:
        print("请提供有效的Anti-captcha API密钥")
        return
    
    try:
        # 构建API请求
        url = "https://api.anti-captcha.com/getBalance"
        data = {
            "clientKey": ANTI_CAPTCHA_KEY
        }
        
        response = requests.post(url, json=data)
        result = response.json()
        
        print(f"API响应: {json.dumps(result, ensure_ascii=False)}")
        
        if result.get("errorId") == 0:
            balance = result.get("balance")
            print(f"当前账户余额: ${balance}")
            if balance < 0.1:
                print("警告: 账户余额较低，可能影响验证码解决服务")
        else:
            print(f"获取余额失败: {result.get('errorCode')} - {result.get('errorDescription')}")
    except Exception as e:
        print(f"检查余额时出错: {str(e)}")

def main():
    print("===== 验证码解决方案测试 =====")
    
    # 检查Anti-captcha账户余额
    check_anticaptcha_balance()
    
    # 测试验证码解决
    captcha_response = test_solve_captcha()
    
    # 测试领取测试币
    if captcha_response:
        test_get_test_token(captcha_response)
    else:
        print("\n无法获取验证码响应，跳过领取测试")

if __name__ == "__main__":
    main()