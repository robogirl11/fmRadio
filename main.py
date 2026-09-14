from machine import I2C, Pin, ADC
import time

class RDA5807:
    def __init__(self, i2c, address=0x10):
        self.i2c = i2c
        self.address = address
        self.regs = [0x004B, 0xD000, 0x0000, 0x0000, 0x0000, 0x4000]
        self.write_all()

    def write_all(self):
        """Pushes register data to the chip over I2C"""
        buffer = bytearray(12)
        for i in range(6):
            buffer[i*2] = (self.regs[i] >> 8) & 0xFF
            buffer[i*2+1] = self.regs[i] & 0xFF
        try:
            self.i2c.writeto(self.address, buffer)
        except Exception as e:
            print("I2C Error writing to RDA5807:", e)

    def set_frequency(self, freq_mhz):
        """Sets the tuning frequency (87.5 to 108.0 MHz)"""
        if freq_mhz < 87.5: 
            freq_mhz = 87.5
        if freq_mhz > 108.0: 
            freq_mhz = 108.0
            
        chan = int((freq_mhz - 87.0) * 10)
        self.regs[1] = 0xD000 | (chan << 6) | 0x0010
        self.write_all()

i2c = I2C(1, scl=Pin(7), sda=Pin(6), freq=400000)

pot = ADC(Pin(26))

radio = RDA5807(i2c)
time.sleep(0.5)

print("FM Radio Firmware Active. Turn the potentiometer to scan channels.")

last_freq = 0.0
FREQ_MIN = 87.5
FREQ_MAX = 108.0

while True:
    raw_analog = pot.read_u16()
    
    target_freq = FREQ_MIN + (raw_analog / 65535.0) * (FREQ_MAX - FREQ_MIN)
    target_freq = round(target_freq, 1)
    
    if abs(target_freq - last_freq) >= 0.1:
        print(f"Tuning to: {target_freq} MHz")
        radio.set_frequency(target_freq)
        last_freq = target_freq
        
    time.sleep(0.2)