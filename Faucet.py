import sys
import requests
import urllib3
import json
import time
import os
import pickle
from datetime import datetime, timedelta
from anticaptchaofficial.recaptchav2proxyless import recaptchaV2Proxyless as recaptchav2
try:
    from web3 import Web3
except ImportError:
    print("请先安装web3库: pip install web3")
    sys.exit(1)
try:
    from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLabel, QProgressBar, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QCheckBox, QComboBox
    from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
    from PyQt5.QtGui import QCloseEvent
except ImportError:
    print("请先安装PyQt5库: pip install PyQt5")
    sys.exit(1)

# 尝试导入Selenium相关库
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("注意: Selenium未安装，浏览器自动化功能不可用。如需使用，请安装: pip install selenium webdriver-manager")

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

MAX_PROXY_CHECK_ATTEMPTS = 5
SLEEP_TIME = 60
CLAIM_INTERVAL = 24 * 3600  # 24小时间隔
MAX_CLAIMS_PER_DAY = 2
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'faucet_data.pkl')

class WalletProxyPair:
    def __init__(self, address, proxy):
        self.address = address
        self.proxy = proxy
        self.last_claim_times = []
        self.balance = 0
        self.next_claim_time = None
    
    def can_claim(self):
        now = datetime.now()
        # 清理24小时前的记录
        self.last_claim_times = [t for t in self.last_claim_times 
                                if now - t < timedelta(hours=24)]
        if len(self.last_claim_times) < MAX_CLAIMS_PER_DAY:
            return True
        else:
            # 设置下次可领取时间
            oldest_claim = min(self.last_claim_times)
            self.next_claim_time = oldest_claim + timedelta(hours=24)
            return False
    
    def add_claim(self):
        self.last_claim_times.append(datetime.now())
        
    def get_next_claim_time_str(self):
        if not self.next_claim_time:
            return "可领取"
        now = datetime.now()
        if self.next_claim_time <= now:
            return "可领取"
        time_diff = self.next_claim_time - now
        hours, remainder = divmod(time_diff.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

class ProxyCheckWorker(QThread):
    finished = pyqtSignal(bool)
    log = pyqtSignal(str)
    
    def __init__(self, proxy):
        super().__init__()
        self.proxy = proxy
    
    def run(self):
        for i in range(MAX_PROXY_CHECK_ATTEMPTS):
            try:
                response = requests.get('https://myip.ipip.net', proxies=self.proxy, timeout=5)
                self.log.emit(f'验证成功, IP信息: {response.text}')
                self.finished.emit(True)
                return
            except Exception as e:
                self.log.emit('代理失效，等待1分钟后重新验证')
                time.sleep(SLEEP_TIME)
        self.log.emit('代理验证失败，无法继续执行任务')
        self.finished.emit(False)

class SeleniumFaucetWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal()
    update_balance = pyqtSignal(str, float)
    
    def __init__(self, wallet_proxy_pairs):
        super().__init__()
        self.wallet_proxy_pairs = wallet_proxy_pairs
        self.running = True
    
    def stop(self):
        self.running = False
        
    def run(self):
        if not SELENIUM_AVAILABLE:
            self.log.emit("错误: Selenium未安装，无法使用浏览器自动化功能")
            self.finished.emit()
            return
            
        total = len(self.wallet_proxy_pairs)
        for idx, pair in enumerate(self.wallet_proxy_pairs):
            if not self.running:
                break
                
            if not pair.can_claim():
                self.log.emit(f'地址 {pair.address} 在24小时内已达到领取上限，下次可领取时间: {pair.get_next_claim_time_str()}')
                continue
                
            if self.claim_with_selenium(pair):
                pair.add_claim()
                # 更新余额
                self.check_balance(pair)
                
            self.progress.emit(int((idx + 1) * 100 / total))
            
        self.finished.emit()
    
    def claim_with_selenium(self, pair):
        self.log.emit(f"使用浏览器自动化为地址 {pair.address} 领取测试币...")
        
        try:
            # 设置Chrome选项
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # 无头模式
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            
            # 设置代理
            if pair.proxy:
                proxy_str = list(pair.proxy.values())[0]  # 获取代理字符串
                chrome_options.add_argument(f'--proxy-server={proxy_str}')
            
            # 初始化WebDriver
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            
            try:
                # 访问水龙头网站
                self.log.emit("正在访问水龙头网站...")
                driver.get("https://testnet-faucet.autheo.com")
                
                # 等待页面加载
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "input"))
                )
                
                # 输入钱包地址
                self.log.emit("输入钱包地址...")
                address_input = driver.find_element(By.TAG_NAME, "input")
                address_input.clear()
                address_input.send_keys(pair.address)
                
                # 点击请求按钮
                self.log.emit("点击请求按钮...")
                buttons = driver.find_elements(By.TAG_NAME, "button")
                claim_button = None
                
                for button in buttons:
                    if "REQUEST" in button.text.upper() and "THEO" in button.text.upper():
                        claim_button = button
                        break
                
                if claim_button:
                    claim_button.click()
                    self.log.emit("已点击请求按钮，等待结果...")
                    
                    # 等待结果
                    time.sleep(5)
                    
                    # 检查结果
                    page_source = driver.page_source.lower()
                    if "success" in page_source or "transaction" in page_source or "hash" in page_source:
                        self.log.emit("领取成功!")
                        return True
                    elif "rate limit" in page_source:
                        self.log.emit("请求频率限制，请稍后再试")
                    elif "captcha" in page_source:
                        self.log.emit("需要验证码，无法自动完成")
                    else:
                        self.log.emit(f"未知结果，可能失败: {driver.page_source[:200]}...")
                else:
                    self.log.emit("未找到请求按钮")
            finally:
                # 关闭浏览器
                driver.quit()
                
        except Exception as e:
            self.log.emit(f"浏览器自动化出错: {str(e)}")
        
        return False
    
    def check_balance(self, pair):
        try:
            # 这里使用Web3检查余额
            w3 = Web3(Web3.HTTPProvider('https://rpc-testnet.autheo.com'))
            balance = w3.eth.get_balance(pair.address)
            balance_eth = w3.from_wei(balance, 'ether')
            pair.balance = balance_eth
            self.update_balance.emit(pair.address, balance_eth)
            self.log.emit(f'地址 {pair.address} 当前余额: {balance_eth} AUTH')
        except Exception as e:
            self.log.emit(f"获取余额失败: {str(e)}")

class FaucetWorker(QThread):
    progress = pyqtSignal(int)
    log = pyqtSignal(str)
    finished = pyqtSignal()
    update_balance = pyqtSignal(str, float)
    
    def __init__(self, wallet_proxy_pairs, anti_captcha_key):
        super().__init__()
        self.wallet_proxy_pairs = wallet_proxy_pairs
        self.anti_captcha_key = anti_captcha_key
        self.running = True
    
    def stop(self):
        self.running = False
    
    def retry_operation(self, operation_name, max_attempts, operation_callback, error_callback=None):
        for attempt in range(max_attempts):
            if not self.running:
                return None
            try:
                self.log.emit(f"尝试{operation_name} (尝试 {attempt+1}/{max_attempts})...")
                result = operation_callback()
                if result:
                    return result
            except Exception as e:
                if error_callback:
                    error_callback(e, attempt)
                else:
                    self.log.emit(f"{operation_name}失败: {str(e)}")
            wait_time = 5 * (attempt + 1)
            time.sleep(wait_time)
        return None

    def solve_captcha(self):
        solver = recaptchav2enterpriseproxyon()
        solver.set_verbose(1)
        solver.set_key(self.anti_captcha_key)
        solver.set_website_url("https://testnet-faucet.autheo.com")
        solver.set_website_key("6LfOA04pAAAAAL9ttkwIz40hC63_7IsaU2MgcwVH")
        
        # 设置代理服务器配置
        solver.set_proxy_type("http")
        solver.set_proxy_address(self.proxy_address if hasattr(self, 'proxy_address') else "")
        solver.set_proxy_port(self.proxy_port if hasattr(self, 'proxy_port') else 0)
        solver.set_proxy_login(self.proxy_login if hasattr(self, 'proxy_login') else "")
        solver.set_proxy_password(self.proxy_password if hasattr(self, 'proxy_password') else "")
        
        # 设置用户代理和其他配置
        solver.set_user_agent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        solver.set_soft_id(0)
        
        # 添加更详细的日志
        self.log.emit(f"开始解决验证码，使用API密钥: {self.anti_captcha_key[:5]}...{self.anti_captcha_key[-5:] if len(self.anti_captcha_key) > 10 else ''}")
        self.log.emit(f"目标网站: https://testnet-faucet.autheo.com, 验证码密钥: 6LfOA04pAAAAAL9ttkwIz40hC63_7IsaU2MgcwVH")
        
        # 使用通用重试方法处理验证码解决
        def captcha_operation():
            try:
                response = solver.solve_and_return_solution()
                if response != 0:
                    return response
                error_msg = solver.err_string if hasattr(solver, 'err_string') else "未知错误"
                raise Exception(f"验证码解决失败: {error_msg}")
            except Exception as e:
                self.log.emit(str(e))
                raise

        try:
            result = self.retry_operation(
                operation_name="解决验证码",
                max_attempts=5,
                operation_callback=captcha_operation,
                error_callback=lambda e, a: self.log.emit(f"第{a+1}次尝试失败: {str(e)}")
            )
            return result if result else None
        except Exception as e:
            self.log.emit(f"验证码解决出错: {str(e)}")
            if hasattr(e, "__dict__"):
                self.log.emit(f"错误详情: {str(e.__dict__)}")
            return None
    
    def run(self):
        total = len(self.wallet_proxy_pairs)
        for idx, pair in enumerate(self.wallet_proxy_pairs):
            if not self.running:
                break
            
            if not pair.can_claim():
                self.log.emit(f'地址 {pair.address} 在24小时内已达到领取上限，下次可领取时间: {pair.get_next_claim_time_str()}')
                continue
                
            if self.getTestToken(pair):
                pair.add_claim()
                # 更新余额
                self.check_balance(pair)
                
            self.progress.emit(int((idx + 1) * 100 / total))
            
        self.finished.emit()
    
    def getTestToken(self, pair):
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Content-Type': 'application/json',
            'Origin': 'https://testnet-faucet.autheo.com',
            'Referer': 'https://testnet-faucet.autheo.com/',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

        self.log.emit(f"开始为地址 {pair.address} 领取测试币...")
        
        # 尝试解决验证码
        self.log.emit("正在获取验证码响应...")
        captcha_response = self.solve_captcha()
        if not captcha_response:
            self.log.emit("无法获取有效的验证码响应，领取失败")
            return False

        self.log.emit(f"成功获取验证码响应，长度: {len(captcha_response)}")
        
        json_data = {
            'address': pair.address,
            'chain': 'autheo',
            'g-recaptcha-response': captcha_response
        }

        # 尝试多个API端点
        endpoints = [
            'https://testnet-faucet.autheo.com/api/v2/claim',
    'https://faucet.movementlabs.xyz/api/claim',
            'https://testnet-faucet.autheo.com/api/faucet/claim'
        ]
        
        try:
            # 增加重试次数和等待时间
            for attempt in range(5):  # 从3次增加到5次
                if not self.running:
                    self.log.emit("任务已停止")
                    return False
                    
                # 对每个端点尝试请求
                for endpoint in endpoints:
                    try:
                        self.log.emit(f"尝试领取测试币 (尝试 {attempt+1}/5, 端点: {endpoint})...")
                        
                        # 添加代理日志
                        if pair.proxy:
                            self.log.emit(f"使用代理: {pair.proxy}")
                        
                        response = requests.post(
                            endpoint, 
                            headers=headers, 
                            json=json_data,
                            proxies=pair.proxy,
                            verify=False,
                            timeout=15  # 增加超时时间
                        )
                        
                        # 检查HTTP状态码
                        if response.status_code != 200:
                            self.log.emit(f"HTTP错误: {response.status_code}, 响应: {response.text[:200]}")
                            continue
                            
                        # 尝试解析JSON响应
                        try:
                            result = response.json()
                            self.log.emit(f'领水结果: {json.dumps(result, ensure_ascii=False)}')
                            
                            # 检查成功标志
                            if 'hash' in result:
                                self.log.emit(f"领取成功! 交易哈希: {result['hash']}")
                                return True
                            elif 'error' in result:
                                error_msg = result['error'].lower()
                                if 'rate limit' in error_msg:
                                    self.log.emit(f"请求频率限制，等待20秒后重试...")
                                    time.sleep(20)
                                    break  # 跳出端点循环，尝试下一次重试
                                else:
                                    self.log.emit(f"API错误: {result['error']}")
                            else:
                                self.log.emit(f"未知响应格式: {json.dumps(result, ensure_ascii=False)}")
                        except json.JSONDecodeError:
                            self.log.emit(f"无法解析JSON响应: {response.text[:200]}")
                    except requests.exceptions.Timeout:
                        self.log.emit(f"请求超时，尝试下一个端点")
                    except requests.exceptions.ConnectionError:
                        self.log.emit(f"连接错误，可能是网络问题或代理配置错误")
                    except Exception as e:
                        self.log.emit(f"请求过程中出错: {str(e)}")
                
                # 如果所有端点都失败，等待后重试
                wait_time = 10 * (attempt + 1)  # 逐渐增加等待时间
                self.log.emit(f"所有端点请求失败，等待{wait_time}秒后重试...")
                time.sleep(wait_time)
            
            self.log.emit("已达到最大重试次数，领取失败")
            return False
        except Exception as e:
            self.log.emit(f"领取过程中出现未处理异常: {str(e)}")
            return False
    
    def check_balance(self, pair):
        try:
            # 这里使用Web3检查余额
            w3 = Web3(Web3.HTTPProvider('https://rpc-testnet.autheo.com'))
            balance = w3.eth.get_balance(pair.address)
            balance_eth = w3.from_wei(balance, 'ether')
            pair.balance = balance_eth
            self.update_balance.emit(pair.address, balance_eth)
            self.log.emit(f'地址 {pair.address} 当前余额: {balance_eth} AUTH')
        except Exception as e:
            self.log.emit(f"获取余额失败: {str(e)}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.proxy_worker = None
        self.faucet_worker = None
        self.wallet_proxy_pairs = []
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_countdown)
        self.timer.start(1000)  # 每秒更新一次倒计时
        self.load_data()  # 加载保存的数据
        
    def initUI(self):
        self.setWindowTitle('Movement Testnet 水龙头')
        self.setGeometry(100, 100, 1000, 800)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Anti-captcha API设置
        api_layout = QHBoxLayout()
        api_label = QLabel('Anti-captcha API Key:')
        self.api_input = QLineEdit()
        self.api_input.setPlaceholderText('输入Anti-captcha API Key')
        api_layout.addWidget(api_label)
        api_layout.addWidget(self.api_input)
        layout.addLayout(api_layout)
        
        # 代理设置区域
        proxy_layout = QHBoxLayout()
        proxy_label = QLabel('代理列表:')
        self.proxy_input = QTextEdit()
        self.proxy_input.setPlaceholderText('输入代理地址列表，每行一个 (格式: http://username:password@host:port 或 socks5://username:password@host:port)')
        self.proxy_input.setMaximumHeight(100)
        proxy_layout.addWidget(proxy_label)
        proxy_layout.addWidget(self.proxy_input)
        layout.addLayout(proxy_layout)
        
        # 地址输入区域
        address_layout = QHBoxLayout()
        address_label = QLabel('钱包地址:')
        self.address_input = QTextEdit()
        self.address_input.setPlaceholderText('输入钱包地址列表，每行一个')
        self.address_input.setMaximumHeight(100)
        address_layout.addWidget(address_label)
        address_layout.addWidget(self.address_input)
        layout.addLayout(address_layout)
        
        # 钱包信息表格
        self.wallet_table = QTableWidget(0, 4)
        self.wallet_table.setHorizontalHeaderLabels(['钱包地址', '余额(AUTH)', '已领取次数', '下次可领取时间'])
        self.wallet_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.wallet_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.wallet_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.wallet_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        layout.addWidget(self.wallet_table)
        
        # 进度条
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton('开始领水')
        self.start_btn.clicked.connect(self.startFaucet)
        self.stop_btn = QPushButton('停止')
        self.stop_btn.clicked.connect(self.stopFaucet)
        self.stop_btn.setEnabled(False)
        self.save_btn = QPushButton('保存数据')
        self.save_btn.clicked.connect(self.save_data)
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(self.stop_btn)
        button_layout.addWidget(self.save_btn)
        layout.addLayout(button_layout)
        
        # 日志显示区域
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        layout.addWidget(self.log_display)
    
    def startFaucet(self):
        addresses = [addr.strip() for addr in self.address_input.toPlainText().strip().split('\n') if addr.strip()]
        proxies = [proxy.strip() for proxy in self.proxy_input.toPlainText().strip().split('\n') if proxy.strip()]
        api_key = self.api_input.text().strip()
        
        if not addresses:
            self.appendLog('请输入钱包地址')
            return
        
        if not proxies:
            self.appendLog('请输入代理地址')
            return
        
        if not api_key:
            self.appendLog('请输入Anti-captcha API Key')
            return
        
        if len(addresses) != len(proxies):
            self.appendLog('钱包地址数量与代理地址数量不匹配')
            return
        
        # 保留之前的领取记录
        old_pairs_dict = {pair.address: pair for pair in self.wallet_proxy_pairs}
        
        self.wallet_proxy_pairs = [
            WalletProxyPair(
                address=addr,
                proxy=self.format_proxy(proxy)
            ) for addr, proxy in zip(addresses, proxies)
        ]
        
        # 恢复之前的领取记录
        for pair in self.wallet_proxy_pairs:
            if pair.address in old_pairs_dict:
                pair.last_claim_times = old_pairs_dict[pair.address].last_claim_times
                pair.balance = old_pairs_dict[pair.address].balance
                pair.next_claim_time = old_pairs_dict[pair.address].next_claim_time
        
        # 更新表格
        self.update_wallet_table()
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        
        self.faucet_worker = FaucetWorker(self.wallet_proxy_pairs, api_key)
        self.faucet_worker.progress.connect(self.progress_bar.setValue)
        self.faucet_worker.log.connect(self.appendLog)
        self.faucet_worker.finished.connect(self.onFaucetFinished)
        self.faucet_worker.update_balance.connect(self.update_wallet_balance)
        self.faucet_worker.start()
    
    def update_wallet_balance(self, address, balance):
        for row in range(self.wallet_table.rowCount()):
            if self.wallet_table.item(row, 0).text() == address:
                self.wallet_table.setItem(row, 1, QTableWidgetItem(f"{balance:.6f}"))
                break
    
    def update_wallet_table(self):
        self.wallet_table.setRowCount(0)
        for pair in self.wallet_proxy_pairs:
            row_position = self.wallet_table.rowCount()
            self.wallet_table.insertRow(row_position)
            
            # 地址
            self.wallet_table.setItem(row_position, 0, QTableWidgetItem(pair.address))
            
            # 余额
            self.wallet_table.setItem(row_position, 1, QTableWidgetItem(f"{pair.balance:.6f}"))
            
            # 已领取次数
            claim_count = len(pair.last_claim_times)
            self.wallet_table.setItem(row_position, 2, QTableWidgetItem(str(claim_count)))
            
            # 下次可领取时间
            next_claim = pair.get_next_claim_time_str()
            self.wallet_table.setItem(row_position, 3, QTableWidgetItem(next_claim))
    
    def update_countdown(self):
        for row in range(self.wallet_table.rowCount()):
            address = self.wallet_table.item(row, 0).text()
            for pair in self.wallet_proxy_pairs:
                if pair.address == address:
                    next_claim = pair.get_next_claim_time_str()
                    self.wallet_table.setItem(row, 3, QTableWidgetItem(next_claim))
                    break
    
    def stopFaucet(self):
        if self.faucet_worker:
            self.faucet_worker.stop()
            self.appendLog('正在停止...')
    
    def onFaucetFinished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        self.appendLog('任务完成')
        self.save_data()  # 自动保存数据
    
    def appendLog(self, text):
        self.log_display.append(text)
        self.log_display.verticalScrollBar().setValue(
            self.log_display.verticalScrollBar().maximum()
        )

    def format_proxy(self, proxy_str):
        """格式化代理字符串为代理字典"""
        if proxy_str.startswith('socks5://'):
            return {
                'http': proxy_str,
                'https': proxy_str
            }
        else:
            return {
                'http': proxy_str,
                'https': proxy_str
            }
    
    def save_data(self):
        try:
            with open(DATA_FILE, 'wb') as f:
                data = {
                    'api_key': self.api_input.text(),
                    'proxies': self.proxy_input.toPlainText(),
                    'addresses': self.address_input.toPlainText(),
                    'wallet_proxy_pairs': self.wallet_proxy_pairs
                }
                pickle.dump(data, f)
            self.appendLog('数据已保存')
        except Exception as e:
            self.appendLog(f'保存数据失败: {str(e)}')
    
    def load_data(self):
        try:
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE, 'rb') as f:
                    data = pickle.load(f)
                    self.api_input.setText(data.get('api_key', ''))
                    self.proxy_input.setPlainText(data.get('proxies', ''))
                    self.address_input.setPlainText(data.get('addresses', ''))
                    self.wallet_proxy_pairs = data.get('wallet_proxy_pairs', [])
                    self.update_wallet_table()
                    self.appendLog('已加载保存的数据')
        except Exception as e:
            self.appendLog(f'加载数据失败: {str(e)}')
    
    def closeEvent(self, event: QCloseEvent):
        reply = QMessageBox.question(self, '确认', '是否保存数据后退出？',
                                   QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
        
        if reply == QMessageBox.Yes:
            self.save_data()
            event.accept()
        elif reply == QMessageBox.No:
            event.accept()
        else:
            event.ignore()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
