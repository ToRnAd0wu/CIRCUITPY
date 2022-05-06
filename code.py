# SPDX-FileCopyrightText: 2020 Richard Albritton for Adafruit Industries
#
# SPDX-License-Identifier: MIT

import time
import board
import microcontroller
import displayio
import busio
from analogio import AnalogIn
import neopixel
import adafruit_adt7410
from adafruit_bitmap_font import bitmap_font
from adafruit_display_text.label import Label
from adafruit_button import Button
import adafruit_touchscreen
from adafruit_pyportal import PyPortal
import json

from openweather_graphics import OpenWeather_Graphics
import sys
from secrets import secrets
import adafruit_requests as requests
from digitalio import DigitalInOut
from adafruit_esp32spi import adafruit_esp32spi
import adafruit_esp32spi.adafruit_esp32spi_socket as socket

import gc

cwd = ("/"+__file__).rsplit('/', 1)[0] # the current working directory (where this file is)
sys.path.append(cwd)
LOCATION = "Malmo, SE"
DATA_SOURCE = "http://api.openweathermap.org/data/2.5/weather?q="+LOCATION
DATA_SOURCE += "&appid="+secrets['openweather_token']
HOURS = 24
TEMP_URL = f"https://io.adafruit.com/api/v2/{secrets['aio_username']}/feeds/{secrets['temp_key']}/data/chart?x-aio-key={secrets['aio_key']}&hours={HOURS}"
PERCENT_URL = f"https://io.adafruit.com/api/v2/{secrets['aio_username']}/feeds/{secrets['percent_key']}/data/chart?x-aio-key={secrets['aio_key']}&hours={HOURS}"
FAILS_URL = f"https://io.adafruit.com/api/v2/{secrets['aio_username']}/feeds/{secrets['fails_key']}/data/chart?x-aio-key={secrets['aio_key']}&hours={HOURS}"
VOLTAGE_URL = f"https://io.adafruit.com/api/v2/{secrets['aio_username']}/feeds/{secrets['voltage_key']}/data/chart?x-aio-key={secrets['aio_key']}&hours={HOURS}"
CURRENT_URL = f"https://io.adafruit.com/api/v2/{secrets['aio_username']}/feeds/{secrets['current_key']}/data/chart?x-aio-key={secrets['aio_key']}&hours={HOURS}"

localtile_refresh = None
weather_refresh = None

#Adafruit
esp32_cs = DigitalInOut(board.ESP_CS)
esp32_ready = DigitalInOut(board.ESP_BUSY)
esp32_reset = DigitalInOut(board.ESP_RESET)

spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, esp32_cs, esp32_ready, esp32_reset)

print("Connecting to AP...")
while not esp.is_connected:
    try:
        esp.connect_AP(secrets["ssid"], secrets["password"])
    except RuntimeError as e:
        print("could not connect to AP, retrying: ", e)
        continue
print("Connected to", str(esp.ssid, "utf-8"), "\tRSSI:", esp.rssi)

socket.set_interface(esp)
requests.set_socket(socket, esp)


# ------------- Inputs and Outputs Setup ------------- #
try:  # attempt to init. the temperature sensor

    i2c_bus = busio.I2C(board.SCL, board.SDA)
    adt = adafruit_adt7410.ADT7410(i2c_bus, address=0x48)
    adt.high_resolution = True
except ValueError:
    # Did not find ADT7410. Probably running on Titano or Pynt
    adt = None

# init. the light sensor
#light_sensor = AnalogIn(board.LIGHT)

pixel = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=1)
WHITE = 0xffffff
RED = 0xff0000
YELLOW = 0xffff00
GREEN = 0x00ff00
BLUE = 0x0000ff
PURPLE = 0xff00ff
BLACK = 0x000000

# ------------- Screen Setup ------------- #
# Initialize the pyportal object and let us know what data to fetch and where
# to display it

pyportal = PyPortal(external_spi=spi,esp=esp)
display = board.DISPLAY
display.rotation = 0

# Touchscreen setup
# ------Rotate 0:
screen_width = 320
screen_height = 240
ts = adafruit_touchscreen.Touchscreen(board.TOUCH_XL, board.TOUCH_XR,
                                      board.TOUCH_YD, board.TOUCH_YU,
                                      calibration=((5200, 59000), (5800, 57000)),
                                      size=(screen_width, screen_height))


# ------------- Display Groups ------------- #
splash = displayio.Group()  # The Main Display Group
view1 = displayio.Group()  # Group for View 1 objects
view2 = displayio.Group()  # Group for View 2 objects
view3 = displayio.Group()  # Group for View 3 objects


def hideLayer(group,hide_target):
    try:
        group.remove(hide_target)
    except ValueError:
        pass

def showLayer(group,show_target):
    try:
        time.sleep(0.1)
        group.append(show_target)
    except ValueError:
        pass

# ------------- Setup for Images ------------- #
bg_group = displayio.Group()
splash.append(bg_group)
weather_group = displayio.Group()
background = displayio.Group()
splash.append(background)

# This will handel switching Images and Icons
def set_image(group, filename):
    """Set the image file for a given goup for display.
    This is most useful for Icons or image slideshows.
        :param group: The chosen group
        :param filename: The filename of the chosen image
    """
    print("Set image to ", filename)
    if group:
        group.pop()

    if not filename:
        return  # we're done, no icon desired

    # CircuitPython 6 & 7 compatible
    image_file = open(filename, "rb")
    image = displayio.OnDiskBitmap(image_file)
    image_sprite = displayio.TileGrid(image, pixel_shader=getattr(image, 'pixel_shader', displayio.ColorConverter()))

    # # CircuitPython 7+ compatible
    # image = displayio.OnDiskBitmap(filename)
    # image_sprite = displayio.TileGrid(image, pixel_shader=image.pixel_shader)

    group.append(image_sprite)

set_image(bg_group, "/images/bg.bmp")

# ---------- Text Boxes ------------- #
# Set the font and preload letters
font = bitmap_font.load_font("/fonts/Helvetica-Bold-16.bdf")
font.load_glyphs(b'abcdefghjiklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890- ()')

# Default Label styling:
TABS_X = 10
TABS_Y = 60

# Text Label Objects

#percent
percent_label = Label(font, text="Percent:", color=0xE39300, scale=2)
percent_label.x = TABS_X
percent_label.y = TABS_Y
view1.append(percent_label)

percent_data = Label(font, text="percent_data", color=0xE39300, scale=2)
percent_data.x = TABS_X + 150
percent_data.y = TABS_Y
view1.append(percent_data)

#current
current_label = Label(font, text="Current:", color=0xE39300, scale=2)
current_label.x = TABS_X
current_label.y = TABS_Y + 35
view1.append(current_label)

current_data = Label(font, text="current_data", color=0xE39300, scale=2)
current_data.x = TABS_X + 150
current_data.y = TABS_Y + 35
view1.append(current_data)

#voltage
voltage_label = Label(font, text="Voltage", color=0xE39300, scale=2)
voltage_label.x = TABS_X
voltage_label.y = TABS_Y + 70
view1.append(voltage_label)

voltage_data = Label(font, text="voltage_data", color=0xE39300, scale=2)
voltage_data.x = TABS_X + 150
voltage_data.y = TABS_Y + 70
view1.append(voltage_data)

#temp
temp_label = Label(font, text="Temp", color=0xE39300, scale=2)
temp_label.x = TABS_X
temp_label.y = TABS_Y + 105
view1.append(temp_label)

temp_data = Label(font, text="temp_data", color=0xE39300, scale=2)
temp_data.x = TABS_X + 150
temp_data.y = TABS_Y + 105
view1.append(temp_data)

#fails
fails_label = Label(font, text="Fails:", color=0xE39300, scale=2)
fails_label.x = TABS_X
fails_label.y = TABS_Y + 140
view1.append(fails_label)

failed_data = Label(font, text="failed_data", color=0xE39300, scale=2)
failed_data.x = TABS_X + 150
failed_data.y = TABS_Y + 140
view1.append(failed_data)





text_hight = Label(font, text="M", color=0x03AD31)
# return a reformatted string with word wrapping using PyPortal.wrap_nicely
def text_box(target, top, string, max_chars):
    text = pyportal.wrap_nicely(string, max_chars)
    new_text = ""
    test = ""
    for w in text:
        new_text += '\n'+w
        test += 'M\n'
    text_hight.text = test  # Odd things happen without this
    glyph_box = text_hight.bounding_box
    target.text = ""  # Odd things happen without this
    target.y = int(glyph_box[3]/2)+top
    target.text = new_text

# ---------- Display Buttons ------------- #
# Default button styling:
BUTTON_HEIGHT = 40
BUTTON_WIDTH = 80

# We want three buttons across the top of the screen
TAPS_HEIGHT = 40
TAPS_WIDTH = int(screen_width/3)
TAPS_Y = 0

# We want two big buttons at the bottom of the screen
#BIG_BUTTON_HEIGHT = int(screen_height/3.2)
#BIG_BUTTON_WIDTH = int(screen_width/2)
#BIG_BUTTON_Y = int(screen_height-BIG_BUTTON_HEIGHT)

# This group will make it easy for us to read a button press later.
buttons = []

# Main User Interface Buttons
button_view1 = Button(x=0, y=0,
                      width=TAPS_WIDTH, height=TAPS_HEIGHT,
                      label="AIO", label_font=font, label_color=0xff7e00,
                      fill_color=0x5c5b5c, outline_color=0x767676,
                      selected_fill=0x1a1a1a, selected_outline=0x2e2e2e,
                      selected_label=0x525252)
buttons.append(button_view1)  # adding this button to the buttons group

button_view2 = Button(x=TAPS_WIDTH, y=0,
                      width=TAPS_WIDTH, height=TAPS_HEIGHT,
                      label="Weather", label_font=font, label_color=0xff7e00,
                      fill_color=0x5c5b5c, outline_color=0x767676,
                      selected_fill=0x1a1a1a, selected_outline=0x2e2e2e,
                      selected_label=0x525252)
buttons.append(button_view2)  # adding this button to the buttons group

button_view3 = Button(x=TAPS_WIDTH*2, y=0,
                      width=TAPS_WIDTH, height=TAPS_HEIGHT,
                      label="Graphs", label_font=font, label_color=0xff7e00,
                      fill_color=0x5c5b5c, outline_color=0x767676,
                      selected_fill=0x1a1a1a, selected_outline=0x2e2e2e,
                      selected_label=0x525252)
buttons.append(button_view3)  # adding this button to the buttons group

#button_switch = Button(x=0, y=BIG_BUTTON_Y,
                       #width=BIG_BUTTON_WIDTH, height=BIG_BUTTON_HEIGHT,
                       #label="Switch", label_font=font, label_color=0xff7e00,
                       #fill_color=0x5c5b5c, outline_color=0x767676,
                       #selected_fill=0x1a1a1a, selected_outline=0x2e2e2e,
                       #selected_label=0x525252)
#buttons.append(button_switch)  # adding this button to the buttons group

#button_2 = Button(x=BIG_BUTTON_WIDTH, y=BIG_BUTTON_Y,
                  #width=BIG_BUTTON_WIDTH, height=BIG_BUTTON_HEIGHT,
                  #label="Button", label_font=font, label_color=0xff7e00,
                  #fill_color=0x5c5b5c, outline_color=0x767676,
                  #selected_fill=0x1a1a1a, selected_outline=0x2e2e2e,
                  #selected_label=0x525252)
#buttons.append(button_2)  # adding this button to the buttons group

# Add all of the main buttons to the splash Group
for b in buttons:
    splash.append(b)



#pylint: disable=global-statement
def switch_view(what_view):
    global view_live
    if what_view == 1:
        hideLayer(splash,view2)
        hideLayer(splash,view3)
        hideLayer(background,weather_group)
        button_view1.selected = False
        button_view2.selected = True
        button_view3.selected = True
        showLayer(splash, view1)
        view_live = 1
        print("View1 On")
    elif what_view == 2:
        # global icon
        hideLayer(splash,view1)
        hideLayer(splash,view3)
        button_view1.selected = True
        button_view2.selected = False
        button_view3.selected = True
        showLayer(background,weather_group)
        showLayer(splash,view2)
        view_live = 2
        print("View2 On")
    else:
        hideLayer(splash,view1)
        hideLayer(splash,view2)
        hideLayer(background, weather_group)
        button_view1.selected = True
        button_view2.selected = True
        button_view3.selected = False
        showLayer(splash, view3)
        view_live = 3
        print("View3 On")
#pylint: enable=global-statement

# Set veriables and startup states
switch_view(1)

view_live = 1
board.DISPLAY.show(splash)
gfx = OpenWeather_Graphics(view2, am_pm=False, celsius=True)

# ------------- Code Loop ------------- #
while True:
    touch = ts.touch_point
    gc.collect()
    if adt:  # Only if we have the temperature sensor
        tempC = adt.temperature
    else:  # No temperature sensor
        tempC = microcontroller.cpu.temperature

    tempF = tempC * 1.8 + 32
    if (not weather_refresh) or (time.monotonic() - weather_refresh) > 600:
        gc.collect()
        weather_refresh = time.monotonic()
        try:
            value = requests.get(DATA_SOURCE)
            gfx.display_weather(value,weather_group)
            value = {}
            gc.collect()

            #TEMP
            AIO_temp = requests.get(TEMP_URL)
            with open("/sd/temp.json","w") as df:
                print(json.dumps(AIO_temp.json()['data']))
                df.write(json.dumps(AIO_temp.json()['data']))
            AIO_temp = {}
            gc.collect()

            #PERCENT
            AIO_percent = requests.get(PERCENT_URL)
            with open("/sd/percent.json","w") as df:
                print(json.dumps(AIO_percent.json()['data']))
                df.write(json.dumps(AIO_percent.json()['data']))
            AIO_percent = {}
            gc.collect()

            #VOLTAGE
            AIO_voltage = requests.get(VOLTAGE_URL)
            with open("/sd/voltage.json","w") as df:
                print(json.dumps(AIO_voltage.json()['data']))
                df.write(json.dumps(AIO_voltage.json()['data']))
            AIO_voltage = {}
            gc.collect()

            #CURRENT
            AIO_current = requests.get(CURRENT_URL)
            with open("/sd/current.json","w") as df:
                print(json.dumps(AIO_current.json()['data']))
                df.write(json.dumps(AIO_current.json()['data']))
            AIO_current = {}
            gc.collect()

            #FAILS
            AIO_fails = requests.get(FAILS_URL)
            with open("/sd/wifi.json","w") as df:
                print(json.dumps(AIO_fails.json()['data']))
                df.write(json.dumps(AIO_fails.json()['data']))
            AIO_fails = {}
            gc.collect()



            try:
                with open("/sd/temp.json","r") as df:
                    temp_data.text = f"{json.loads(df.read())[1][-1]:.2}"
            except:
                temp_data.text = "NoD"
            try:
                with open("/sd/percent.json","r") as df:
                    percent_data.text = f"{json.loads(df.read())[1][-1]:.2}"
            except:
                percent_data.text = "NoD"
            try:
                with open("/sd/voltage.json","r") as df:
                    voltage_data.text = f"{json.loads(df.read())[1][-1]:.4}"
            except:
                voltage_data.text = "NoD"
            try:
                with open("/sd/current.json","r") as df:
                    current_data.text = f"{json.loads(df.read())[1][-1]:.5}"
            except:
                current_data.text = "NoD"
            try:
                with open("/sd/wifi.json","r") as df:
                    failed_data.text = f"{json.loads(df.read())[1][-1]:.2}".strip('.')
            except:
                failed_data.text = "NoD"
            #dict = {}
        except RuntimeError as e:
                print("Some error occured, retrying! -", e)
                continue
    print(gc.mem_free())

    # ------------- Handle Button Press Detection  ------------- #
    if touch:  # Only do this if the screen is touched
        # loop with buttons using enumerate() to number each button group as i
        for i, b in enumerate(buttons):
            if b.contains(touch):  # Test each button to see if it was pressed
                print('button%d pressed' % i)
                if i == 0 and view_live != 1:  # only if view1 is visable
                    switch_view(1)
                    while ts.touch_point:
                        pass
                if i == 1 and view_live != 2:  # only if view2 is visable
                    switch_view(2)
                    while ts.touch_point:
                        pass
                if i == 2 and view_live != 3:  # only if view3 is visable
                    switch_view(3)
                    while ts.touch_point:
                        pass