#!/usr/bin/env python3
import logging
import datetime
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import epd2in13_V2
from pisugar2py import PiSugar2

# === Logger ===
LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# === Paths and Limits ===
USER_PATH = '/home/secrets/pihole_user'
PW_PATH = '/home/secrets/pihole_pw'
LOW_BATTERY_THRESHOLD = 20

# === Aux funcs ===
def read_from_file(path):
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except Exception as e:
        LOG.error(f"Error loading file content: {e}")
        return None

def get_battery():
    try:
        LOG.debug("Initializing PiSugar2...")
        ps = PiSugar2()
        battery_percentage = ps.get_battery_percentage()
        ps.set_pi_from_rtc()
        return int(battery_percentage.value)
    except Exception as e:
        LOG.error(f"Error getting battery status: {e}")
        return "N/A"

# === PiHole funcs ===
def authenticate(ip, password):
    url = f"http://{ip}/api/auth"
    payload = {"password": password}
    try:
        response = requests.post(url, json=payload, timeout=5)
        data = response.json()
        if not data.get("session", {}).get("valid"):
            raise Exception("Session is not valid")
        return data.get("session", {}).get("sid")
    except Exception as e:
        LOG.error(f"Authentication failed for {ip}: {e}")
        return None

def logout(ip, sid):
    url = f"http://{ip}/api/auth"
    try:
        requests.delete(url, headers={"sid": sid}, timeout=5)
    except Exception as e:
        LOG.error(f"Logout failed for {ip}: {e}")

def get_pihole_data(ip, password):
    sid = authenticate(ip, password)
    if not sid:
        return "Error", 0.0
    try:
        status_url = f"http://{ip}/api/dns/blocking"
        response = requests.get(status_url, headers={"sid": sid}, timeout=5)
        status = response.json().get("blocking", "N/A")
        summary_url = f"http://{ip}/api/stats/summary"
        response = requests.get(summary_url, headers={"sid": sid}, timeout=5)
        blocked_percentage = response.json()["queries"].get("percent_blocked", 0.0)
        return status, float(f"{blocked_percentage:.2f}")
    except Exception as e:
        LOG.error(f"Error getting PiHole data from {ip}: {e}")
        return "N/A", 0.0
    finally:
        logout(ip, sid)

# === System ===
def get_local_uptime():
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    except Exception as e:
        LOG.error(f"Error reading local uptime: {e}")
        return "N/A"

def get_local_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read()) / 1000, 1)
    except Exception as e:
        LOG.error(f"Error reading local CPU temp: {e}")
        return "N/A"

def get_remote_uptime(ip, user, password):
    try:
        command = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {user}@{ip} cat /proc/uptime"
        output = subprocess.getoutput(command)
        uptime_seconds = float(output.split()[0])
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    except Exception as e:
        LOG.error(f"Error reading remote uptime: {e}")
        return "N/A"

def get_remote_cpu_temp(ip, user, password):
    try:
        command = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {user}@{ip} cat /sys/class/thermal/thermal_zone0/temp"
        output = subprocess.getoutput(command)
        return round(int(output.strip()) / 1000, 1)
    except Exception as e:
        LOG.error(f"Error reading remote CPU temp: {e}")
        return "N/A"

# === Main ===
def main():
    pihole1_ip = '192.168.50.135'
    pihole2_ip = '127.0.0.1'

    user = read_from_file(USER_PATH)
    password = read_from_file(PW_PATH)

    pihole1_status, pihole1_blocked = get_pihole_data(pihole1_ip, password)
    pihole2_status, pihole2_blocked = get_pihole_data(pihole2_ip, password)

    pihole1_uptime = get_remote_uptime(pihole1_ip, user, password)
    pihole1_temp = get_remote_cpu_temp(pihole1_ip, user, password)

    pihole2_uptime = get_local_uptime()
    pihole2_temp = get_local_cpu_temp()

    battery = get_battery()

    epd = epd2in13_V2.EPD()
    epd.init(epd.FULL_UPDATE)
    width, height = epd.height, epd.width

    image = Image.new('1', (width, height), 255)
    draw = ImageDraw.Draw(image)

    font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
    font_small_bold = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)

    now_str = datetime.datetime.now().strftime("%d/%m %H:%M")

    draw.text((1, 6), f"PiHole .135", font=font_small_bold, fill=0)
    draw.text((133, 6), f"PiHole .136", font=font_small_bold, fill=0)

    draw.text((1, 25), f"Status: {pihole1_status}", font=font_small, fill=0)
    draw.text((1, 44), f"Up: {pihole1_uptime}", font=font_small, fill=0)
    draw.text((1, 63), f"Blocked: {pihole1_blocked}%", font=font_small, fill=0)
    draw.text((1, 82), f"Temp: {pihole1_temp}°C", font=font_small, fill=0)

    draw.text((133, 25), f"Status: {pihole2_status}", font=font_small, fill=0)
    draw.text((133, 44), f"Up: {pihole2_uptime}", font=font_small, fill=0)
    draw.text((133, 63), f"Blocked: {pihole2_blocked}%", font=font_small, fill=0)
    draw.text((133, 82), f"Temp: {pihole2_temp}°C", font=font_small, fill=0)

    # Separator lines
    draw.line((123, 0, 123, 100), fill=0)  # Vertical separator
    draw.line((0, 101, width, 101), fill=0)   # Horizontal footer separator

    if isinstance(battery, int):
        battery_bar_length = int(50 * battery / 100)
        draw.rectangle((1, 107, 10 + battery_bar_length, 117), fill=0)
        draw.rectangle((1, 107, 60, 117), outline=0)
        draw.text((75, 105), f"{round(battery)}%", font=font_small, fill=0)
    else:
        draw.text((1, 105), "Battery: N/A", font=font_small, fill=0)

    draw.text((160, 105), now_str, font=font_small, fill=0)

    rotated_image = image.rotate(180)
    color_inverted_image = ImageOps.invert(rotated_image.convert("L")).convert("1")
    epd.display(epd.getbuffer(rotated_image))
    epd.sleep()

if __name__ == "__main__":
    main()
