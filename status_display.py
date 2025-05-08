#!/usr/bin/env python3
import logging
import datetime
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import epd2in13_V2

# === Logger ===
LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# === Paths and Limits ===
USER_PATH = '/home/secrets/pihole_user'
PW_PATH = '/home/secrets/pihole_pw'
LOW_BATTERY_THRESHOLD = 20

# === Aux funcs ===
def readFromFile(path):
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except Exception as e:
        LOG.error(f"readFromFile - Error loading file content: {e}")
        return None

def getBattery():
    try:
        LOG.debug("getBattery - Getting battery info via netcat")
        command = 'echo "get battery" | nc -q 0 127.0.0.1 8423'
        output = subprocess.check_output(command, shell=True, text=True)
        for line in output.splitlines():
            if line.lower().startswith("battery:"):
                battery_value = float(line.split(":")[1].strip())
                LOG.debug(f"getBattery - Battery % is: {battery_value}")
                return int(round(battery_value))
        return "N/A"
    except Exception as e:
        LOG.error(f"getBattery - Error getting battery status via netcat: {e}")
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
        LOG.error(f"authenticate - Authentication failed for {ip}: {e}")
        return None

def logout(ip, sid):
    url = f"http://{ip}/api/auth"
    try:
        requests.delete(url, headers={"sid": sid}, timeout=5)
    except Exception as e:
        LOG.error(f"logout - Logout failed for {ip}: {e}")

def getPiHoleData(ip, password):
    sid = authenticate(ip, password)
    if not sid:
        return "N/A", 0.0
    try:
        summary_url = f"http://{ip}/api/stats/summary"
        response = requests.get(summary_url, headers={"sid": sid}, timeout=5)
        resquestsNumber = response.json()["queries"].get("total")
        blockedPercentage = response.json()["queries"].get("percent_blocked", 0.0)
        return resquestsNumber, float(f"{blockedPercentage:.2f}")
    except Exception as e:
        LOG.error(f"getPiHoleData - Error getting PiHole data from {ip}: {e}")
        return "N/A", 0.0
    finally:
        logout(ip, sid)

# === System ===
def getLocalUpTime():
    try:
        with open("/proc/uptime", "r") as f:
            uptimeSeconds = float(f.readline().split()[0])
            hours = int(uptimeSeconds // 3600)
            minutes = int((uptimeSeconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    except Exception as e:
        LOG.error(f"getLocalUpTime - Error reading local uptime: {e}")
        return "N/A"

def getLocalCPUTemp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read()) / 1000, 1)
    except Exception as e:
        LOG.error(f"getLocalCPUTemp - Error reading local CPU temp: {e}")
        return "N/A"

def getRemoteUpTime(ip, user, password):
    try:
        LOG.debug(f"getRemoteUpTime - Reading remote uptime on: {ip}")
        command = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {user}@{ip} cat /proc/uptime"
        output = subprocess.getoutput(command)
        uptimeSeconds = float(output.split()[0])
        hours = int(uptimeSeconds // 3600)
        minutes = int((uptimeSeconds % 3600) // 60)
        return f"{hours}h {minutes}m"
    except Exception as e:
        LOG.error(f"getRemoteUpTime - Error reading remote uptime: {e}")
        return "N/A"

def getRemoteCPUTemp(ip, user, password):
    try:
        LOG.debug(f"getRemoteCPUTemp - Reading remote CPU Temp on: {ip}")
        command = f"sshpass -p '{password}' ssh -o StrictHostKeyChecking=no {user}@{ip} cat /sys/class/thermal/thermal_zone0/temp"
        output = subprocess.getoutput(command)
        return round(int(output.strip()) / 1000, 1)
    except Exception as e:
        LOG.error(f"getRemoteCPUTemp - Error reading remote CPU temp: {e}")
        return "N/A"

# === Main ===
def main():
    LOG.debug("main - Starting execution")
    pihole1Ip = '192.168.50.135'
    pihole2Ip = '127.0.0.1'

    user = readFromFile(USER_PATH)
    password = readFromFile(PW_PATH)

    pihole1RequestsNumber, pihole1Blocked = getPiHoleData(pihole1Ip, password)
    pihole2RequestsNumber, pihole2Blocked = getPiHoleData(pihole2Ip, password)

    pihole1UpTime = getRemoteUpTime(pihole1Ip, user, password)
    pihole1Temp = getRemoteCPUTemp(pihole1Ip, user, password)

    pihole2UpTime = getLocalUpTime()
    pihole2Temp = getLocalCPUTemp()

    battery = getBattery()

    now_str = datetime.datetime.now().strftime("%d/%m %H:%M")

    epd = epd2in13_V2.EPD()
    epd.init(epd.PART_UPDATE)
    width, height = epd.height, epd.width
    image = Image.new('1', (width, height), 255)
    draw = ImageDraw.Draw(image)

    fontSmall = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
    fontSmallBold = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)
    fontBigBold = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 16)

    draw.text((10, 4), "PiHole .135", font=fontBigBold, fill=0)
    draw.text((135, 4), "PiHole .136", font=fontBigBold, fill=0)

    draw.text((10, 25), "REQ:", font=fontSmallBold, fill=0)
    draw.text((50, 25), f"{pihole1RequestsNumber}", font=fontSmall, fill=0)
    draw.text((10, 44), "BLKD:", font=fontSmallBold, fill=0)
    draw.text((60, 44), f"{pihole1Blocked}%", font=fontSmall, fill=0)
    draw.text((10, 63), "UP:", font=fontSmallBold, fill=0)
    draw.text((40, 63), f"{pihole1UpTime}", font=fontSmall, fill=0)
    draw.text((10, 82), "TEMP:", font=fontSmallBold, fill=0)
    draw.text((60, 82), f"{pihole1Temp}°C", font=fontSmall, fill=0)

    draw.text((135, 25), "REQ:", font=fontSmallBold, fill=0)
    draw.text((175, 25), f"{pihole2RequestsNumber}", font=fontSmall, fill=0)
    draw.text((135, 44), "BLKD:", font=fontSmallBold, fill=0)
    draw.text((185, 44), f"{pihole2Blocked}%", font=fontSmall, fill=0)
    draw.text((135, 63), "UP:", font=fontSmallBold, fill=0)
    draw.text((165, 63), f"{pihole2UpTime}", font=fontSmall, fill=0)
    draw.text((135, 82), "TEMP:", font=fontSmallBold, fill=0)
    draw.text((185, 82), f"{pihole2Temp}°C", font=fontSmall, fill=0)

    # Separator lines
    draw.line((127.5, 0, 127.5, 100), fill=0)  # Vertical separator
    draw.line((0, 101, width, 101), fill=0)   # Horizontal footer separator

    # Battery
    if isinstance(battery, int):
        batteryBarLength = int(60 * battery / 100)
        draw.text((85, 105), f"{round(battery)}%", font=fontSmall, fill=0)
    else:
        batteryBarLength = 0
        draw.text((85, 105), "N/A", font=fontSmall, fill=0)
    draw.rectangle((10, 107, 10 + batteryBarLength, 117), fill=0)
    draw.rectangle((10, 107, 70, 117), outline=0)

    # Date-time
    draw.text((155, 105), now_str, font=fontSmall, fill=0)

    rotatedImage = image.rotate(180)
    colorInvertedImage = ImageOps.invert(rotatedImage.convert("L")).convert("1")
    epd.display(epd.getbuffer(colorInvertedImage))
    epd.sleep()

if __name__ == "__main__":
    main()
