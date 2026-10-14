
import time
import board
import busio

RDA5807_ADDR = 0x10

# ---- Reg 0x02 bit positions ----
DHIZ = 1 << 15
DMUTE = 1 << 14
MONO = 1 << 13
BASS = 1 << 12
SEEKUP = 1 << 9
SEEK = 1 << 8
SKMODE = 1 << 7
NEW_METHOD = 1 << 2
SOFT_RESET = 1 << 1
ENABLE = 1 << 0

# ---- Reg 0x03 ----
TUNE = 1 << 4

BAND_87_108 = 0b00  # US/Europe
BAND_76_91 = 0b01  # Japan
BAND_76_108 = 0b10  # worldwide

SPACE_100K = 0b00
SPACE_200K = 0b01
SPACE_50K = 0b10
SPACE_25K = 0b11

_SPACE_KHZ = {SPACE_100K: 100, SPACE_200K: 200, SPACE_50K: 50, SPACE_25K: 25}
_BAND_BASE_MHZ = {BAND_87_108: 87.0, BAND_76_91: 76.0, BAND_76_108: 76.0}


class RDA5807:
    def __init__(self, i2c=None, band=BAND_87_108, space=SPACE_100K):
        self.i2c = i2c or busio.I2C(board.SCL, board.SDA, frequency=100000)
        self.band = band
        self.space = space
        self._volume = 15
        self._mono = False
        self._reg04 = 0x0200  # softmute enabled, 75us de-emphasis, AFC on
        self._init_chip()

    # ---------------- low level ----------------

    def _write_block(self, values):
        """values: list of 16-bit ints written starting at register 0x02."""
        data = bytearray(len(values) * 2)
        for i, v in enumerate(values):
            data[2 * i] = (v >> 8) & 0xFF
            data[2 * i + 1] = v & 0xFF
        while not self.i2c.try_lock():
            pass
        try:
            self.i2c.writeto(RDA5807_ADDR, bytes(data))
        finally:
            self.i2c.unlock()

    def _read_block(self, n_regs):
        """Returns a list of 16-bit ints starting at register 0x0A."""
        buf = bytearray(n_regs * 2)
        while not self.i2c.try_lock():
            pass
        try:
            self.i2c.readfrom_into(RDA5807_ADDR, buf)
        finally:
            self.i2c.unlock()
        return [(buf[2 * i] << 8) | buf[2 * i + 1] for i in range(n_regs)]

    # ---------------- setup ----------------

    def _init_chip(self):
        # Soft reset + power up first.
        self._write_block([DHIZ | ENABLE | SOFT_RESET])
        time.sleep(0.1)
        self._apply_config()
        time.sleep(0.1)

    def _apply_config(self):
        reg02 = DHIZ | ENABLE | NEW_METHOD
        if not self._mono:
            pass  # MONO bit stays 0 -> stereo
        else:
            reg02 |= MONO
        reg02 |= DMUTE  # unmute audio path

        reg03 = (self.band << 2) | self.space  # TUNE bit added per-call in tune()
        reg04 = self._reg04
        reg05 = 0x8000 | (8 << 8) | (self._volume & 0x0F)  # INT_MODE=1, default seek th, volume

        self._write_block([reg02, reg03, reg04, reg05])

    # ---------------- controls ----------------

    def set_volume(self, level):
        """0 (mute) - 15 (max)."""
        self._volume = max(0, min(15, level))
        self._apply_config()

    def set_mono(self, mono):
        self._mono = bool(mono)
        self._apply_config()

    def tune(self, freq_mhz, timeout=1.0):
        """Tune directly to a frequency in MHz."""
        base = _BAND_BASE_MHZ[self.band]
        spacing_mhz = _SPACE_KHZ[self.space] / 1000.0
        chan = int(round((freq_mhz - base) / spacing_mhz))
        chan = max(0, min(0x3FF, chan))

        reg03 = (chan << 6) | (self.band << 2) | self.space | TUNE
        # reg02 unchanged (re-send current config so it isn't reset)
        reg02 = DHIZ | ENABLE | NEW_METHOD | DMUTE | (MONO if self._mono else 0)
        self._write_block([reg02, reg03])
        self._wait_stc(timeout)

    def seek(self, up=True, timeout=3.0):
        """Seek to the next station. Returns the frequency found, or None."""
        reg02 = DHIZ | ENABLE | NEW_METHOD | DMUTE | SEEK
        if up:
            reg02 |= SEEKUP
        if self._mono:
            reg02 |= MONO
        self._write_block([reg02])
        ok = self._wait_stc(timeout)
        # Clear SEEK bit
        reg02 &= ~SEEK
        self._write_block([reg02])
        if not ok:
            return None
        status = self.read_status()
        if status["seek_fail"]:
            return None
        return status["freq_mhz"]

    def _wait_stc(self, timeout):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            status = self.read_status()
            if status["stc"]:
                return True
            time.sleep(0.02)
        return False

    def read_status(self):
        regs = self._read_block(2)  # reg 0x0A, 0x0B
        reg0a, reg0b = regs[0], regs[1]

        chan = reg0a & 0x03FF
        base = _BAND_BASE_MHZ[self.band]
        spacing_mhz = _SPACE_KHZ[self.space] / 1000.0
        freq_mhz = base + chan * spacing_mhz

        return {
            "rds_ready": bool(reg0a & (1 << 15)),
            "stc": bool(reg0a & (1 << 14)),
            "seek_fail": bool(reg0a & (1 << 13)),
            "stereo": bool(reg0a & (1 << 10)),
            "channel": chan,
            "freq_mhz": round(freq_mhz, 2),
            "rssi": (reg0b >> 9) & 0x7F,
            "fm_true": bool(reg0b & (1 << 8)),
            "fm_ready": bool(reg0b & (1 << 7)),
        }
