#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont, ImageOps
import subprocess
import datetime
import epd2in13_V2  # usa _V3 se for o teu modelo
from pisugar2py import PiSugar2
import logging
import socket
import os
import shutil
import json

logging.basicConfig(level=logging.DEBUG)

# === Configurações ===
LOW_BATTERY_THRESHOLD = 20

# === Funções auxiliares ===
def get_battery():
    try:
        logging.debug("Initializing PiSugar2...")
        ps = PiSugar2()
        logging.debug("Getting battery level...")
        battery_percentage = ps.get_battery_percentage()
        logging.debug(
            "Battery: " + str(int(battery_percentage.value)) + " %")
        logging.debug("Syncing RTC...")
        ps.set_pi_from_rtc()
        return int(battery_percentage.value)
    except Exception as e:
        logging.error("Error getting battery status")
        logging.error(e)
        ps = False
        return "N/A"

def check_pihole_status():
    logging.debug("Checking PiHole status")
    try:
        MPD_FILE = b"Pi-hole blocking is enabled" 
        output = subprocess.check_output(["pihole", "status"])
        return "Ativo" if MPD_FILE in output else "Inativo"
    except Exception as e:
        logging.error("Error checking PiHole status")
        logging.error(e)
        return "N/A"
    
def get_ip():
    logging.debug("Checking IP")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception as e:
        logging.error("Error checking IP")
        logging.error(e)
        ip = "N/A"
    return ip

def get_uptime():
    logging.debug("Checking Up Time")
    with open("/proc/uptime", "r") as f:
        uptime_seconds = float(f.readline().split()[0])
        hours = int(uptime_seconds // 3600)
        minutes = int((uptime_seconds % 3600) // 60)
        return f"{hours}h {minutes}m"

def get_temp():
    logging.debug("Checking Temperature")
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            return round(int(f.read()) / 1000, 1)
    except Exception as e:
        logging.error("Error checking temperature")
        logging.error(e)
        return "N/A"

def get_free_space():
    logging.debug("Checking Free Space")
    total, used, free = shutil.disk_usage("/")
    return round(free / (1024**3), 1)

def check_internet():
    logging.debug("Checking Internet")
    return os.system("ping -c 1 8.8.8.8 > /dev/null 2>&1") == 0

# === Main ===
def main():
    epd = epd2in13_V2.EPD()
    epd.init(epd.FULL_UPDATE)
    width, height = epd.height, epd.width

    image = Image.new('1', (width, height), 255)
    draw = ImageDraw.Draw(image)

    global font_small, font_large, font_small_bold
    font_large = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 20)
    font_small = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 14)
    font_small_bold = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', 14)

    #PiSugar2
    battery_pct = get_battery()

    # PiHole
    pihole_status = check_pihole_status()

    # Recolher dados
    ip = get_ip()
    uptime = get_uptime()
    temp = get_temp()
    free_gb = get_free_space()
    internet_ok = check_internet()
    now_str = datetime.datetime.now().strftime("%d/%m %H:%M")

    # Desenho
    #Bateria: 72%    IP: 192.168.1.42
    #Pi-hole: Ativo    Internet: OK
    #Temp: 42.6°C    Uptime: 3h 42m
    #Anúncios bloqueados: 18.3%
    #------------------------------
    #Atualizado: 20/04 14:58 

    draw.text((5, 5), f"Bateria: {battery_pct}%   IP: {ip}", font=font_small, fill=0)
    draw.text((5, 25), f"Pi-hole: {pihole_status}    Internet: {'OK' if internet_ok else 'Falha'}", font=font_small, fill=0)
    draw.text((5, 45), f"Temp: {temp}°C    Uptime: {uptime}", font=font_small, fill=0)
    draw.text((5, 65), f"Espaço livre: {free_gb}GB", font=font_small, fill=0)

    draw.line((0, 102, width, 102), fill=0)

    draw.text((5, 105), f"Atualizado em: {now_str}", font=font_small, fill=0)

    rotated_image = image.rotate(180)
    color_inverted_image = ImageOps.invert(rotated_image.convert("L")).convert("1")
    epd.display(epd.getbuffer(color_inverted_image))
    epd.sleep()

if __name__ == "__main__":
    main()
