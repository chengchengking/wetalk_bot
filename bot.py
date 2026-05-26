import os
import sys
import time
import json
import subprocess
import re
import xml.etree.ElementTree as ET
import traceback
from datetime import datetime

# 强制配置标准输出/错误流为 UTF-8 编码，防止在 Windows 非交互式终端下输出 Unicode 字符报错
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# ADB 路径配置（优先使用 O+Connect 内置路径）
ADB_PATH = r"D:\O+Connect\daemon\bin\adb.exe"
if not os.path.exists(ADB_PATH):
    ADB_PATH = "adb"

PACKAGE_NAME = "com.wetalkapp"
LAST_CHECKIN_FILE = "last_checkin.txt"
STATS_FILE = "stats.json"

# 允许的前台应用包名（在此之外的包名均视为意外跳转，自动发送返回键）
ALLOWED_PACKAGES = [
    "com.wetalkapp",
    "com.google.android.gms.ads",
    "com.google.android.gms",
    "com.android.webview",
    "com.android.permissioncontroller",
    "com.google.android.packageinstaller",
    "com.coloros.safecenter",
    "com.oppo.safe",
]


# 统计数据初始化
stats = {
    "start_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "checked_in": False,
    "video_attempts": 0,
    "video_successes": 0,
    "ad_closes": 0,
    "early_close_prevented": 0,
    "store_redirects_prevented": 0,
    "app_restarts": 0,
    "current_balance": "$0.0000"
}

def load_stats():
    global stats
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r") as f:
                stats = json.load(f)
        except Exception:
            pass

def save_stats():
    try:
        with open(STATS_FILE, "w") as f:
            json.dump(stats, f, indent=4)
    except Exception:
        pass

def log(msg):
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_msg = f"[{current_time}] {msg}"
    print(formatted_msg)
    try:
        with open("bot.log", "a", encoding="utf-8") as f:
            f.write(formatted_msg + "\n")
    except Exception:
        pass

def print_dashboard():
    """打印运行统计仪表盘"""
    try:
        # 仅在交互式终端清除屏幕，避免后台运行日志乱码
        if sys.stdout.isatty():
            os.system("cls" if os.name == "nt" else "clear")
        else:
            print("\n" + "="*60 + " DASHBOARD " + "="*60)
            
        print("=================================================================")
        print("        🤖 WeTalk (微通话) 高耐久自动挂机助手 (V2.2 生产版)      ")
        print("=================================================================")
        print(f" 启动时间  : {stats['start_time']}")
        try:
            uptime = datetime.now().replace(microsecond=0) - datetime.strptime(stats['start_time'], '%Y-%m-%d %H:%M:%S')
        except Exception:
            uptime = "未知"
        print(f" 运行累计  : {uptime}")
        print(f" 当前余额  : {stats['current_balance']}")
        print(f" 今日签到  : {'[已完成]' if stats['checked_in'] else '[未完成]'}")
        print("-----------------------------------------------------------------")
        print(f" 视频请求次数 : {stats['video_attempts']} 次")
        print(f" 视频成功奖励 : {stats['video_successes']} 次")
        print(f" 自动关闭广告 : {stats['ad_closes']} 次")
        print(f" 规避早关弹窗 : {stats['early_close_prevented']} 次")
        print(f" 阻止应用跳转 : {stats['store_redirects_prevented']} 次")
        print(f" 重启APP次数  : {stats['app_restarts']} 次")
        print("=================================================================")
        print(" 提示: 按 [Ctrl + C] 可安全退出挂机脚本")
        print("=================================================================")
        print()
    except Exception as e:
        # 备用极简打印，确保绝不报错中断
        print(f"[Dashboard] 余额: {stats['current_balance']}, 视频请求: {stats['video_attempts']}, 成功奖励: {stats['video_successes']}")

def run_adb(args, timeout=10):
    """运行 ADB 命令并返回输出（带超时防护和自愈功能）"""
    full_cmd = [ADB_PATH] + args
    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore', timeout=timeout)
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log(f"ADB 命令超时: {args}")
        if "uiautomator" in args:
            log("正在清理手机上的 uiautomator 卡死进程...")
            subprocess.run([ADB_PATH, "shell", "pkill", "uiautomator"], capture_output=True)
            subprocess.run([ADB_PATH, "shell", "pkill", "-f", "uiautomator"], capture_output=True)
        return ""
    except Exception as e:
        log(f"执行 ADB 命令 {args} 异常: {e}")
        return ""

def get_connected_device():
    """获取连接的 ADB 设备"""
    output = run_adb(["devices"])
    lines = output.split("\n")[1:]
    devices = []
    for line in lines:
        if line.strip():
            parts = line.split()
            if len(parts) >= 2 and parts[1] == "device":
                devices.append(parts[0])
    return devices[0] if devices else None

def get_current_activity():
    """获取当前前台运行的 Activity 和包名"""
    output = run_adb(["shell", "dumpsys", "window"])
    for line in output.splitlines():
        if "mCurrentFocus" in line:
            match = re.search(r'([\w\.]+)/([\w\.]+)', line)
            if match:
                return match.group(1), match.group(2)
    return "", ""

def dump_ui():
    """Dump 手机 UI 结构并解析为 XML Root"""
    # 导出到手机本地
    run_adb(["shell", "uiautomator", "dump", "/sdcard/window_dump.xml"])
    # 拉取到电脑本地
    local_path = "temp_dump.xml"
    run_adb(["pull", "/sdcard/window_dump.xml", local_path])
    
    if os.path.exists(local_path):
        try:
            tree = ET.parse(local_path)
            root = tree.getroot()
            os.remove(local_path)
            return root
        except Exception as e:
            # 针对偶发的 ADB 获取 UI 冲突，清除缓存并等待重试
            if os.path.exists(local_path):
                os.remove(local_path)
    return None

def parse_bounds(bounds_str):
    """解析 bounds 属性为坐标 [x1, y1, x2, y2]"""
    match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
    if match:
        return list(map(int, match.groups()))
    return None

def get_center_coord(bounds_str):
    """获取 bounds 的中心坐标 (x, y)"""
    bounds = parse_bounds(bounds_str)
    if bounds:
        x1, y1, x2, y2 = bounds
        return (x1 + x2) // 2, (y1 + y2) // 2
    return None

def find_node_by_text(node, text):
    """根据 text 查找节点"""
    if node.get("text") == text:
        return node
    for child in node:
        res = find_node_by_text(child, text)
        if res is not None:
            return res
    return None

def find_node_by_text_contains(node, text_to_find):
    """根据 text 子串查找节点"""
    text = node.get("text", "")
    if text_to_find in text:
        return node
    for child in node:
        res = find_node_by_text_contains(child, text_to_find)
        if res is not None:
            return res
    return None


def find_node_by_id(node, resource_id):
    """根据 resource-id 查找节点"""
    if node.get("resource-id") == resource_id:
        return node
    for child in node:
        res = find_node_by_id(child, resource_id)
        if res is not None:
            return res
    return None

def find_close_button(node):
    """在 XML 中智能寻找广告关闭/跳过按钮"""
    text = node.get("text", "")
    desc = node.get("content-desc", "")
    cls = node.get("class", "")
    clickable = node.get("clickable", "")
    
    # 智能关键词匹配
    keywords = ["close", "Close", "关闭", "跳过", "Skip", "skip", "Awesome", "确定", "确定并关闭"]
    is_match = False
    for kw in keywords:
        if kw in text or kw in desc:
            is_match = True
            break
            
    # 特殊的关闭图标匹配
    if text.strip().lower() == "x" or desc.strip().lower() == "x":
        is_match = True
        
    if is_match and clickable == "true" and node.get("bounds"):
        return node
        
    if is_match and (cls == "android.widget.Button" or "Button" in cls) and node.get("bounds"):
        return node

    for child in node:
        res = find_close_button(child)
        if res is not None:
            return res
            
    return None

def tap_coord(x, y):
    """点击指定坐标"""
    run_adb(["shell", "input", "tap", str(x), str(y)])

def press_back():
    """发送返回键"""
    run_adb(["shell", "input", "keyevent", "4"])

def launch_app():
    """启动 WeTalk 应用"""
    stats["app_restarts"] += 1
    save_stats()
    run_adb(["shell", "monkey", "-p", PACKAGE_NAME, "-c", "android.intent.category.LAUNCHER", "1"])
    # 强制等待 15 秒，确保 WeTalk 冷启动和 Splash 加载完成，避免被误判反复杀死重启
    time.sleep(15.0)

def active_recovery():
    """自动化硬重启与 IP/网络重置主动避让机制"""
    log("=================================================================")
    log("🚀 [主动防护] 检测到灰色按钮！拒绝坐以待毙，启动主动避让与自愈机制...")
    log("=================================================================")
    
    # 1. 强杀 WeTalk 进程，清除可能死锁的本地广告缓存
    log("Step 1: 正在强杀 WeTalk 应用以清除本地 Ad SDK 缓存...")
    run_adb(["shell", "am", "force-stop", PACKAGE_NAME])
    time.sleep(1.5)
    
    # 2. 闪断网络重置 IP（尝试通过飞行模式切换来获取运营商新 IP）
    log("Step 2: 正在闪断网络（重置 IP 地址和 Ad SDK 会话）...")
    # 尝试开启飞行模式
    run_adb(["shell", "cmd", "connectivity", "airplane-mode", "enable"])
    time.sleep(2.0)
    # 关闭飞行模式恢复网络
    run_adb(["shell", "cmd", "connectivity", "airplane-mode", "disable"])
    
    log("正在等待手机网络自动连接与恢复 (10秒)...")
    time.sleep(10.0)
    
    # 3. 重新拉起应用
    log("Step 3: 正在重新拉起 WeTalk 客户端并进入个人中心...")
    stats["app_restarts"] += 1
    save_stats()
    run_adb(["shell", "monkey", "-p", PACKAGE_NAME, "-c", "android.intent.category.LAUNCHER", "1"])
    # 强制等待 15 秒，确保 WeTalk 冷启动和 Splash 加载完成，避免被误判反复杀死重启
    time.sleep(15.0)

def check_if_already_checked_in():
    """检查今天是否已经签到过"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(LAST_CHECKIN_FILE):
        with open(LAST_CHECKIN_FILE, "r") as f:
            last_date = f.read().strip()
            if last_date == today_str:
                stats["checked_in"] = True
                return True
    stats["checked_in"] = False
    return False

def mark_checked_in():
    """标记今日已完成签到"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    with open(LAST_CHECKIN_FILE, "w") as f:
        f.write(today_str)
    stats["checked_in"] = True
    save_stats()

def main():
    load_stats()
    
    # 1. 检测设备连接
    device = get_connected_device()
    if not device:
        print("错误: 未检测到任何已连接的 ADB 设备！请确保手机已通过投屏或 USB 连接并开启了“USB调试”。")
        sys.exit(1)
    
    consecutive_no_action = 0
    checkin_attempted = False
    loading_timeout = 0
    last_early_close_time = 0
    consecutive_clicks_no_ad = 0
    consecutive_recoveries = 0  # 新增：连续自愈重试次数
    waiting_for_reward = False  # 新增：是否正等待广告奖励弹窗
    
    while True:
        try:
            # 获取当前包名和活动名
            pkg, act = get_current_activity()
            
            # 2. 意外离开 WeTalk 且进入了系统桌面或设置页，强制拉回 APP
            is_launcher = pkg and ("launcher" in pkg or "home" in pkg or "settings" in pkg or "systemui" in pkg)
            if is_launcher or pkg == "":
                log("检测到处于系统桌面、设置或黑屏界面，正在强制拉回 WeTalk...")
                launch_app()
                continue

            # 3. 阻止系统或第三方应用商店、浏览器等广告意外跳转
            if pkg and pkg not in ALLOWED_PACKAGES:
                stats["store_redirects_prevented"] += 1
                save_stats()
                log(f"检测到广告意外跳转至 {pkg}，正在执行返回键以强制返回广告...")
                # 连续发送返回键回到广告播放
                press_back()
                time.sleep(0.5)
                press_back()
                time.sleep(1.0)
                continue
                
            # 4. 获取界面布局
            root = dump_ui()
            if root is None:
                time.sleep(2)
                continue
            
            # 5. 分析主界面与弹窗状态
            
            # A-0. 自动处理系统或应用的权限弹窗
            is_permission_pkg = pkg and ("permission" in pkg or "installer" in pkg or "safe" in pkg)
            if is_permission_pkg:
                log(f"检测到系统权限弹窗 (当前界面: {pkg})，尝试自动处理...")
                handled = False
                for btn_text in ["始终允许", "允许", "仅在使用中允许", "取消", "拒绝", "禁止"]:
                    btn_node = find_node_by_text(root, btn_text)
                    if btn_node is not None:
                        center = get_center_coord(btn_node.get("bounds"))
                        if center:
                            log(f"自动点击系统权限弹窗的【{btn_text}】按钮...")
                            tap_coord(center[0], center[1])
                            time.sleep(2.0)
                            handled = True
                            break
                if handled:
                    continue
                else:
                    log("未找到匹配的系统权限按钮，保持观察...")
                    time.sleep(2.0)
                    continue

            # A-0.2. 检查 WeTalk 内部权限申请或通知提示弹窗并自动取消
            permission_dlg = find_node_by_text(root, "请允许WeTalk获得通知权限")
            if permission_dlg is not None:
                cancel_btn = find_node_by_text(root, "取消")
                if cancel_btn is not None:
                    log("检测到 WeTalk 通知权限申请弹窗，自动点击【取消】以恢复挂机...")
                    center = get_center_coord(cancel_btn.get("bounds"))
                    if center:
                        tap_coord(center[0], center[1])
                        time.sleep(1.5)
                        continue

            # A. 检查奖励到账确认弹窗（“好的”弹窗）
            confirm_btn = find_node_by_id(root, "com.wetalkapp:id/confirm_btn")
            if confirm_btn is None:
                confirm_btn = find_node_by_text(root, "好的")
                
            if confirm_btn is not None:
                center = get_center_coord(confirm_btn.get("bounds"))
                if center:
                    tap_coord(center[0], center[1])
                    if waiting_for_reward:
                        stats["video_successes"] += 1
                        save_stats()
                        waiting_for_reward = False
                        log("🎉 成功结算：确认视频 ad 奖励弹窗！(video_successes +1)")
                    else:
                        log("🤖 点击清除 WeTalk 启动/其它弹窗（不计入视频奖励次数）")
                time.sleep(1.5)
                continue

            # B. 检查 WeTalk 的加载加载中 spinner (加载超时防护)
            load_spinner = find_node_by_id(root, "com.wetalkapp:id/load")
            if load_spinner is not None:
                consecutive_clicks_no_ad = 0  # 正在加载广告，说明点击已生效，重置计数
                loading_timeout += 1
                if loading_timeout >= 6:  # 加载超过 12-15 秒未响应
                    # 发送 Back 键取消加载，并强制冷却
                    press_back()
                    loading_timeout = 0
                    time.sleep(5.0)  # 冷却 5 秒
                else:
                    time.sleep(1.0)
                continue
            loading_timeout = 0  # 重置超时计数

            # C. 处于 WeTalk 个人中心主界面
            check_in_node = find_node_by_id(root, "com.wetalkapp:id/checkInDaily")
            watch_video_node = find_node_by_id(root, "com.wetalkapp:id/watchVideo")
            balance_node = find_node_by_id(root, "com.wetalkapp:id/balance")
            tab_layout_node = find_node_by_id(root, "com.wetalkapp:id/tabLayout")
            
            # 记录最新余额
            if balance_node is not None:
                stats["current_balance"] = balance_node.get("text", "$0.0000")
                save_stats()
            
            # 渲染仪表盘
            print_dashboard()

            # 自愈和状态防护：如果检测到主界面的 Tab 栏，但未处于个人中心（即签到与视频按钮均不可见）
            if tab_layout_node is not None and check_in_node is None and watch_video_node is None:
                log("检测到主界面 Tab 栏，但未处于个人中心，正在强制切换到个人中心...")
                # 强行切换到右下角个人中心 Tab
                tap_coord(1296, 3072)
                time.sleep(1.5)
                continue

            if check_in_node is not None or watch_video_node is not None:
                consecutive_no_action = 0
                
                # A-1. 每日签到逻辑
                if not check_if_already_checked_in() and not checkin_attempted and check_in_node is not None:
                    checkin_attempted = True
                    center = get_center_coord(check_in_node.get("bounds"))
                    if center:
                        log("检测到签到按钮，正在执行每日签到...")
                        tap_coord(center[0], center[1])
                        time.sleep(2.0)
                        continue
                
                # A-2. 循环看视频赚余额逻辑
                if watch_video_node is not None:
                    # 安全机制：如果连续点击了 2 次却没有成功拉起广告（即还在个人中心界面）
                    if consecutive_clicks_no_ad >= 2:
                        consecutive_clicks_no_ad = 0  # 恢复重试
                        if consecutive_recoveries >= 1:
                            log("⚠️ [防封避让] 网络闪断重启后，『观看视频』按钮依然不可用！")
                            log("可能已触发 WeTalk 每日上限、广告池枯竭或服务器端账号风控。")
                            log("为保护账号，脚本将进入 5 分钟 (300秒) 的静默观察期...")
                            for i in range(300, 0, -1):
                                if i % 30 == 0 or i <= 5:
                                    log(f"静默冷却中... 剩余 {i} 秒")
                                time.sleep(1.0)
                            consecutive_recoveries = 0  # 冷却结束后重置自愈次数
                        else:
                            active_recovery()
                            consecutive_recoveries += 1
                        continue
                        
                    stats["video_attempts"] += 1
                    save_stats()
                    center = get_center_coord(watch_video_node.get("bounds"))
                    if center:
                        log(f"正在第 {stats['video_attempts']} 次点击观看视频...")
                        tap_coord(center[0], center[1])
                        consecutive_clicks_no_ad += 1  # 增加尝试点击计数
                        waiting_for_reward = True  # 点击了视频，进入等待奖励结算状态
                        # 广告播放前留出时间载入
                        time.sleep(4.0)
                        continue
                        
            else:
                # D. 处于广告界面或广告结束弹窗中
                consecutive_clicks_no_ad = 0  # 成功进入广告或非主界面状态，重置点击计数
                consecutive_recoveries = 0     # 成功拉起广告，说明自愈或状态正常，重置自愈尝试次数
                
                # 检查防早关失去奖励的对话框
                lose_reward_dialog = find_node_by_text_contains(root, "关闭广告")
                if lose_reward_dialog is None:
                    lose_reward_dialog = find_node_by_text_contains(root, "失去奖励")
                if lose_reward_dialog is None:
                    lose_reward_dialog = find_node_by_text_contains(root, "无法获得奖励")
                    
                if lose_reward_dialog is not None:
                    stats["early_close_prevented"] += 1
                    save_stats()
                    log("检测到防早关警告弹窗，自动点击继续播放，并启动 22 秒静默播放冷却...")
                    last_early_close_time = time.time()  # 记录早关弹窗触发时间，开始冷却
                    continue_btn = find_node_by_text(root, "继续")
                    if continue_btn is None:
                        continue_btn = find_node_by_text_contains(root, "继续")
                    if continue_btn is not None:
                        center = get_center_coord(continue_btn.get("bounds"))
                        if center:
                            tap_coord(center[0], center[1])
                    else:
                        tap_coord(1112, 1800)
                    time.sleep(5.0)
                    continue
                
                # 检查是否处于点击关闭按钮的冷却时间内
                in_cooldown = (time.time() - last_early_close_time < 22)
                
                close_btn = None
                if not in_cooldown:
                    close_btn = find_close_button(root)
                else:
                    log("广告处于 22 秒静默播放冷却中，跳过寻找关闭按钮以防早关...")
                    consecutive_no_action = 0  # 冷却期间重置卡死计数，因为这是正常的广告播放时间
                
                # 检测到关闭按钮
                if close_btn is not None:
                    center = get_center_coord(close_btn.get("bounds"))
                    if center:
                        log("检测到广告关闭/跳过按钮，正在自动关闭广告...")
                        tap_coord(center[0], center[1])
                        stats["ad_closes"] += 1
                        save_stats()
                        
                        # 签到在关闭广告后被视为成功
                        if not check_if_already_checked_in():
                            mark_checked_in()
                        time.sleep(1.5)
                        continue
                
                # E. 兜底策略：广告正在加载或正在播放中
                if not in_cooldown:
                    consecutive_no_action += 1
                # 卡死防护：如果在广告界面或未知界面停留超过 70 秒没有任何可点击状态，则自动触发返回
                if consecutive_no_action >= 7:
                    log("界面无响应或广告播放超时，执行兜底返回操作...")
                    press_back()
                    time.sleep(1.0)
                    tap_coord(1344, 256)  # 点击右上角常用关闭坐标
                    consecutive_no_action = 0
                    time.sleep(1.5)
                else:
                    time.sleep(4.0)  # 每 4 秒轮询一次，极速响应关闭
                    
        except KeyboardInterrupt:
            print("\n挂机脚本已手动终止。统计数据已保存。")
            break
        except Exception as e:
            log(f"主循环捕获异常: {e}")
            log(traceback.format_exc())
            time.sleep(5)

if __name__ == "__main__":
    main()
