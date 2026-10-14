from machine import Pin, I2C, ADC
from rda5807 import RDA5807, BAND_87_108, SPACE_100K
import time

# 1. Initialize Hardware Connections using correct RP2040 GPIOs
i2c = I2C(0, scl=Pin(7), sda=Pin(6), freq=400000) # Match your A5 (SCL) and A4 (SDA)
radio = RDA5807(i2c=i2c, band=BAND_87_108, space=SPACE_100K)

# 2. Initialize Analog Dials (A0 -> GPIO 26, A1 -> GPIO 27)
tuning_knob = ADC(Pin(26))  
volume_knob = ADC(Pin(27))  

# 3. Initialize Power Toggle Button (A2 -> GPIO 28)
power_button = Pin(28, Pin.IN, Pin.PULL_UP)  

# State tracking variables
radio_on = True  
button_was_pressed = False
last_volume = -1
last_freq = -1.0

radio.set_mono(True)
print("Radio System Ready! Initializing loops...")

while True:
    # -------------------------------------------------------------
    # BUTTON CHECK (SW1 / GPIO 28)
    # -------------------------------------------------------------
    if power_button.value() == 0:
        if not button_was_pressed:
            radio_on = not radio_on
            button_was_pressed = True  
            
            if radio_on:
                print("--- RADIO ON ---")
                radio.set_volume(10)
                last_volume = -1  
                last_freq = -1.0  
            else:
                print("--- RADIO OFF ---")
                radio.set_volume(0)  
            time.sleep(0.2)
    else:
        button_was_pressed = False

    # -------------------------------------------------------------
    # CONTROL LOOPS (Only executes when active)
    # -------------------------------------------------------------
    if radio_on:
        # Volume Control (RV2)
        vol_raw = volume_knob.read_u16()
        target_volume = int((vol_raw / 65535) * 15)
        if target_volume != last_volume:
            radio.set_volume(target_volume)
            print(f"Volume: {target_volume}")
            last_volume = target_volume

        # Tuning Control (RV1)
        tune_raw = tuning_knob.read_u16()
        target_freq = 87.5 + ((tune_raw / 65535) * (108.0 - 87.5))
        target_freq = round(target_freq, 1)
        if abs(target_freq - last_freq) >= 0.1:
            radio.tune(target_freq)
            print(f"Station: {target_freq} MHz")
            last_freq = target_freq

    time.sleep(0.05)
