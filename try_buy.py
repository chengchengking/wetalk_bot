import os
import sys
import time
import re
import subprocess
import xml.etree.ElementTree as ET

ADB_PATH = r"D:\O+Connect\daemon\bin\adb.exe"
if not os.path.exists(ADB_PATH):
    ADB_PATH = "adb"

def run_adb(args):
    full_cmd = [ADB_PATH] + args
    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=10)
        return result.stdout.strip()
    except Exception as e:
        print(f"[ADB Error] {e}")
        return ""

def tap_coord(x, y):
    print(f"👉 点击坐标: ({x}, {y})")
    run_adb(["shell", "input", "tap", str(x), str(y)])
    time.sleep(2.0)

def dump_ui():
    run_adb(["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"])
    run_adb(["pull", "/sdcard/window_dump.xml", "temp_dump.xml"])
    if os.path.exists("temp_dump.xml"):
        try:
            tree = ET.parse("temp_dump.xml")
            root = tree.getroot()
            os.remove("temp_dump.xml")
            return root
        except Exception:
            pass
    return None

def parse_bounds(bounds_str):
    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
    if match:
        return list(map(int, match.groups()))
    return None

def get_center_coord(bounds_str):
    bounds = parse_bounds(bounds_str)
    if bounds:
        x1, y1, x2, y2 = bounds
        return (x1 + x2) // 2, (y1 + y2) // 2
    return None

def find_node_by_text_contains(node, text_to_find):
    text = node.get("text", "")
    if text_to_find in text:
        return node
    for child in node:
        res = find_node_by_text_contains(child, text_to_find)
        if res is not None:
            return res
    return None

def take_screenshot(name):
    print(f"📸 正在截屏并拉取: {name}...")
    run_adb(["shell", "screencap", "-p", f"/sdcard/{name}"])
    run_adb(["pull", f"/sdcard/{name}", name])

def main():
    print("=========================================================")
    print("🚀 WeTalk 租号与抢付极限测试脚本 (try_buy.py)")
    print("=========================================================")
    
    # 1. 切换到“电话号码”选项卡 (Tab 3: SIM卡图标)
    # 根据之前的 UI 布局，Tab 3 坐标位于 x=1008, y=3072 附近
    print("\nStep 1: 正在尝试切换到『电话号码』主菜单...")
    tap_coord(1008, 3072)
    take_screenshot("step1_tab3.png")
    
    # 2. Dump UI 并寻找“获取新的电话号码”按钮
    root = dump_ui()
    if root is None:
        print("错误: 无法获取 UI 树结构")
        return
        
    btn = find_node_by_text_contains(root, "获取新的电话号码")
    if btn is not None:
        center = get_center_coord(btn.get("bounds"))
        if center:
            print("🎉 找到『获取新的电话号码』按钮！")
            tap_coord(center[0], center[1])
    else:
        # 兜底点击：通常在页面中心的显著位置，我们点击 (720, 1600) 附近
        print("未在 UI 中找到文字，执行兜底点击『获取新的电话号码』区域...")
        tap_coord(720, 1600)
        
    time.sleep(3.0)
    take_screenshot("step2_get_number.png")
    
    # 3. 寻找国家/选择套餐
    print("\nStep 3: 尝试寻找并选择套餐...")
    root = dump_ui()
    if root is not None:
        # 尝试寻找“选择套餐”或 $5.00 套餐相关按钮
        pkg_btn = find_node_by_text_contains(root, "选择套餐")
        if pkg_btn is None:
            pkg_btn = find_node_by_text_contains(root, "套餐")
        if pkg_btn is None:
            pkg_btn = find_node_by_text_contains(root, "5.00")
            
        if pkg_btn is not None:
            center = get_center_coord(pkg_btn.get("bounds"))
            if center:
                print("🎉 找到套餐选择按钮！")
                tap_coord(center[0], center[1])
        else:
            print("未检测到套餐文本，执行常用套餐坐标兜底点击...")
            tap_coord(720, 2000)
            
    time.sleep(2.0)
    take_screenshot("step3_select_package.png")
    
    # 4. 尝试开通号码
    print("\nStep 4: 正在点击『开通号码』...")
    root = dump_ui()
    if root is not None:
        active_btn = find_node_by_text_contains(root, "开通号码")
        if active_btn is None:
            active_btn = find_node_by_text_contains(root, "开通")
            
        if active_btn is not None:
            center = get_center_coord(active_btn.get("bounds"))
            if center:
                tap_coord(center[0], center[1])
        else:
            print("未检测到开通按钮文本，执行开通动作坐标兜底点击...")
            tap_coord(720, 2800)
            
    time.sleep(3.0)
    take_screenshot("step4_activate_result.png")
    
    print("\n=========================================================")
    print("🏁 抢付购买测试已完成！请查看生成的图片以确认购买结果。")
    print("=========================================================")

if __name__ == "__main__":
    main()
