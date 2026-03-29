import serial
import serial.tools.list_ports
import time
import sys
import threading

# ---------- GPIO (RELAYS) ----------
import RPi.GPIO as GPIO

# ---------- OLED ----------
from luma.core.interface.serial import i2c
from luma.oled.device import ssd1306
from luma.core.render import canvas

# ---------- DHT ----------
import board
import adafruit_dht

# ==========================
# CONFIG
# ==========================
BAUDRATE = 921600

DAY_THRESHOLD   = 2500     # below = day
NIGHT_THRESHOLD = 3800     # above = night (hysteresis)

SERIAL_TIMEOUT = 0.1       # ultra low latency
STATE_COOLDOWN = 1.0       # seconds (prevents flicker)
PRINT_INTERVAL = 0.5       # seconds

# OLED
OLED_ADDR = 0x3C

# DHT sensors
DHT1_PIN = board.D17    # GPIO17
DHT2_PIN = board.D27    # GPIO27
DHT_TYPE = adafruit_dht.DHT11   # change to DHT22 if needed
READ_INTERVAL = 2.0   # seconds

# ---------- RELAYS ----------
FAN_RELAY_PIN   = 22   # GPIO22
VALVE_RELAY_PIN = 23   # GPIO23

# ==========================
# INIT GPIO
# ==========================
GPIO.setmode(GPIO.BCM)
GPIO.setup(FAN_RELAY_PIN, GPIO.OUT)
GPIO.setup(VALVE_RELAY_PIN, GPIO.OUT)

# Default OFF
GPIO.output(FAN_RELAY_PIN, GPIO.LOW)
GPIO.output(VALVE_RELAY_PIN, GPIO.LOW)

# ==========================
# RELAY CONTROL
# ==========================
def fan_on():
    GPIO.output(FAN_RELAY_PIN, GPIO.HIGH)
    print("🌀 Fan ON")

def fan_off():
    GPIO.output(FAN_RELAY_PIN, GPIO.LOW)
    print("🌀 Fan OFF")

def valve_on():
    GPIO.output(VALVE_RELAY_PIN, GPIO.HIGH)
    print("💧 Valve ON")

def valve_off():
    GPIO.output(VALVE_RELAY_PIN, GPIO.LOW)
    print("💧 Valve OFF")

# ==========================
# INIT OLED
# ==========================
serial_i2c = i2c(port=1, address=OLED_ADDR)
oled = ssd1306(serial_i2c)

# ==========================
# INIT DHT
# ==========================
dht1 = DHT_TYPE(DHT1_PIN, use_pulseio=False)
dht2 = DHT_TYPE(DHT2_PIN, use_pulseio=False)

# ==========================
# GLOBAL DATA
# ==========================
t1 = h1 = None
t2 = h2 = None

soil_value = None
light_value = None

day_status = None
last_state_change = 0
last_print = 0

# ==========================
# SERIAL AUTO-DETECT
# ==========================
def find_esp32():
    for p in serial.tools.list_ports.comports():
        if "ACM" in p.device or "USB" in p.device:
            return p.device
    return None

port = find_esp32()
if not port:
    print("❌ ESP32 not found")
    sys.exit(1)

ser = serial.Serial(port, BAUDRATE, timeout=SERIAL_TIMEOUT)
time.sleep(2)
ser.reset_input_buffer()

print(f"✅ ESP32 connected on: {port}")

# ==========================
# COMMAND SENDER (ESP32)
# ==========================
def send_cmd(cmd: str):
    try:
        ser.write((cmd + "\n").encode())
    except:
        pass

# ==========================
# SERIAL PARSER
# ==========================
def parse_line(line: str):
    try:
        parts = line.strip().split(",")
        if len(parts) != 2:
            return None, None
        soil = int(parts[0])
        light = int(parts[1])
        return soil, light
    except:
        return None, None

# ==========================
# DHT THREAD
# ==========================
def read_sensors():
    global t1, h1, t2, h2
    while True:
        try:
            t1 = round(dht1.temperature, 1)
            h1 = round(dht1.humidity, 1)
        except:
            pass

        try:
            t2 = round(dht2.temperature, 1)
            h2 = round(dht2.humidity, 1)
        except:
            pass

        time.sleep(READ_INTERVAL)

# ==========================
# OLED UPDATE
# ==========================
def update_oled():
    with canvas(oled) as draw:
        draw.text((0, 0),  "GREENHOUSE MONITOR", fill=255)
        draw.text((0, 12), "---------------------", fill=255)

        # DHT1
        if t1 is not None and h1 is not None:
            draw.text((0, 24), f"DHT1 T:{t1}C  H:{h1}%", fill=255)
        else:
            draw.text((0, 24), "DHT1 T:--  H:--", fill=255)

        # DHT2
        if t2 is not None and h2 is not None:
            draw.text((0, 36), f"DHT2 T:{t2}C  H:{h2}%", fill=255)
        else:
            draw.text((0, 36), "DHT2 T:--  H:--", fill=255)

        if day_status:
            draw.text((0, 52), f"MODE: {day_status}", fill=255)
        else:
            draw.text((0, 52), "MODE: ---", fill=255)

# ==========================
# START THREADS
# ==========================
print("🚀 Starting DHT thread...")
threading.Thread(target=read_sensors, daemon=True).start()

print("🚀 Controller started")

# ==========================
# MAIN LOOP
# ==========================
while True:
    try:
        if ser.in_waiting:
            raw = ser.readline().decode(errors="ignore").strip()

            soil, light = parse_line(raw)
            if soil is None or light is None:
                continue

            soil_value = soil
            light_value = light

            now = time.time()

            # -------- DAY/NIGHT FSM --------
            new_state = day_status

            if day_status is None:
                if light < DAY_THRESHOLD:
                    new_state = "Day"
                elif light > NIGHT_THRESHOLD:
                    new_state = "Night"

            elif day_status == "Day":
                if light > NIGHT_THRESHOLD:
                    new_state = "Night"

            elif day_status == "Night":
                if light < DAY_THRESHOLD:
                    new_state = "Day"

            # -------- STATE CHANGE --------
            if new_state != day_status and new_state is not None:
                if now - last_state_change > STATE_COOLDOWN:
                    day_status = new_state
                    last_state_change = now

                    if day_status == "Night":
                        print("🌙 Night detected → LED ON")
                        send_cmd("LED_ON")
                    else:
                        print("☀️ Day detected → LED OFF")
                        send_cmd("LED_OFF")

            # -------- AUTOMATION LOGIC --------
            # Fan by temperature
            if t1 is not None and t1 > 30:
                fan_on()
            else:
                fan_off()

            # Valve by soil
            if soil_value is not None and soil_value < 1900:
                valve_on()
            else:
                valve_off()

            # -------- OLED --------
            update_oled()

            # -------- PRINT --------
            if now - last_print > PRINT_INTERVAL:
                last_print = now
                print(f"Soil:{soil_value}  Light:{light_value}  Mode:{day_status} | "
                      f"T1:{t1} H1:{h1} | T2:{t2} H2:{h2}")

        else:
            time.sleep(0.001)

    except KeyboardInterrupt:
        print("\n🛑 Exiting...")
        send_cmd("LED_OFF")
        fan_off()
        valve_off()
        GPIO.cleanup()
        break
    except Exception as e:
        print("⚠️ Error:", e)
        time.sleep(0.1)
