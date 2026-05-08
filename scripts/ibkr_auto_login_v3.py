#!/usr/bin/env python3
"""Auto-login IB Gateway v3 — clean restart + Tab navigation + screenshot verification."""
import os
import time
import subprocess
import sys
from pathlib import Path

DISPLAY = ':99'
GATEWAY_BIN = '/home/saengtawan/Jts/ibgateway'
CONFIG_PATH = '/home/saengtawan/ibc/config.ini'
LOG_FILE = '/home/saengtawan/ibc/logs/auto_login.log'


def log(m):
    Path(LOG_FILE).parent.mkdir(exist_ok=True)
    line = f"[{time.strftime('%H:%M:%S')}] {m}"
    print(line, flush=True)
    with open(LOG_FILE, 'a') as f: f.write(line + '\n')


def read_config():
    user = pw = None
    with open(CONFIG_PATH) as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if line.startswith('IbLoginId='):
                user = line.split('=', 1)[1].strip()
            elif line.startswith('IbPassword='):
                pw = line.split('=', 1)[1]  # don't strip — preserve exact
    return user, pw


def kill_all():
    log("Kill all old Gateway/Xvfb processes")
    subprocess.run(['pkill', '-9', '-f', 'ibgateway.GWClient'], capture_output=True)
    subprocess.run(['pkill', '-9', '-f', '/Jts/.install4j'], capture_output=True)
    subprocess.run(['pkill', '-9', '-f', f'Xvfb {DISPLAY}'], capture_output=True)
    time.sleep(3)


def is_port_open(port=4002):
    r = subprocess.run(['ss', '-tln'], capture_output=True, text=True)
    return f':{port} ' in r.stdout


def screenshot(tag):
    os.environ['DISPLAY'] = DISPLAY
    from Xlib import display, X
    from PIL import Image
    d = display.Display()
    root = d.screen().root
    g = root.get_geometry()
    raw = root.get_image(0,0,g.width,g.height,X.ZPixmap,0xffffffff)
    img = Image.frombytes('RGB', (g.width, g.height), raw.data, 'raw', 'BGRX')
    p = f'/tmp/ibkr_{tag}.png'
    img.save(p)
    log(f"📸 {p}")
    d.close()
    return p


def main():
    user, pw = read_config()
    if not user or not pw or pw == 'demouser':
        log("ERROR: real credentials not in config"); sys.exit(1)
    log(f"User: {user}  PW len: {len(pw)}")

    kill_all()

    log(f"Start Xvfb on {DISPLAY}")
    subprocess.Popen(['Xvfb', DISPLAY, '-screen', '0', '1280x800x24'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)

    log("Launch Gateway")
    env = os.environ.copy(); env['DISPLAY'] = DISPLAY
    subprocess.Popen([GATEWAY_BIN], env=env,
                     stdout=open('/tmp/gw_out.log','w'),
                     stderr=open('/tmp/gw_err.log','w'),
                     start_new_session=True)

    log("Wait 60s for Gateway login dialog to fully load")
    time.sleep(60)

    # Take screenshot to verify dialog is showing
    screenshot('before_login')

    os.environ['DISPLAY'] = DISPLAY
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.3

    # Set up clipboard helper
    def clip(text):
        proc = subprocess.Popen(['xclip', '-selection', 'clipboard'],
                                stdin=subprocess.PIPE,
                                env={'DISPLAY': DISPLAY, 'PATH': os.environ.get('PATH','/usr/bin:/bin')})
        proc.communicate(input=text.encode())

    log("Strategy: assume username field has initial focus, use Tab to nav")

    # Username field should be focused on Gateway open
    # Clear any existing text first
    pyautogui.hotkey('ctrl', 'a'); time.sleep(0.3)
    pyautogui.press('delete'); time.sleep(0.3)

    log(f"Paste username: {user}")
    clip(user)
    time.sleep(0.5)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.7)

    log("Tab to password field")
    pyautogui.press('tab')
    time.sleep(0.5)
    pyautogui.hotkey('ctrl', 'a'); time.sleep(0.3)
    pyautogui.press('delete'); time.sleep(0.3)

    log(f"Paste password (len={len(pw)})")
    clip(pw)
    time.sleep(0.5)
    pyautogui.hotkey('ctrl', 'v')
    time.sleep(0.7)

    screenshot('after_paste')

    log("Press Enter to submit")
    pyautogui.press('enter')

    log("Watch for port 4002 (max 150s)")
    for i in range(75):
        if is_port_open(4002):
            log(f"✅ Port 4002 OPEN after {(i+1)*2}s")
            screenshot('success')
            return 0
        time.sleep(2)
        if i in (5, 15, 30, 45, 60):
            screenshot(f'wait_{(i+1)*2}s')

    log("❌ Port 4002 did NOT open within 150s")
    screenshot('final_fail')
    return 2


if __name__ == '__main__':
    sys.exit(main())
