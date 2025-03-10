import requests
import json
import time
import sys

# 测试不同方法获取测试币

def test_direct_api_request():
    print("测试直接API请求（无验证码）...")
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

    try:
        response = requests.post(
            'https://testnet-faucet.autheo.com/api/claim',
            headers=headers,
            json=data,
            timeout=10
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"请求失败: {str(e)}")
        return None

def test_with_empty_captcha():
    print("\n测试使用空验证码...")
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
        'chain': 'autheo',
        'g-recaptcha-response': ''
    }

    try:
        response = requests.post(
            'https://testnet-faucet.autheo.com/api/claim',
            headers=headers,
            json=data,
            timeout=10
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"请求失败: {str(e)}")
        return None

def test_with_fake_captcha():
    print("\n测试使用伪造验证码...")
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9',
        'Connection': 'keep-alive',
        'Content-Type': 'application/json',
        'Origin': 'https://testnet-faucet.autheo.com',
        'Referer': 'https://testnet-faucet.autheo.com/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    # 尝试一个伪造的验证码响应
    fake_captcha = "03AGdBq24PK3C0J8RRjL9M5Iq6Hn6YFzZ7KZ6Hn6YFzZ7K"

    data = {
        'address': '0x50CF84E8348bf31C95d0E29c673CB66863ECA76F',
        'chain': 'autheo',
        'g-recaptcha-response': fake_captcha
    }

    try:
        response = requests.post(
            'https://testnet-faucet.autheo.com/api/claim',
            headers=headers,
            json=data,
            timeout=10
        )
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.text}")
        return response.json() if response.status_code == 200 else None
    except Exception as e:
        print(f"请求失败: {str(e)}")
        return None

def main():
    # 测试直接API请求
    test_direct_api_request()
    
    # 测试空验证码
    test_with_empty_captcha()
    
    # 测试伪造验证码
    test_with_fake_captcha()

if __name__ == "__main__":
    main()