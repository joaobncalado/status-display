#!/usr/bin/env python3
import asyncio
import aiohttp
import asyncssh
import logging
import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps
import epd2in13_V2
from pisugar2py import PiSugar2
from dataclasses import dataclass
import socket

# === Logger ===
LOG = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG)

# === Paths and Limits ===
USER_PATH = '/home/secrets/pihole_user'
PW_PATH = '/home/secrets/pihole_pw'
LOW_BATTERY_THRESHOLD = 20

# === Data structures ===
@dataclass
class DeviceStatus:
    ip: str
    status: str
    blocked_percentage: float
    uptime: str
    cpu_temp: float

# === Aux funcs ===
def read_from_file(path):
    try:
        with open(path, 'r') as f:
            return f.read().strip()
    except Exception as e:
        LOG.error(f"Error loading file content: {e}")
        return None

async def get_battery():
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
async def authenticate(session, ip, password):
    url = f"http://{ip}/api/auth"
    payload = {"password": password}
    try:
        async with session.post(url, json=payload) as response:
            data = await response.json()
            if not data.get("session", {}).get("valid"):
                raise Exception("Session is not valid")
            return data.get("session", {}).get("sid")
    except Exception as e:
        LOG.error(f"Authentication failed for {ip}: {e}")
        return None

async def logout(session, ip, sid):
    url = f"http://{ip}/api/auth"
    try:
        await session.delete(url, headers={"sid": sid})
    except Exception as e:
        LOG.error(f"Logout failed for {ip}: {e}")

async def get_pihole_data(ip, password):
    async with aiohttp.ClientSession() as session:
        sid = await authenticate(session, ip, password)
        if not sid:
            return DeviceStatus(ip, "Error", 0.0, "N/A", "N/A")
        
        try:
            # Status
            status_url = f"http://{ip}/api/dns/blocking"
            async with session.get(status_url, headers={"sid": sid}) as response:
                blocking_data = await response.json()
                status = blocking_data.get("blocking", "N/A")

            # Blocked Percentage
            summary_url = f"http://{ip}/api/stats/summary"
            async with session.get(summary_url, headers={"sid": sid}) as response:
                summary_data = await response.json()
                blocked_percentage = summary_data["queries"].get("percent_blocked", 0.0)

            return status, float(f"{blocked_percentage:.2f}")

        except Exception as e:
            LOG.error(f"Error getting PiHole data from {ip}: {e}")
            return "N/A", 0.0
        finally:
            await logout(session, ip, sid)

# === local and remote system funcs ===
async def get_local_uptime():
    try:
        with open("/proc/uptime", "r") as f:
            uptime_seconds = float(f.readline().split()[0])
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    except Exception as e:
        LOG.error(f"Error reading local uptime: {e}")
        return "N/A"

async def get_local_cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read()) / 1000, 1)
    except Exception as e:
        LOG.error(f"Error reading local CPU temp: {e}")
        return "N/A"

async def get_remote_uptime(ip, user, password):
    try:
        async with asyncssh.connect(ip, username=user, password=password, known_hosts=None) as conn:
            result = await conn.run('cat /proc/uptime')
            uptime_seconds = float(result.stdout.split()[0])
            hours = int(uptime_seconds // 3600)
            minutes = int((uptime_seconds % 3600) // 60)
            return f"{hours}h {minutes}m"
    except Exception as e:
        LOG.error(f"Error getting remote uptime: {e}")
        return "N/A"

async def get_remote_cpu_temp(ip, user, password):
    try:
        async with asyncssh.connect(ip, username=user, password=password, known_hosts=None) as conn:
            result = await conn.run('cat /sys/class/thermal/thermal_zone0/temp')
            return round(int(result.stdout.strip()) / 1000, 1)
    except Exception as e:
        LOG.error(f"Error getting remote CPU temp: {e}")
        return "N/A"

# === main ===
async def main():
    pihole1_ip = '192.168.50.135'
    pihole2_ip = '127.0.0.1'

    user = read_from_file(USER_PATH)
    password = read_from_file(PW_PATH)

    # parallel execution
    results = await asyncio.gather(
        get_pihole_data(pihole1_ip, password),
        get_pihole_data(pihole2_ip, password),
        get_remote_uptime(pihole1_ip, user, password),
        get_remote_cpu_temp(pihole1_ip, user, password),
        get_local_uptime(),
        get_local_cpu_temp(),
        get_battery()
    )

    # split results
    (pihole1_status, pihole1_blocked), (pihole2_status, pihole2_blocked), \
    pihole1_uptime, pihole1_temp, pihole2_uptime, pihole2_temp, battery = results

    # start display
    epd = epd2in13_V2.EPD()
    epd.init(epd.FULL_UPDATE)
    width, height = epd.height, epd.width

    image = Image.new('1', (width, height), 255)
    draw = ImageDraw.Draw(image)

    font_bold = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
    font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)

    now_str = datetime.datetime.now().strftime("%d/%m %H:%M")

    # --- layout drawing ---
    # Headers
    draw.text((10, 6), f"{pihole1_ip}", font=font_bold, fill=0)
    draw.text((130, 6), f"{pihole2_ip}", font=font_bold, fill=0)

    # Data
    draw.text((10, 25), f"Status: {pihole1_status}", font=font_small, fill=0)
    draw.text((10, 44), f"Uptime: {pihole1_uptime}", font=font_small, fill=0)
    draw.text((10, 63), f"Blocked: {pihole1_blocked}%", font=font_small, fill=0)
    draw.text((10, 82), f"Temp: {pihole1_temp}°C", font=font_small, fill=0)

    draw.text((130, 25), f"Status: {pihole2_status}", font=font_small, fill=0)
    draw.text((130, 44), f"Uptime: {pihole2_uptime}", font=font_small, fill=0)
    draw.text((130, 63), f"Blocked: {pihole2_blocked}%", font=font_small, fill=0)
    draw.text((130, 82), f"Temp: {pihole2_temp}°C", font=font_small, fill=0)

    # Separator lines
    draw.line((122, 0, 122, height), fill=0)  # Vertical separator
    draw.line((0, 100, width, 100), fill=0)   # Horizontal footer separator

    # Battery bar + percentage
    battery_bar_length = int(50 * battery / 100) if isinstance(battery, int) else 0
    draw.rectangle((10, 103, 10 + battery_bar_length, 115), fill=0)
    draw.rectangle((10, 103, 60, 115), outline=0)  # Battery outline
    draw.text((80, 101), f"{round(battery)}%", font=font_small, fill=0)
    draw.text((160, 101), now_str, font=font_small, fill=0)

    # Final display
    rotated_image = image.rotate(180)
    bw_image = rotated_image.convert("1")
    epd.display(epd.getbuffer(bw_image))
    epd.sleep()

if __name__ == "__main__":
    asyncio.run(main())
