"""ST7735 128x128 LCD display driver for WLANPi Pro.

Ported from wlanpi-fpms/fpms/modules/screen/st7735.py — logic unchanged,
only imports adapted for the new package layout.
"""

from __future__ import annotations

import time

from PIL import Image

from wlanpi_fpms2.interfaces.screen.drivers.screen import AbstractScreen

LCD_WIDTH, LCD_HEIGHT, LCD_X, LCD_Y = 128, 128, 2, 1
LCD_X_MAXPIXEL = 132  # LCD width maximum memory
LCD_Y_MAXPIXEL = 162  # LCD height maximum memory
SCAN_DIR_DFT = 6      # U2D_R2L


class RaspberryPi:
    def __init__(self, spi=None, spi_freq=40000000, rst=27, dc=25, bl=24, bl_freq=1000):
        import spidev
        from gpiozero import DigitalInputDevice, DigitalOutputDevice, PWMOutputDevice

        self.INPUT = False
        self.OUTPUT = True
        self.SPEED = spi_freq
        self.BL_freq = bl_freq

        self.GPIO_RST_PIN = DigitalOutputDevice(rst, active_high=True, initial_value=False)
        self.GPIO_DC_PIN  = DigitalOutputDevice(dc,  active_high=True, initial_value=False)
        self.GPIO_BL_PIN  = PWMOutputDevice(bl, frequency=bl_freq)
        self.GPIO_BL_PIN.value = 0

        self.SPI = spi if spi is not None else spidev.SpiDev(0, 0)
        self.SPI.max_speed_hz = spi_freq
        self.SPI.mode = 0b00

    def digital_write(self, pin, value):
        if value:
            pin.on()
        else:
            pin.off()

    def digital_read(self, pin):
        return pin.value

    def delay_ms(self, ms):
        time.sleep(ms / 1000.0)

    def spi_writebyte(self, data):
        self.SPI.writebytes(data)

    def bl_DutyCycle(self, duty):
        self.GPIO_BL_PIN.value = duty / 100

    def module_init(self):
        self.SPI.max_speed_hz = self.SPEED
        self.SPI.mode = 0b00
        return 0

    def module_exit(self):
        self.SPI.close()
        self.digital_write(self.GPIO_RST_PIN, 1)
        self.digital_write(self.GPIO_DC_PIN, 0)
        self.GPIO_BL_PIN.close()
        time.sleep(0.001)


class LCD(RaspberryPi):
    width, height = LCD_WIDTH, LCD_HEIGHT
    LCD_Scan_Dir = SCAN_DIR_DFT
    LCD_X_Adjust, LCD_Y_Adjust = LCD_X, LCD_Y

    def LCD_Reset(self):
        self.digital_write(self.GPIO_RST_PIN, True)
        time.sleep(0.01)
        self.digital_write(self.GPIO_RST_PIN, False)
        time.sleep(0.01)
        self.digital_write(self.GPIO_RST_PIN, True)
        time.sleep(0.01)

    def LCD_WriteReg(self, reg):
        self.digital_write(self.GPIO_DC_PIN, False)
        self.spi_writebyte([reg])

    def LCD_WriteData_8bit(self, data):
        self.digital_write(self.GPIO_DC_PIN, True)
        self.spi_writebyte([data])

    def LCD_InitReg(self):
        init_sequence = [
            (0xB1, [0x01, 0x2C, 0x2D]),
            (0xB2, [0x01, 0x2C, 0x2D]),
            (0xB3, [0x01, 0x2C, 0x2D, 0x01, 0x2C, 0x2D]),
            (0xB4, [0x07]),
            (0xC0, [0xA2, 0x02, 0x84]),
            (0xC1, [0xC5]),
            (0xC2, [0x0A, 0x00]),
            (0xC3, [0x8A, 0x2A]),
            (0xC4, [0x8A, 0xEE]),
            (0xC5, [0x0E]),
            (0xe0, [0x0f, 0x1a, 0x0f, 0x18, 0x2f, 0x28, 0x20, 0x22, 0x1f, 0x1b, 0x23, 0x37, 0x00, 0x07, 0x02, 0x10]),
            (0xe1, [0x0f, 0x1b, 0x0f, 0x17, 0x33, 0x2c, 0x29, 0x2e, 0x30, 0x30, 0x39, 0x3f, 0x00, 0x07, 0x03, 0x10]),
            (0xF0, [0x01]),
            (0xF6, [0x00]),
            (0x3A, [0x05]),
        ]
        for reg, data in init_sequence:
            self.LCD_WriteReg(reg)
            for d in data:
                self.LCD_WriteData_8bit(d)

    def LCD_SetGramScanWay(self, scan_dir):
        self.LCD_Scan_Dir = scan_dir
        MemoryAccessReg_Data = {
            1: 0x00, 2: 0x80, 3: 0x40, 4: 0xC0,
            5: 0x20, 6: 0x60, 7: 0xA0, 8: 0xE0,
        }[scan_dir]
        if MemoryAccessReg_Data & 0x10 != 1:
            self.LCD_X_Adjust, self.LCD_Y_Adjust = LCD_Y, LCD_X
        else:
            self.LCD_X_Adjust, self.LCD_Y_Adjust = LCD_X, LCD_Y
        self.LCD_WriteReg(0x36)
        self.LCD_WriteData_8bit(MemoryAccessReg_Data | 0x08)

    def LCD_Init(self, scan_dir):
        if self.module_init() != 0:
            return -1
        self.bl_DutyCycle(100)
        self.LCD_Reset()
        self.LCD_InitReg()
        self.LCD_SetGramScanWay(scan_dir)
        self.delay_ms(200)
        self.LCD_WriteReg(0x11)
        self.delay_ms(120)
        self.LCD_WriteReg(0x29)

    def LCD_SetWindows(self, xstart, ystart, xend, yend):
        self.LCD_WriteReg(0x2A)
        self.LCD_WriteData_8bit(0x00)
        self.LCD_WriteData_8bit((xstart & 0xff) + self.LCD_X_Adjust)
        self.LCD_WriteData_8bit(0x00)
        self.LCD_WriteData_8bit(((xend - 1) & 0xff) + self.LCD_X_Adjust)
        self.LCD_WriteReg(0x2B)
        self.LCD_WriteData_8bit(0x00)
        self.LCD_WriteData_8bit((ystart & 0xff) + self.LCD_Y_Adjust)
        self.LCD_WriteData_8bit(0x00)
        self.LCD_WriteData_8bit(((yend - 1) & 0xff) + self.LCD_Y_Adjust)
        self.LCD_WriteReg(0x2C)

    def LCD_Clear(self):
        buf = [0x00, 0x00] * (self.width * self.height)
        self.LCD_SetWindows(0, 0, self.width, self.height)
        self.digital_write(self.GPIO_DC_PIN, True)
        for i in range(0, len(buf), 4096):
            self.spi_writebyte(buf[i:i + 4096])

    def LCD_ShowImage(self, image: Image.Image, xstart: int, ystart: int) -> None:
        if image is None:
            return
        if image.size != (self.width, self.height):
            raise ValueError(f"Image must be {self.width}x{self.height}")
        pix = []
        img = image.load()
        for y in range(self.height):
            for x in range(self.width):
                r, g, b = img[x, y]
                pix.append((r & 0xF8) | (g >> 5))
                pix.append(((g << 3) & 0xE0) | (b >> 3))
        self.LCD_SetWindows(0, 0, self.width, self.height)
        self.digital_write(self.GPIO_DC_PIN, True)
        for i in range(0, len(pix), 4096):
            self.spi_writebyte(pix[i:i + 4096])

    def LCD_Backlight(self, on: bool) -> None:
        self.bl_DutyCycle(100 if on else 0)


class ST7735(AbstractScreen):
    def init(self) -> bool:
        self.device = LCD()
        self.device.LCD_Init(SCAN_DIR_DFT)
        self.device.LCD_Clear()
        return True

    def drawImage(self, image: Image.Image) -> None:
        if image.size != (LCD_WIDTH, LCD_HEIGHT):
            image = image.resize((LCD_WIDTH, LCD_HEIGHT), Image.LANCZOS)
        self.device.LCD_ShowImage(image, 0, 0)

    def clear(self) -> None:
        self.device.LCD_Clear()

    def sleep(self) -> None:
        self.device.LCD_Clear()
        self.device.LCD_Backlight(False)

    def wakeup(self) -> None:
        self.device.LCD_Backlight(True)
