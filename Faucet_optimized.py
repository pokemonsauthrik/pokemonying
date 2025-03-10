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
    from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException
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
    
    def __init__(self, wallet_proxy_pairs, anti_captcha_key=None):
        super().__init__()
        self.wallet_proxy_pairs = wallet_proxy_pairs
        self.anti_captcha_key = anti_captcha_key
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
    
    def solve_captcha_with_anticaptcha(self):
        """使用AntiCaptcha服务解决验证码"""
        if not self.anti_captcha_key:
            self.log.emit("未提供AntiCaptcha API密钥，无法自动解决验证码")
            return None
            
        solver = recaptchav2()
        solver.set_verbose(1)
        solver.set_key(self.anti_captcha_key)
        solver.set_website_url("https://testnet-faucet.autheo.com")
        solver.set_website_key("6LfOA04pAAAAAL9ttkwIz40hC63_7IsaU2MgcwVH")
        
        # 增加更多配置以提高成功率
        solver.set_soft_id(0)
        # 设置为不可见类型的reCAPTCHA
        solver.set_is_invisible(1)
        
        self.log.emit("开始使用AntiCaptcha解决验证码...")
        
        try:
            for attempt in range(3):
                self.log.emit(f"尝试解决验证码 (尝试 {attempt+1}/3)...")
                
                try:
                    response = solver.solve_and_return_solution()
                    
                    if response != 0:
                        self.log.emit(f"验证码解决成功! 响应长度: {len(response)}")
                        return response
                    else:
                        error_msg = solver.err_string if hasattr(solver, 'err_string') else "未知错误"
                        self.log.emit(f"验证码解决失败: {error_msg}")
                        time.sleep(5)  # 等待一段时间后重试
                except Exception as e:
                    self.log.emit(f'验证码解决出错: {str(e)}')
                    time.sleep(5)
            return None
        except Exception as e:
            self.log.emit(f'代理格式错误: {str(e)}')
            return None
    
    def on_proxy_check_finished(self, success):
        self.check_proxy_button.setEnabled(True)
        if success:
            self.log('代理验证成功，可以开始领取测试币')
        else:
            self.log('代理验证失败，请检查代理设置')
    
    def start_task(self):
        # 获取API密钥
        api_key = self.api_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, '警告', '请输入Anti-captcha API Key')
            return
        
        # 获取地址列表
        address_text = self.address_input.toPlainText().strip()
        if not address_text:
            QMessageBox.warning(self, '警告', '请输入至少一个钱包地址')
            return
            
        addresses = [addr.strip() for addr in address_text.split('\n') if addr.strip()]
        
        # 获取代理列表
        proxy_text = self.proxy_input.toPlainText().strip()
        proxies = []
        if proxy_text:
            proxy_lines = proxy_text.split('\n')
            for line in proxy_lines:
                if line.strip():
                    if line.startswith('http://') or line.startswith('https://') or line.startswith('socks5://'):
                        protocol = line.split('://')[0]
                        proxies.append({protocol: line.strip()})
                    else:
                        proxies.append({'http': line.strip(), 'https': line.strip()})
        
        # 如果代理数量少于地址数量，循环使用代理
        if proxies:
            while len(proxies) < len(addresses):
                proxies.extend(proxies[:len(addresses) - len(proxies)])
        else:
            # 如果没有代理，使用None
            proxies = [None] * len(addresses)
        
        # 创建钱包-代理对
        self.wallet_proxy_pairs = []
        for i, address in enumerate(addresses):
            pair = WalletProxyPair(address, proxies[i] if i < len(proxies) else None)
            self.wallet_proxy_pairs.append(pair)
        
        # 更新表格
        self.update_wallet_table()
        
        # 保存数据
        self.save_data()
        
        # 开始任务
        self.log('开始领取测试币...')
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.check_proxy_button.setEnabled(False)
        
        # 根据选择的模式创建不同的worker
        if self.automation_combo.currentIndex() == 0 and SELENIUM_AVAILABLE:
            self.log('使用Selenium浏览器自动化模式')
            self.faucet_worker = SeleniumFaucetWorker(self.wallet_proxy_pairs, api_key)
        else:
            self.log('使用API直接请求模式')
            self.faucet_worker = FaucetWorker(self.wallet_proxy_pairs, api_key)
        
        self.faucet_worker.progress.connect(self.progress_bar.setValue)
        self.faucet_worker.log.connect(self.log)
        self.faucet_worker.finished.connect(self.on_task_finished)
        self.faucet_worker.update_balance.connect(self.update_balance)
        self.faucet_worker.start()
    
    def stop_task(self):
        if self.faucet_worker and self.faucet_worker.isRunning():
            self.log('正在停止任务...')
            self.faucet_worker.stop()
            self.faucet_worker.wait()
            self.log('任务已停止')
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
    
    def on_task_finished(self):
        self.log('任务完成')
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
        self.save_data()
    
    def update_wallet_table(self):
        self.wallet_table.setRowCount(len(self.wallet_proxy_pairs))
        for i, pair in enumerate(self.wallet_proxy_pairs):
            # 地址
            address_item = QTableWidgetItem(pair.address)
            address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 0, address_item)
            
            # 余额
            balance_item = QTableWidgetItem(f"{pair.balance:.6f}")
            balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 1, balance_item)
            
            # 已领取次数
            claim_count_item = QTableWidgetItem(str(len(pair.last_claim_times)))
            claim_count_item.setFlags(claim_count_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 2, claim_count_item)
            
            # 下次可领取时间
            next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
            next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_countdown(self):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if i < self.wallet_table.rowCount():
                next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
                next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_balance(self, address, balance):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if pair.address == address:
                balance_item = QTableWidgetItem(f"{balance:.6f}")
                balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 1, balance_item)
                break
    
    def save_data(self):
        data = {
            'api_key': self.api_input.text(),
            'proxies': self.proxy_input.toPlainText(),
            'addresses': self.address_input.toPlainText(),
            'wallet_proxy_pairs': self.wallet_proxy_pairs
        }
        try:
            with open(DATA_FILE, 'wb') as f:
                pickle.dump(data, f)
            self.log('数据已保存')
        except Exception as e:
            self.log(f'保存数据失败: {str(e)}')
    
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'rb') as f:
                    data = pickle.load(f)
                
                if 'api_key' in data:
                    self.api_input.setText(data['api_key'])
                if 'proxies' in data:
                    self.proxy_input.setText(data['proxies'])
                if 'addresses' in data:
                    self.address_input.setText(data['addresses'])
                if 'wallet_proxy_pairs' in data:
                    self.wallet_proxy_pairs = data['wallet_proxy_pairs']
                    self.update_wallet_table()
                
                self.log('数据已加载')
            except Exception as e:
                self.log(f'加载数据失败: {str(e)}')
    
    def closeEvent(self, event: QCloseEvent):
        if self.faucet_worker and self.faucet_worker.isRunning():
            reply = QMessageBox.question(self, '确认', '任务正在运行，确定要退出吗？',
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.faucet_worker.stop()
                self.faucet_worker.wait()
                self.save_data()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_data()
            event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
                        error_msg = solver.err_string if hasattr(solver, 'err_string') else "未知错误"
                        self.log.emit(f"验证码解决失败: {error_msg}")
                        
                        if "ERROR_KEY_DOES_NOT_EXIST" in error_msg or "ERROR_ZERO_BALANCE" in error_msg:
                            self.log.emit("API密钥无效或余额不足，无法继续尝试")
                            return None
                        
                        time.sleep(5)
                except Exception as e:
                    self.log.emit(f"解决验证码过程中出错: {str(e)}")
                    time.sleep(5)
            
            self.log.emit("验证码解决失败，已达到最大重试次数")
            return None
        except Exception as e:
            self.log.emit(f"验证码解决出错: {str(e)}")
            return None
    
    def claim_with_selenium(self, pair):
        self.log.emit(f"使用浏览器自动化为地址 {pair.address} 领取测试币...")
        
        driver = None
        try:
            # 设置Chrome选项
            chrome_options = Options()
            chrome_options.add_argument("--window-size=1920,1080")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--disable-extensions")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--no-sandbox")
            
            # 在无头模式下，某些网站可能会检测并阻止，所以我们使用有头模式
            # chrome_options.add_argument("--headless")
            
            # 设置代理
            if pair.proxy:
                proxy_str = list(pair.proxy.values())[0]  # 获取代理字符串
                chrome_options.add_argument(f'--proxy-server={proxy_str}')
                self.log.emit(f"使用代理: {proxy_str}")
            
            # 初始化WebDriver
            self.log.emit("初始化Chrome浏览器...")
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            
            # 访问水龙头网站
            self.log.emit("正在访问水龙头网站...")
            driver.get("https://testnet-faucet.autheo.com")
            
            # 等待页面加载
            self.log.emit("等待页面加载...")
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "input"))
            )
            
            # 输入钱包地址
            self.log.emit("输入钱包地址...")
            address_input = driver.find_element(By.TAG_NAME, "input")
            address_input.clear()
            address_input.send_keys(pair.address)
            
            # 查找并点击请求按钮
            self.log.emit("查找请求按钮...")
            buttons = driver.find_elements(By.TAG_NAME, "button")
            claim_button = None
            
            for button in buttons:
                if "REQUEST" in button.text.upper() and "THEO" in button.text.upper():
                    claim_button = button
                    break
                    
            if not claim_button:
                self.log.emit("未找到请求按钮，尝试查找其他按钮...")
                for button in buttons:
                    if "REQUEST" in button.text.upper() or "CLAIM" in button.text.upper() or "GET" in button.text.upper():
                        claim_button = button
                        break
            
            if not claim_button:
                self.log.emit("未找到任何可用的请求按钮，领取失败")
                return False
            
            # 点击请求按钮
            self.log.emit("点击请求按钮...")
            claim_button.click()
            
            # 等待验证码出现
            self.log.emit("等待验证码加载...")
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src, 'recaptcha')]")
                )
                self.log.emit("检测到验证码")
                
                # 如果有AntiCaptcha API密钥，尝试自动解决验证码
                if self.anti_captcha_key:
                    captcha_response = self.solve_captcha_with_anticaptcha()
                    if captcha_response:
                        self.log.emit("尝试注入验证码响应...")
                        # 注入验证码响应
                        driver.execute_script(f"document.getElementById('g-recaptcha-response').innerHTML='{captcha_response}';")
                        
                        # 触发验证码回调
                        driver.execute_script("___grecaptcha_cfg.clients[0].L.L.callback('g-recaptcha-response');")
                        
                        # 等待结果
                        self.log.emit("等待领取结果...")
                        time.sleep(5)
                    else:
                        error_msg = solver.err_string if hasattr(solver, 'err_string') else "未知错误"
                        self.log.emit(f"验证码解决失败: {error_msg}")
                        time.sleep(5)  # 等待一段时间后重试
                        continue
        except Exception as e:
            self.log(f'代理格式错误: {str(e)}')
            self.check_proxy_button.setEnabled(True)
    
    def on_proxy_check_finished(self, success):
        self.check_proxy_button.setEnabled(True)
        if success:
            self.log('代理验证成功，可以开始领取测试币')
        else:
            self.log('代理验证失败，请检查代理设置')
    
    def start_task(self):
        # 获取API密钥
        api_key = self.api_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, '警告', '请输入Anti-captcha API Key')
            return
        
        # 获取地址列表
        address_text = self.address_input.toPlainText().strip()
        if not address_text:
            QMessageBox.warning(self, '警告', '请输入至少一个钱包地址')
            return
            
        addresses = [addr.strip() for addr in address_text.split('\n') if addr.strip()]
        
        # 获取代理列表
        proxy_text = self.proxy_input.toPlainText().strip()
        proxies = []
        if proxy_text:
            proxy_lines = proxy_text.split('\n')
            for line in proxy_lines:
                if line.strip():
                    if line.startswith('http://') or line.startswith('https://') or line.startswith('socks5://'):
                        protocol = line.split('://')[0]
                        proxies.append({protocol: line.strip()})
                    else:
                        proxies.append({'http': line.strip(), 'https': line.strip()})
        
        # 如果代理数量少于地址数量，循环使用代理
        if proxies:
            while len(proxies) < len(addresses):
                proxies.extend(proxies[:len(addresses) - len(proxies)])
        else:
            # 如果没有代理，使用None
            proxies = [None] * len(addresses)
        
        # 创建钱包-代理对
        self.wallet_proxy_pairs = []
        for i, address in enumerate(addresses):
            pair = WalletProxyPair(address, proxies[i] if i < len(proxies) else None)
            self.wallet_proxy_pairs.append(pair)
        
        # 更新表格
        self.update_wallet_table()
        
        # 保存数据
        self.save_data()
        
        # 开始任务
        self.log('开始领取测试币...')
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.check_proxy_button.setEnabled(False)
        
        # 根据选择的模式创建不同的worker
        if self.automation_combo.currentIndex() == 0 and SELENIUM_AVAILABLE:
            self.log('使用Selenium浏览器自动化模式')
            self.faucet_worker = SeleniumFaucetWorker(self.wallet_proxy_pairs, api_key)
        else:
            self.log('使用API直接请求模式')
            self.faucet_worker = FaucetWorker(self.wallet_proxy_pairs, api_key)
        
        self.faucet_worker.progress.connect(self.progress_bar.setValue)
        self.faucet_worker.log.connect(self.log)
        self.faucet_worker.finished.connect(self.on_task_finished)
        self.faucet_worker.update_balance.connect(self.update_balance)
        self.faucet_worker.start()
    
    def stop_task(self):
        if self.faucet_worker and self.faucet_worker.isRunning():
            self.log('正在停止任务...')
            self.faucet_worker.stop()
            self.faucet_worker.wait()
            self.log('任务已停止')
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
    
    def on_task_finished(self):
        self.log('任务完成')
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
        self.save_data()
    
    def update_wallet_table(self):
        self.wallet_table.setRowCount(len(self.wallet_proxy_pairs))
        for i, pair in enumerate(self.wallet_proxy_pairs):
            # 地址
            address_item = QTableWidgetItem(pair.address)
            address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 0, address_item)
            
            # 余额
            balance_item = QTableWidgetItem(f"{pair.balance:.6f}")
            balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 1, balance_item)
            
            # 已领取次数
            claim_count_item = QTableWidgetItem(str(len(pair.last_claim_times)))
            claim_count_item.setFlags(claim_count_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 2, claim_count_item)
            
            # 下次可领取时间
            next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
            next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_countdown(self):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if i < self.wallet_table.rowCount():
                next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
                next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_balance(self, address, balance):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if pair.address == address:
                balance_item = QTableWidgetItem(f"{balance:.6f}")
                balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 1, balance_item)
                break
    
    def save_data(self):
        data = {
            'api_key': self.api_input.text(),
            'proxies': self.proxy_input.toPlainText(),
            'addresses': self.address_input.toPlainText(),
            'wallet_proxy_pairs': self.wallet_proxy_pairs
        }
        try:
            with open(DATA_FILE, 'wb') as f:
                pickle.dump(data, f)
            self.log('数据已保存')
        except Exception as e:
            self.log(f'保存数据失败: {str(e)}')
    
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'rb') as f:
                    data = pickle.load(f)
                
                if 'api_key' in data:
                    self.api_input.setText(data['api_key'])
                if 'proxies' in data:
                    self.proxy_input.setText(data['proxies'])
                if 'addresses' in data:
                    self.address_input.setText(data['addresses'])
                if 'wallet_proxy_pairs' in data:
                    self.wallet_proxy_pairs = data['wallet_proxy_pairs']
                    self.update_wallet_table()
                
                self.log('数据已加载')
            except Exception as e:
                self.log(f'加载数据失败: {str(e)}')
    
    def closeEvent(self, event: QCloseEvent):
        if self.faucet_worker and self.faucet_worker.isRunning():
            reply = QMessageBox.question(self, '确认', '任务正在运行，确定要退出吗？',
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.faucet_worker.stop()
                self.faucet_worker.wait()
                self.save_data()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_data()
            event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
                        self.log.emit("自动解决验证码失败，请手动完成验证码")
                        # 给用户30秒时间手动完成验证码
                        time.sleep(30)
                else:
                proxy = {'http': first_proxy, 'https': first_proxy}
                self.log(f'正在验证代理: {first_proxy}')
                self.check_proxy_button.setEnabled(False)
                self.proxy_worker = ProxyCheckWorker(proxy)
                self.proxy_worker.log.connect(self.log)
                self.proxy_worker.finished.connect(self.on_proxy_check_finished)
                self.proxy_worker.start()
        except Exception as e:
            self.log(f'代理格式错误: {str(e)}')
            self.check_proxy_button.setEnabled(True)
    
    def on_proxy_check_finished(self, success):
        self.check_proxy_button.setEnabled(True)
        if success:
            self.log('代理验证成功，可以开始领取测试币')
        else:
            self.log('代理验证失败，请检查代理设置')
    
    def start_task(self):
        # 获取API密钥
        api_key = self.api_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, '警告', '请输入Anti-captcha API Key')
            return
        
        # 获取地址列表
        address_text = self.address_input.toPlainText().strip()
        if not address_text:
            QMessageBox.warning(self, '警告', '请输入至少一个钱包地址')
            return
            
        addresses = [addr.strip() for addr in address_text.split('\n') if addr.strip()]
        
        # 获取代理列表
        proxy_text = self.proxy_input.toPlainText().strip()
        proxies = []
        if proxy_text:
            proxy_lines = proxy_text.split('\n')
            for line in proxy_lines:
                if line.strip():
                    if line.startswith('http://') or line.startswith('https://') or line.startswith('socks5://'):
                        protocol = line.split('://')[0]
                        proxies.append({protocol: line.strip()})
                    else:
                        proxies.append({'http': line.strip(), 'https': line.strip()})
        
        # 如果代理数量少于地址数量，循环使用代理
        if proxies:
            while len(proxies) < len(addresses):
                proxies.extend(proxies[:len(addresses) - len(proxies)])
        else:
            # 如果没有代理，使用None
            proxies = [None] * len(addresses)
        
        # 创建钱包-代理对
        self.wallet_proxy_pairs = []
        for i, address in enumerate(addresses):
            pair = WalletProxyPair(address, proxies[i] if i < len(proxies) else None)
            self.wallet_proxy_pairs.append(pair)
        
        # 更新表格
        self.update_wallet_table()
        
        # 保存数据
        self.save_data()
        
        # 开始任务
        self.log('开始领取测试币...')
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.check_proxy_button.setEnabled(False)
        
        # 根据选择的模式创建不同的worker
        if self.automation_combo.currentIndex() == 0 and SELENIUM_AVAILABLE:
            self.log('使用Selenium浏览器自动化模式')
            self.faucet_worker = SeleniumFaucetWorker(self.wallet_proxy_pairs, api_key)
        else:
            self.log('使用API直接请求模式')
            self.faucet_worker = FaucetWorker(self.wallet_proxy_pairs, api_key)
        
        self.faucet_worker.progress.connect(self.progress_bar.setValue)
        self.faucet_worker.log.connect(self.log)
        self.faucet_worker.finished.connect(self.on_task_finished)
        self.faucet_worker.update_balance.connect(self.update_balance)
        self.faucet_worker.start()
    
    def stop_task(self):
        if self.faucet_worker and self.faucet_worker.isRunning():
            self.log('正在停止任务...')
            self.faucet_worker.stop()
            self.faucet_worker.wait()
            self.log('任务已停止')
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
    
    def on_task_finished(self):
        self.log('任务完成')
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
        self.save_data()
    
    def update_wallet_table(self):
        self.wallet_table.setRowCount(len(self.wallet_proxy_pairs))
        for i, pair in enumerate(self.wallet_proxy_pairs):
            # 地址
            address_item = QTableWidgetItem(pair.address)
            address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 0, address_item)
            
            # 余额
            balance_item = QTableWidgetItem(f"{pair.balance:.6f}")
            balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 1, balance_item)
            
            # 已领取次数
            claim_count_item = QTableWidgetItem(str(len(pair.last_claim_times)))
            claim_count_item.setFlags(claim_count_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 2, claim_count_item)
            
            # 下次可领取时间
            next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
            next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_countdown(self):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if i < self.wallet_table.rowCount():
                next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
                next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_balance(self, address, balance):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if pair.address == address:
                balance_item = QTableWidgetItem(f"{balance:.6f}")
                balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 1, balance_item)
                break
    
    def save_data(self):
        data = {
            'api_key': self.api_input.text(),
            'proxies': self.proxy_input.toPlainText(),
            'addresses': self.address_input.toPlainText(),
            'wallet_proxy_pairs': self.wallet_proxy_pairs
        }
        try:
            with open(DATA_FILE, 'wb') as f:
                pickle.dump(data, f)
            self.log('数据已保存')
        except Exception as e:
            self.log(f'保存数据失败: {str(e)}')
    
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'rb') as f:
                    data = pickle.load(f)
                
                if 'api_key' in data:
                    self.api_input.setText(data['api_key'])
                if 'proxies' in data:
                    self.proxy_input.setText(data['proxies'])
                if 'addresses' in data:
                    self.address_input.setText(data['addresses'])
                if 'wallet_proxy_pairs' in data:
                    self.wallet_proxy_pairs = data['wallet_proxy_pairs']
                    self.update_wallet_table()
                
                self.log('数据已加载')
            except Exception as e:
                self.log(f'加载数据失败: {str(e)}')
    
    def closeEvent(self, event: QCloseEvent):
        if self.faucet_worker and self.faucet_worker.isRunning():
            reply = QMessageBox.question(self, '确认', '任务正在运行，确定要退出吗？',
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.faucet_worker.stop()
                self.faucet_worker.wait()
                self.save_data()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_data()
            event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
                    self.log.emit("请手动完成验证码，等待30秒...")
                    # 给用户30秒时间手动完成验证码
                    time.sleep(30)
            except TimeoutException:
                self.log.emit("未检测到验证码，继续等待结果...")
            
            # 等待结果
            self.log.emit("等待领取结果...")
            time.sleep(5)
            
            # 检查结果
            page_source = driver.page_source.lower()
            if "success" in page_source or "transaction" in page_source or "hash" in page_source:
                self.log.emit("领取成功!")
                return True
            elif "rate limit" in page_source:
                self.log.emit("请求频率限制，请稍后再试")
            elif "captcha" in page_source:
                self.log.emit("验证码未正确完成")
            else:
                proxy = {'http': first_proxy, 'https': first_proxy}
                self.log(f'正在验证代理: {first_proxy}')
                self.check_proxy_button.setEnabled(False)
                self.proxy_worker = ProxyCheckWorker(proxy)
                self.proxy_worker.log.connect(self.log)
                self.proxy_worker.finished.connect(self.on_proxy_check_finished)
                self.proxy_worker.start()
        except Exception as e:
            self.log(f'代理格式错误: {str(e)}')
            self.check_proxy_button.setEnabled(True)
    
    def on_proxy_check_finished(self, success):
        self.check_proxy_button.setEnabled(True)
        if success:
            self.log('代理验证成功，可以开始领取测试币')
        else:
            self.log('代理验证失败，请检查代理设置')
    
    def start_task(self):
        # 获取API密钥
        api_key = self.api_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, '警告', '请输入Anti-captcha API Key')
            return
        
        # 获取地址列表
        address_text = self.address_input.toPlainText().strip()
        if not address_text:
            QMessageBox.warning(self, '警告', '请输入至少一个钱包地址')
            return
            
        addresses = [addr.strip() for addr in address_text.split('\n') if addr.strip()]
        
        # 获取代理列表
        proxy_text = self.proxy_input.toPlainText().strip()
        proxies = []
        if proxy_text:
            proxy_lines = proxy_text.split('\n')
            for line in proxy_lines:
                if line.strip():
                    if line.startswith('http://') or line.startswith('https://') or line.startswith('socks5://'):
                        protocol = line.split('://')[0]
                        proxies.append({protocol: line.strip()})
                    else:
                        proxies.append({'http': line.strip(), 'https': line.strip()})
        
        # 如果代理数量少于地址数量，循环使用代理
        if proxies:
            while len(proxies) < len(addresses):
                proxies.extend(proxies[:len(addresses) - len(proxies)])
        else:
            # 如果没有代理，使用None
            proxies = [None] * len(addresses)
        
        # 创建钱包-代理对
        self.wallet_proxy_pairs = []
        for i, address in enumerate(addresses):
            pair = WalletProxyPair(address, proxies[i] if i < len(proxies) else None)
            self.wallet_proxy_pairs.append(pair)
        
        # 更新表格
        self.update_wallet_table()
        
        # 保存数据
        self.save_data()
        
        # 开始任务
        self.log('开始领取测试币...')
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.check_proxy_button.setEnabled(False)
        
        # 根据选择的模式创建不同的worker
        if self.automation_combo.currentIndex() == 0 and SELENIUM_AVAILABLE:
            self.log('使用Selenium浏览器自动化模式')
            self.faucet_worker = SeleniumFaucetWorker(self.wallet_proxy_pairs, api_key)
        else:
            self.log('使用API直接请求模式')
            self.faucet_worker = FaucetWorker(self.wallet_proxy_pairs, api_key)
        
        self.faucet_worker.progress.connect(self.progress_bar.setValue)
        self.faucet_worker.log.connect(self.log)
        self.faucet_worker.finished.connect(self.on_task_finished)
        self.faucet_worker.update_balance.connect(self.update_balance)
        self.faucet_worker.start()
    
    def stop_task(self):
        if self.faucet_worker and self.faucet_worker.isRunning():
            self.log('正在停止任务...')
            self.faucet_worker.stop()
            self.faucet_worker.wait()
            self.log('任务已停止')
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
    
    def on_task_finished(self):
        self.log('任务完成')
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
        self.save_data()
    
    def update_wallet_table(self):
        self.wallet_table.setRowCount(len(self.wallet_proxy_pairs))
        for i, pair in enumerate(self.wallet_proxy_pairs):
            # 地址
            address_item = QTableWidgetItem(pair.address)
            address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 0, address_item)
            
            # 余额
            balance_item = QTableWidgetItem(f"{pair.balance:.6f}")
            balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 1, balance_item)
            
            # 已领取次数
            claim_count_item = QTableWidgetItem(str(len(pair.last_claim_times)))
            claim_count_item.setFlags(claim_count_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 2, claim_count_item)
            
            # 下次可领取时间
            next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
            next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_countdown(self):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if i < self.wallet_table.rowCount():
                next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
                next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_balance(self, address, balance):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if pair.address == address:
                balance_item = QTableWidgetItem(f"{balance:.6f}")
                balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 1, balance_item)
                break
    
    def save_data(self):
        data = {
            'api_key': self.api_input.text(),
            'proxies': self.proxy_input.toPlainText(),
            'addresses': self.address_input.toPlainText(),
            'wallet_proxy_pairs': self.wallet_proxy_pairs
        }
        try:
            with open(DATA_FILE, 'wb') as f:
                pickle.dump(data, f)
            self.log('数据已保存')
        except Exception as e:
            self.log(f'保存数据失败: {str(e)}')
    
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'rb') as f:
                    data = pickle.load(f)
                
                if 'api_key' in data:
                    self.api_input.setText(data['api_key'])
                if 'proxies' in data:
                    self.proxy_input.setText(data['proxies'])
                if 'addresses' in data:
                    self.address_input.setText(data['addresses'])
                if 'wallet_proxy_pairs' in data:
                    self.wallet_proxy_pairs = data['wallet_proxy_pairs']
                    self.update_wallet_table()
                
                self.log('数据已加载')
            except Exception as e:
                self.log(f'加载数据失败: {str(e)}')
    
    def closeEvent(self, event: QCloseEvent):
        if self.faucet_worker and self.faucet_worker.isRunning():
            reply = QMessageBox.question(self, '确认', '任务正在运行，确定要退出吗？',
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.faucet_worker.stop()
                self.faucet_worker.wait()
                self.save_data()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_data()
            event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
                self.log.emit(f"未知结果，可能失败: {driver.page_source[:200]}...")
            
            return False
        except Exception as e:
            self.log.emit(f"浏览器自动化出错: {str(e)}")
            if driver:
                try:
                    driver.quit()
                except:
                    pass
            return False
    
    def check_balance(self, pair):
        try:
            # 使用Web3检查余额
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
    
    def solve_captcha(self):
        solver = recaptchav2()
        solver.set_verbose(1)
        solver.set_key(self.anti_captcha_key)
        solver.set_website_url("https://testnet-faucet.autheo.com")
        solver.set_website_key("6LfOA04pAAAAAL9ttkwIz40hC63_7IsaU2MgcwVH")
        
        # 增加更多配置以提高成功率
        solver.set_soft_id(0)
        # 设置为不可见类型的reCAPTCHA
        solver.set_is_invisible(1)
        
        # 添加更详细的日志
        self.log.emit(f"开始解决验证码，使用API密钥: {self.anti_captcha_key[:5]}...{self.anti_captcha_key[-5:] if len(self.anti_captcha_key) > 10 else ''}")
        self.log.emit(f"目标网站: https://testnet-faucet.autheo.com, 验证码密钥: 6LfOA04pAAAAAL9ttkwIz40hC63_7IsaU2MgcwVH")
        
        try:
            # 增加重试次数和等待时间
            for attempt in range(5):  # 从3次增加到5次
                self.log.emit(f"尝试解决验证码 (尝试 {attempt+1}/5)...")
                
                # 检查API密钥是否为空
                if not self.anti_captcha_key or len(self.anti_captcha_key) < 10:
                    self.log.emit("错误: API密钥无效或为空")
                    return None
                
                # 尝试解决验证码
                try:
                    response = solver.solve_and_return_solution()
                    
                    # 检查响应
                    if response != 0:
                        self.log.emit(f"验证码解决成功! 响应长度: {len(response)}")
                        if len(response) < 10:
                            self.log.emit(f"警告: 响应长度异常短: {response}")
                        return response
                    else:
                        error_msg = solver.err_string if hasattr(solver, 'err_string') else "未知错误"
                        self.log.emit(f"验证码解决失败: {error_msg}")
                        time.sleep(5)  # 等待一段时间后重试
                        continue
        except Exception as e:
            self.log(f'代理格式错误: {str(e)}')
            self.check_proxy_button.setEnabled(True)
    
    def on_proxy_check_finished(self, success):
        self.check_proxy_button.setEnabled(True)
        if success:
            self.log('代理验证成功，可以开始领取测试币')
        else:
            self.log('代理验证失败，请检查代理设置')
    
    def start_task(self):
        # 获取API密钥
        api_key = self.api_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, '警告', '请输入Anti-captcha API Key')
            return
        
        # 获取地址列表
        address_text = self.address_input.toPlainText().strip()
        if not address_text:
            QMessageBox.warning(self, '警告', '请输入至少一个钱包地址')
            return
            
        addresses = [addr.strip() for addr in address_text.split('\n') if addr.strip()]
        
        # 获取代理列表
        proxy_text = self.proxy_input.toPlainText().strip()
        proxies = []
        if proxy_text:
            proxy_lines = proxy_text.split('\n')
            for line in proxy_lines:
                if line.strip():
                    if line.startswith('http://') or line.startswith('https://') or line.startswith('socks5://'):
                        protocol = line.split('://')[0]
                        proxies.append({protocol: line.strip()})
                    else:
                        proxies.append({'http': line.strip(), 'https': line.strip()})
        
        # 如果代理数量少于地址数量，循环使用代理
        if proxies:
            while len(proxies) < len(addresses):
                proxies.extend(proxies[:len(addresses) - len(proxies)])
        else:
            # 如果没有代理，使用None
            proxies = [None] * len(addresses)
        
        # 创建钱包-代理对
        self.wallet_proxy_pairs = []
        for i, address in enumerate(addresses):
            pair = WalletProxyPair(address, proxies[i] if i < len(proxies) else None)
            self.wallet_proxy_pairs.append(pair)
        
        # 更新表格
        self.update_wallet_table()
        
        # 保存数据
        self.save_data()
        
        # 开始任务
        self.log('开始领取测试币...')
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.check_proxy_button.setEnabled(False)
        
        # 根据选择的模式创建不同的worker
        if self.automation_combo.currentIndex() == 0 and SELENIUM_AVAILABLE:
            self.log('使用Selenium浏览器自动化模式')
            self.faucet_worker = SeleniumFaucetWorker(self.wallet_proxy_pairs, api_key)
        else:
            self.log('使用API直接请求模式')
            self.faucet_worker = FaucetWorker(self.wallet_proxy_pairs, api_key)
        
        self.faucet_worker.progress.connect(self.progress_bar.setValue)
        self.faucet_worker.log.connect(self.log)
        self.faucet_worker.finished.connect(self.on_task_finished)
        self.faucet_worker.update_balance.connect(self.update_balance)
        self.faucet_worker.start()
    
    def stop_task(self):
        if self.faucet_worker and self.faucet_worker.isRunning():
            self.log('正在停止任务...')
            self.faucet_worker.stop()
            self.faucet_worker.wait()
            self.log('任务已停止')
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
    
    def on_task_finished(self):
        self.log('任务完成')
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
        self.save_data()
    
    def update_wallet_table(self):
        self.wallet_table.setRowCount(len(self.wallet_proxy_pairs))
        for i, pair in enumerate(self.wallet_proxy_pairs):
            # 地址
            address_item = QTableWidgetItem(pair.address)
            address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 0, address_item)
            
            # 余额
            balance_item = QTableWidgetItem(f"{pair.balance:.6f}")
            balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 1, balance_item)
            
            # 已领取次数
            claim_count_item = QTableWidgetItem(str(len(pair.last_claim_times)))
            claim_count_item.setFlags(claim_count_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 2, claim_count_item)
            
            # 下次可领取时间
            next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
            next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_countdown(self):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if i < self.wallet_table.rowCount():
                next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
                next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_balance(self, address, balance):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if pair.address == address:
                balance_item = QTableWidgetItem(f"{balance:.6f}")
                balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 1, balance_item)
                break
    
    def save_data(self):
        data = {
            'api_key': self.api_input.text(),
            'proxies': self.proxy_input.toPlainText(),
            'addresses': self.address_input.toPlainText(),
            'wallet_proxy_pairs': self.wallet_proxy_pairs
        }
        try:
            with open(DATA_FILE, 'wb') as f:
                pickle.dump(data, f)
            self.log('数据已保存')
        except Exception as e:
            self.log(f'保存数据失败: {str(e)}')
    
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'rb') as f:
                    data = pickle.load(f)
                
                if 'api_key' in data:
                    self.api_input.setText(data['api_key'])
                if 'proxies' in data:
                    self.proxy_input.setText(data['proxies'])
                if 'addresses' in data:
                    self.address_input.setText(data['addresses'])
                if 'wallet_proxy_pairs' in data:
                    self.wallet_proxy_pairs = data['wallet_proxy_pairs']
                    self.update_wallet_table()
                
                self.log('数据已加载')
            except Exception as e:
                self.log(f'加载数据失败: {str(e)}')
    
    def closeEvent(self, event: QCloseEvent):
        if self.faucet_worker and self.faucet_worker.isRunning():
            reply = QMessageBox.question(self, '确认', '任务正在运行，确定要退出吗？',
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.faucet_worker.stop()
                self.faucet_worker.wait()
                self.save_data()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_data()
            event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
                        error_msg = solver.err_string if hasattr(solver, 'err_string') else "未知错误"
                        self.log.emit(f"验证码解决失败: {error_msg}")
                        
                        # 根据错误类型决定是否重试
                        if "ERROR_KEY_DOES_NOT_EXIST" in error_msg or "ERROR_ZERO_BALANCE" in error_msg:
                            self.log.emit("API密钥无效或余额不足，无法继续尝试")
                            return None
                        elif "ERROR_NO_SLOT_AVAILABLE" in error_msg:
                            wait_time = 10
                            self.log.emit(f"服务器繁忙，等待{wait_time}秒后重试...")
                            time.sleep(wait_time)
                        else:
                        error_msg = solver.err_string if hasattr(solver, 'err_string') else "未知错误"
                        self.log.emit(f"验证码解决失败: {error_msg}")
                        time.sleep(5)  # 等待一段时间后重试
                        continue
        except Exception as e:
            self.log(f'代理格式错误: {str(e)}')
            self.check_proxy_button.setEnabled(True)
    
    def on_proxy_check_finished(self, success):
        self.check_proxy_button.setEnabled(True)
        if success:
            self.log('代理验证成功，可以开始领取测试币')
        else:
            self.log('代理验证失败，请检查代理设置')
    
    def start_task(self):
        # 获取API密钥
        api_key = self.api_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, '警告', '请输入Anti-captcha API Key')
            return
        
        # 获取地址列表
        address_text = self.address_input.toPlainText().strip()
        if not address_text:
            QMessageBox.warning(self, '警告', '请输入至少一个钱包地址')
            return
            
        addresses = [addr.strip() for addr in address_text.split('\n') if addr.strip()]
        
        # 获取代理列表
        proxy_text = self.proxy_input.toPlainText().strip()
        proxies = []
        if proxy_text:
            proxy_lines = proxy_text.split('\n')
            for line in proxy_lines:
                if line.strip():
                    if line.startswith('http://') or line.startswith('https://') or line.startswith('socks5://'):
                        protocol = line.split('://')[0]
                        proxies.append({protocol: line.strip()})
                    else:
                        proxies.append({'http': line.strip(), 'https': line.strip()})
        
        # 如果代理数量少于地址数量，循环使用代理
        if proxies:
            while len(proxies) < len(addresses):
                proxies.extend(proxies[:len(addresses) - len(proxies)])
        else:
            # 如果没有代理，使用None
            proxies = [None] * len(addresses)
        
        # 创建钱包-代理对
        self.wallet_proxy_pairs = []
        for i, address in enumerate(addresses):
            pair = WalletProxyPair(address, proxies[i] if i < len(proxies) else None)
            self.wallet_proxy_pairs.append(pair)
        
        # 更新表格
        self.update_wallet_table()
        
        # 保存数据
        self.save_data()
        
        # 开始任务
        self.log('开始领取测试币...')
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.check_proxy_button.setEnabled(False)
        
        # 根据选择的模式创建不同的worker
        if self.automation_combo.currentIndex() == 0 and SELENIUM_AVAILABLE:
            self.log('使用Selenium浏览器自动化模式')
            self.faucet_worker = SeleniumFaucetWorker(self.wallet_proxy_pairs, api_key)
        else:
            self.log('使用API直接请求模式')
            self.faucet_worker = FaucetWorker(self.wallet_proxy_pairs, api_key)
        
        self.faucet_worker.progress.connect(self.progress_bar.setValue)
        self.faucet_worker.log.connect(self.log)
        self.faucet_worker.finished.connect(self.on_task_finished)
        self.faucet_worker.update_balance.connect(self.update_balance)
        self.faucet_worker.start()
    
    def stop_task(self):
        if self.faucet_worker and self.faucet_worker.isRunning():
            self.log('正在停止任务...')
            self.faucet_worker.stop()
            self.faucet_worker.wait()
            self.log('任务已停止')
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
    
    def on_task_finished(self):
        self.log('任务完成')
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
        self.save_data()
    
    def update_wallet_table(self):
        self.wallet_table.setRowCount(len(self.wallet_proxy_pairs))
        for i, pair in enumerate(self.wallet_proxy_pairs):
            # 地址
            address_item = QTableWidgetItem(pair.address)
            address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 0, address_item)
            
            # 余额
            balance_item = QTableWidgetItem(f"{pair.balance:.6f}")
            balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 1, balance_item)
            
            # 已领取次数
            claim_count_item = QTableWidgetItem(str(len(pair.last_claim_times)))
            claim_count_item.setFlags(claim_count_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 2, claim_count_item)
            
            # 下次可领取时间
            next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
            next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_countdown(self):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if i < self.wallet_table.rowCount():
                next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
                next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_balance(self, address, balance):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if pair.address == address:
                balance_item = QTableWidgetItem(f"{balance:.6f}")
                balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 1, balance_item)
                break
    
    def save_data(self):
        data = {
            'api_key': self.api_input.text(),
            'proxies': self.proxy_input.toPlainText(),
            'addresses': self.address_input.toPlainText(),
            'wallet_proxy_pairs': self.wallet_proxy_pairs
        }
        try:
            with open(DATA_FILE, 'wb') as f:
                pickle.dump(data, f)
            self.log('数据已保存')
        except Exception as e:
            self.log(f'保存数据失败: {str(e)}')
    
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'rb') as f:
                    data = pickle.load(f)
                
                if 'api_key' in data:
                    self.api_input.setText(data['api_key'])
                if 'proxies' in data:
                    self.proxy_input.setText(data['proxies'])
                if 'addresses' in data:
                    self.address_input.setText(data['addresses'])
                if 'wallet_proxy_pairs' in data:
                    self.wallet_proxy_pairs = data['wallet_proxy_pairs']
                    self.update_wallet_table()
                
                self.log('数据已加载')
            except Exception as e:
                self.log(f'加载数据失败: {str(e)}')
    
    def closeEvent(self, event: QCloseEvent):
        if self.faucet_worker and self.faucet_worker.isRunning():
            reply = QMessageBox.question(self, '确认', '任务正在运行，确定要退出吗？',
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.faucet_worker.stop()
                self.faucet_worker.wait()
                self.save_data()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_data()
            event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
                            wait_time = 5 * (attempt + 1)  # 逐渐增加等待时间
                            self.log.emit(f"等待{wait_time}秒后重试...")
                            time.sleep(wait_time)
                except Exception as inner_e:
                    self.log.emit(f"解决验证码过程中出错: {str(inner_e)}")
                    time.sleep(5)
            
            self.log.emit("验证码解决失败，已达到最大重试次数")
            return None
        except Exception as e:
            self.log.emit(f"验证码解决出错: {str(e)}")
            # 尝试获取更详细的错误信息
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
        # 由于API端点404错误，我们将使用Selenium浏览器自动化方法
        if SELENIUM_AVAILABLE:
            selenium_worker = SeleniumFaucetWorker([pair], self.anti_captcha_key)
            selenium_worker.log.connect(self.log.emit)
            return selenium_worker.claim_with_selenium(pair)
        else:
            self.log.emit("错误: Selenium未安装，无法使用浏览器自动化功能")
            self.log.emit("请安装Selenium: pip install selenium webdriver-manager")
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
        self.setWindowTitle('Movement Testnet 水龙头 (优化版)')
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
        
        # 日志区域
        log_label = QLabel('运行日志:')
        layout.addWidget(log_label)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        # 验证代理按钮
        self.check_proxy_button = QPushButton('验证代理')
        self.check_proxy_button.clicked.connect(self.check_proxy)
        button_layout.addWidget(self.check_proxy_button)
        
        # 自动化模式选择
        self.automation_combo = QComboBox()
        self.automation_combo.addItem("使用Selenium浏览器自动化 (推荐)")
        self.automation_combo.addItem("使用API直接请求 (不推荐)")
        button_layout.addWidget(self.automation_combo)
        
        # 开始按钮
        self.start_button = QPushButton('开始领取')
        self.start_button.clicked.connect(self.start_task)
        button_layout.addWidget(self.start_button)
        
        # 停止按钮
        self.stop_button = QPushButton('停止')
        self.stop_button.clicked.connect(self.stop_task)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        
        layout.addLayout(button_layout)
        
        # 状态栏
        self.statusBar().showMessage('就绪')
    
    def log(self, message):
        self.log_text.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")
        self.log_text.ensureCursorVisible()
    
    def check_proxy(self):
        proxy_text = self.proxy_input.toPlainText().strip()
        if not proxy_text:
            QMessageBox.warning(self, '警告', '请输入至少一个代理地址')
            return
            
        proxy_lines = proxy_text.split('\n')
        first_proxy = proxy_lines[0].strip()
        
        # 解析代理格式
        try:
            if first_proxy.startswith('http://') or first_proxy.startswith('https://') or first_proxy.startswith('socks5://'):
                protocol = first_proxy.split('://')[0]
                proxy = {protocol: first_proxy}
            else:
                proxy = {'http': first_proxy, 'https': first_proxy}
                self.log(f'正在验证代理: {first_proxy}')
                self.check_proxy_button.setEnabled(False)
                self.proxy_worker = ProxyCheckWorker(proxy)
                self.proxy_worker.log.connect(self.log)
                self.proxy_worker.finished.connect(self.on_proxy_check_finished)
                self.proxy_worker.start()
        except Exception as e:
            self.log(f'代理格式错误: {str(e)}')
            self.check_proxy_button.setEnabled(True)
    
    def on_proxy_check_finished(self, success):
        self.check_proxy_button.setEnabled(True)
        if success:
            self.log('代理验证成功，可以开始领取测试币')
        else:
            self.log('代理验证失败，请检查代理设置')
    
    def start_task(self):
        # 获取API密钥
        api_key = self.api_input.text().strip()
        if not api_key:
            QMessageBox.warning(self, '警告', '请输入Anti-captcha API Key')
            return
        
        # 获取地址列表
        address_text = self.address_input.toPlainText().strip()
        if not address_text:
            QMessageBox.warning(self, '警告', '请输入至少一个钱包地址')
            return
            
        addresses = [addr.strip() for addr in address_text.split('\n') if addr.strip()]
        
        # 获取代理列表
        proxy_text = self.proxy_input.toPlainText().strip()
        proxies = []
        if proxy_text:
            proxy_lines = proxy_text.split('\n')
            for line in proxy_lines:
                if line.strip():
                    if line.startswith('http://') or line.startswith('https://') or line.startswith('socks5://'):
                        protocol = line.split('://')[0]
                        proxies.append({protocol: line.strip()})
                    else:
                        proxies.append({'http': line.strip(), 'https': line.strip()})
        
        # 如果代理数量少于地址数量，循环使用代理
        if proxies:
            while len(proxies) < len(addresses):
                proxies.extend(proxies[:len(addresses) - len(proxies)])
        else:
            # 如果没有代理，使用None
            proxies = [None] * len(addresses)
        
        # 创建钱包-代理对
        self.wallet_proxy_pairs = []
        for i, address in enumerate(addresses):
            pair = WalletProxyPair(address, proxies[i] if i < len(proxies) else None)
            self.wallet_proxy_pairs.append(pair)
        
        # 更新表格
        self.update_wallet_table()
        
        # 保存数据
        self.save_data()
        
        # 开始任务
        self.log('开始领取测试币...')
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.check_proxy_button.setEnabled(False)
        
        # 根据选择的模式创建不同的worker
        if self.automation_combo.currentIndex() == 0 and SELENIUM_AVAILABLE:
            self.log('使用Selenium浏览器自动化模式')
            self.faucet_worker = SeleniumFaucetWorker(self.wallet_proxy_pairs, api_key)
        else:
            self.log('使用API直接请求模式')
            self.faucet_worker = FaucetWorker(self.wallet_proxy_pairs, api_key)
        
        self.faucet_worker.progress.connect(self.progress_bar.setValue)
        self.faucet_worker.log.connect(self.log)
        self.faucet_worker.finished.connect(self.on_task_finished)
        self.faucet_worker.update_balance.connect(self.update_balance)
        self.faucet_worker.start()
    
    def stop_task(self):
        if self.faucet_worker and self.faucet_worker.isRunning():
            self.log('正在停止任务...')
            self.faucet_worker.stop()
            self.faucet_worker.wait()
            self.log('任务已停止')
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
    
    def on_task_finished(self):
        self.log('任务完成')
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.check_proxy_button.setEnabled(True)
        self.save_data()
    
    def update_wallet_table(self):
        self.wallet_table.setRowCount(len(self.wallet_proxy_pairs))
        for i, pair in enumerate(self.wallet_proxy_pairs):
            # 地址
            address_item = QTableWidgetItem(pair.address)
            address_item.setFlags(address_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 0, address_item)
            
            # 余额
            balance_item = QTableWidgetItem(f"{pair.balance:.6f}")
            balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 1, balance_item)
            
            # 已领取次数
            claim_count_item = QTableWidgetItem(str(len(pair.last_claim_times)))
            claim_count_item.setFlags(claim_count_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 2, claim_count_item)
            
            # 下次可领取时间
            next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
            next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
            self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_countdown(self):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if i < self.wallet_table.rowCount():
                next_claim_item = QTableWidgetItem(pair.get_next_claim_time_str())
                next_claim_item.setFlags(next_claim_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 3, next_claim_item)
    
    def update_balance(self, address, balance):
        for i, pair in enumerate(self.wallet_proxy_pairs):
            if pair.address == address:
                balance_item = QTableWidgetItem(f"{balance:.6f}")
                balance_item.setFlags(balance_item.flags() & ~Qt.ItemIsEditable)
                self.wallet_table.setItem(i, 1, balance_item)
                break
    
    def save_data(self):
        data = {
            'api_key': self.api_input.text(),
            'proxies': self.proxy_input.toPlainText(),
            'addresses': self.address_input.toPlainText(),
            'wallet_proxy_pairs': self.wallet_proxy_pairs
        }
        try:
            with open(DATA_FILE, 'wb') as f:
                pickle.dump(data, f)
            self.log('数据已保存')
        except Exception as e:
            self.log(f'保存数据失败: {str(e)}')
    
    def load_data(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, 'rb') as f:
                    data = pickle.load(f)
                
                if 'api_key' in data:
                    self.api_input.setText(data['api_key'])
                if 'proxies' in data:
                    self.proxy_input.setText(data['proxies'])
                if 'addresses' in data:
                    self.address_input.setText(data['addresses'])
                if 'wallet_proxy_pairs' in data:
                    self.wallet_proxy_pairs = data['wallet_proxy_pairs']
                    self.update_wallet_table()
                
                self.log('数据已加载')
            except Exception as e:
                self.log(f'加载数据失败: {str(e)}')
    
    def closeEvent(self, event: QCloseEvent):
        if self.faucet_worker and self.faucet_worker.isRunning():
            reply = QMessageBox.question(self, '确认', '任务正在运行，确定要退出吗？',
                                      QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                self.faucet_worker.stop()
                self.faucet_worker.wait()
                self.save_data()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_data()
            event.accept()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()