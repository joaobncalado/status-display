#!/usr/bin/env python3
from PIL import Image, ImageDraw, ImageFont
import subprocess
import datetime
import epd2in13_V2  # usa _V3 se for o teu modelo
from pisugar2py import PiSugar2
import logging

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
        logging.error(e)
        ps = False
        return None

def check_pihole():
    try:
        MPD_FILE = b"Pi-hole blocking is enabled" 
        output = subprocess.check_output(["pihole", "status"])
        return "Ativo" if MPD_FILE in output else "Inativo"
    except Exception as e:
        logging.error(e)
        return "Erro"

def draw_battery(draw, x, y, percent):
    draw.rectangle((x, y, x + 40, y + 20), outline=0, width=2)
    draw.rectangle((x + 40, y + 6, x + 44, y + 14), fill=0)
    level = int((percent / 100) * 3)
    for i in range(level):
        draw.rectangle((x + 4 + i * 12, y + 4, x + 14 + i * 12, y + 16), fill=0)

def draw_pihole_icon(draw, x, y):
    draw.ellipse((x, y, x + 24, y + 24), fill=0)
    draw.polygon([(x + 12, y - 12), (x + 8, y), (x + 16, y)], fill=0)

def draw_alert(draw, x, y, text):
    draw.rectangle((x, y, x + 240, y + 25), fill=0)
    draw.text((x + 10, y + 5), text, font=font_small_bold, fill=255)

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

    now = datetime.datetime.now().strftime('%d/%m/%Y %H:%M')

    battery = get_battery()
    pihole_status = check_pihole()

    # Topo: Data e Hora
    draw.text((10, 5), now, font=font_small, fill=0)

    # Bateria
    draw_battery(draw, 10, 30, battery if battery is not None else 0)
    draw.text((60, 32), f"Bateria: {battery}%", font=font_small, fill=0)

    # Pi-hole
    draw_pihole_icon(draw, 10, 70)
    draw.text((60, 75), f"Pi-hole: {pihole_status}", font=font_large, fill=0)

    # Alertas
    if battery is not None and battery < LOW_BATTERY_THRESHOLD:
        draw_alert(draw, 0, height - 45, "ALERTA: Bateria fraca!")
    if pihole_status != "Ativo":
        draw_alert(draw, 0, height - 20, "ALERTA: Pi-hole inativo!")

    epd.display(epd.getbuffer(image))
    epd.sleep()

if __name__ == "__main__":
    main()
