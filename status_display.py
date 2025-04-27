#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont, ImageOps
import subprocess
import datetime
import epd2in13_V2
from pisugar2py import PiSugar2
import logging
import socket
import requests
import re

LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# === Configurações ===
LOW_BATTERY_THRESHOLD = 20
USER_PATH = '/home/secrets/pihole_user'
PW_PATH = '/home/secrets/pihole_pw'

# === Funções auxiliares ===
def read_user_from_file():
    try:
        with open(USER_PATH, 'r') as file:
            user = file.read().strip()
            return user
    except Exception as e:
        print(f"Error loading user: {e}")
        return None

def read_password_from_file():
    try:
        with open(PW_PATH, 'r') as file:
            password = file.read().strip()
            return password
    except Exception as e:
        print(f"Error loading password: {e}")
        return None

# === PiSugar2 ===
def get_battery():
    try:
        LOG.debug("Initializing PiSugar2...")
        ps = PiSugar2()
        LOG.debug("Getting battery level...")
        battery_percentage = ps.get_battery_percentage()
        LOG.debug("Battery: " + str(int(battery_percentage.value)) + " %")
        LOG.debug("Syncing RTC...")
        ps.set_pi_from_rtc()
        return int(battery_percentage.value)
    except Exception as e:
        LOG.error(f"Error getting battery status: {e}")
        return "N/A"

# === PiHole ===    
def authenticate(ip, password):
    url = f"http://{ip}/api/auth"
    payload = {"password": password}
    headers = {"Content-Type": "application/json"}

    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()
    data = response.json()

    valid = data.get("session").get("valid")

    if not valid:
        raise Exception("Error authenticating, session is not valid")

    return data.get("session").get("sid")

def logout(ip, sid):
    url = f"http://{ip}/api/auth"
    headers = {"sid": sid}

    try:
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
    except Exception as e:
        LOG.error(f"Error logging out: {e}")

def get_blocked_percentage(ip, password):
    try:
        sid = authenticate(ip, password)
    except Exception as e:
        LOG.error(f"Error authenticating: {e}")
        return "N/A"

    url = f"http://{ip}/api/stats/summary"
    headers = {"sid": sid}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        logout(ip, sid)
        summary = response.json()

        battery_percentage = summary["queries"].get("percent_blocked", 0.0)
        return float("{:.2f}".format(battery_percentage))
    except Exception as e:
        print(f"Error getting stats summary: {e}")
        return "N/A"
    
def get_status(ip, password):
    try:
        sid = authenticate(ip, password)
    except Exception as e:
        LOG.error(f"Error authenticating: {e}")
        return "N/A"
    
    url = f"http://{ip}/api/dns/blocking"
    headers = {"sid": sid}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        logout(ip, sid)
        dns_blocking = response.json()

        return dns_blocking.get("blocking")
    except Exception as e:
        print(f"Error getting DNS blocking status: {e}")
        return "N/A"

# === System ===
def get_uptime():
    LOG.debug("Checking local uptime")
    with open("/proc/uptime", "r") as f:
        uptime_seconds = float(f.readline().split()[0])
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    
def get_cpu_temp():
    LOG.debug("Checking local CPU temperature")
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read()) / 1000, 1)
    except Exception as e:
        LOG.error(f"Error checking local CPU temperature: {e}")
        return "N/A"

# === Remote System ===
def get_remote_uptime(ip, user, password):
    LOG.debug("Checking remote uptime")
    try:
        command = "sshpass -p " + password + " ssh " + user + "@" + ip + " cat /proc/uptime"
        output = subprocess.getstatusoutput(command)
        LOG.debug(f"Remote Uptime: {output}")
        uptime_seconds = float(output[1].split()[0])
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    except Exception as e:
        LOG.error(f"Error reading remote uptime: {e}")
        return 0

def get_remote_cpu_temp(ip, user, password):
    LOG.debug("Checking remote CPU temperature")
    try:
        command = "sshpass -p " + password + " ssh " + user + "@" + ip + " cat /sys/class/thermal/thermal_zone0/temp"
        output = subprocess.getstatusoutput(command)
        LOG.debug(f"Remote CPU Temperature: {output}")
        return round(int(output[1]) / 1000, 1)
    except Exception as e:
        LOG.error(f"Error reading remote CPU temperature: {e}")
        return "N/A"

# === Main ===
def main():
    pihole1_ip = '192.168.50.135'
    pihole2_ip = '192.168.50.136'
    localhost = '127.0.0.1'

    password = read_password_from_file()
    user = read_user_from_file()

    epd = epd2in13_V2.EPD()
    epd.init(epd.FULL_UPDATE)
    width, height = epd.height, epd.width

    image = Image.new('1', (width, height), 255)
    draw = ImageDraw.Draw(image)

    # PiHole1
    pihole1_status = get_status(pihole1_ip, password)
    LOG.debug(f"Pi-hole 1 Status:  {pihole1_status}")
    pihole1_blocked_percentage = get_blocked_percentage(pihole1_ip, password)
    LOG.debug(f"Pi-hole 1 Blocked Ads: {pihole1_blocked_percentage}%")
    pihole1_uptime = get_remote_uptime(pihole1_ip, user, password)
    LOG.debug(f"Pi-hole 1 Uptime: {pihole1_uptime}")
    pihole1_cpu_temperature = get_remote_cpu_temp(pihole1_ip, user, password)
    LOG.debug(f"Pi-hole 1 CPU Temperature: {pihole1_cpu_temperature}")

    # PiHole2
    pihole2_status = get_status(localhost, password)
    LOG.debug(f"Pi-hole 2 Status:  {pihole2_status}")
    pihole2_blocked_percentage = get_blocked_percentage(localhost, password)
    LOG.debug(f"Pi-hole 2 Blocked Ads: {pihole2_blocked_percentage}%")
    pihole2_uptime = get_uptime()
    LOG.debug(f"Pi-hole 2 Uptime: {pihole2_uptime}")
    pihole2_temperature = get_cpu_temp()
    LOG.debug(f"Pi-hole 2 CPU Temperature: {pihole2_temperature}")

    # PiSugar2
    battery_percentage = get_battery()
    LOG.debug(f"Battery Status: {battery_percentage}")

    now_str = datetime.datetime.now().strftime("%d/%m %H:%M")

    global font_small, font_large, font_small_bold
    font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
    font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
    font_small_bold = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)
    #+---------------------------------+
    #| 192.168.50.135 | 192.168.50.136 |
    #| Active         | Active         |
    #| 10d 03:15:42   | 03d 12:48:21   |
    #| Blocked: 85%   | Blocked: 78%   |
    #| CPU: 55°C      | CPU: 50°C      |
    #|---------------------------------|
    #| [85%] 2025-04-27 12:34:56       |
    #+---------------------------------+
    # Desenhar as informações de Pi-hole 1
    draw.text((10, 6), f"{pihole1_ip}", font=font_small, fill=0)
    draw.text((10, 25), f"Status: {pihole1_status}", font=font_small, fill=0)
    draw.text((10, 44), f"Uptime: {pihole1_uptime}", font=font_small, fill=0)
    draw.text((10, 63), f"Blocked: {pihole1_blocked_percentage}%", font=font_small, fill=0)
    draw.text((10, 82), f"Temp: {pihole1_cpu_temperature}ºC", font=font_small, fill=0)

    # Desenhar as informações de Pi-hole 2
    draw.text((130, 6), f"{pihole2_ip}", font=font_small, fill=0)
    draw.text((130, 25), f"Status: {pihole2_status}", font=font_small, fill=0)
    draw.text((130, 44), f"Uptime: {pihole2_uptime}", font=font_small, fill=0)
    draw.text((130, 63), f"Blocked: {pihole2_blocked_percentage}%", font=font_small, fill=0)
    draw.text((130, 82), f"Temp: {pihole2_temperature}%", font=font_small, fill=0)

    # Rodapé com a percentagem de bateria e data/hora de atualização
    draw.text((10, 101), f"[{battery_percentage}%]", font=font_small, fill=0)
    draw.text((160, 101), f"{now_str}", font=font_small, fill=0)

    rotated_image = image.rotate(180)
    color_inverted_image = ImageOps.invert(rotated_image.convert("L")).convert("1")
    epd.display(epd.getbuffer(color_inverted_image))
    epd.sleep()

if __name__ == "__main__":
    main()
