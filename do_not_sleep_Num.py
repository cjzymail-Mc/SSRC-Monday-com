



# -------------------------------------------------------------------------
#2024更新： import模块（自动安装）  越来越复杂。。。不管了，能用就好
##import openai

import subprocess
import sys
import importlib.util

def install(package):

    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

packages = ["pyautogui"]   # 安装名称（例如：pip python-docx）★ ★ ★ ★ ★

modules = ["pyautogui"]           # 导入名称（例如：import docx）★ ★ ★ ★ ★ ★

for package, module in zip(packages, modules):
    is_installed = importlib.util.find_spec(module)
    if is_installed is None:
        print(f'开始安装{package}...\n')
        install(package)
        print(f'    {package}安装完成@！！\n')
        print(f'        尝试再次导入{module}\n')
        try:
            exec(f"import {module}")
            print(f'          {module}导入成功\n\n')
        except ImportError:
            print(f'{module}导入失败\n')
    else:
        print(f'{module}导入成功\n')
# -------------------------------------------------------------------------






import pyautogui
import time

pyautogui.FAILSAFE = False        # 关掉"鼠标到左上角就退出"的保护，防止误触崩溃

print("Don't Sleep!!!!!!!!!!!!!!!!!!（Num Lock 切换模式）")
print("按 Ctrl+C 停止")

while True:
    try:
        pyautogui.press('numlock')   # 按一下 Num Lock
        time.sleep(1)
        pyautogui.press('numlock')   # 再按一下还原
    except KeyboardInterrupt:
        print("\n已手动停止")
        break
    except Exception as e:
        # 任何底层 GUI/API 异常都不让程序退出，打印后继续
        print(f"[{time.strftime('%H:%M:%S')}] 忽略一次异常: {e!r}")
    time.sleep(55)               # 每 56 秒循环一次
