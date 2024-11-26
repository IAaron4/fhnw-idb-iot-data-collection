#-------------------------------------Import-Libraries-----------------------------------
# Libraries
import board # type: ignore
import time
import lib.adafruit_dht as adafruit_dht
import analogio
import digitalio

from lib.adafruit_esp32spi import adafruit_esp32spi, adafruit_esp32spi_socketpool
import lib.adafruit_requests as adafruit_requests
import lib.adafruit_connection_manager as adafruit_connection_manager
# LED library and display
import busio
from lib.ChainableLED import ChainableLED
from lib.GroveUltraSonicRangers import GroveUltrasonicRanger
from lib import adafruit_minimqtt, tm1637lib

# config file
import config

#-------------------------------------Hardware-Setup-------------------------------------
#-------------------------------------Sensor-Setup---------------------------------------
# setup: button sensor
sensor_button = digitalio.DigitalInOut(board.A0) # nRF52840, Grove A0
sensor_button.direction = digitalio.Direction.INPUT
sensor_button.pull = digitalio.Pull.UP

# setup: temperature and humidity sensor
dht = adafruit_dht.DHT11(board.A4)  # nRF52840, Grove A4

# setup: light sensor
sensor_light = analogio.AnalogIn(board.A2) # nRF52840, Grove A2

# setup: ultrasonic rangers sensor
sonar = GroveUltrasonicRanger(board.RX)

#-------------------------------------Actuator-Setup------------------------------------
# setup: red default LED on board
led = digitalio.DigitalInOut(board.RED_LED)  # general-purpose RED LED
led.direction = digitalio.Direction.OUTPUT

# setup: RGB-LED
CLK_PIN = board.D5 # nRF5840, Grove D2
DATA_PIN = board.D6  # nRF5840, data pin
NUMBER_OF_LEDS = 1

rgb_led = ChainableLED(CLK_PIN, DATA_PIN, NUMBER_OF_LEDS)
# set color of rgb_led to red
rgb_led.setColorRGB(0, 96, 96, 96)

# setup: display
display = tm1637lib.Grove4DigitDisplay(board.D9, board.D10) # nRF52840 D9, D10, Grove D4

# setup: buzzer
actuator = digitalio.DigitalInOut(board.SCL) # nRF52840, Grove SCL
actuator.direction = digitalio.Direction.OUTPUT

# FeatherWing ESP32 AirLift, nRF52840
cs = digitalio.DigitalInOut(board.D13)
rdy = digitalio.DigitalInOut(board.D11)
rst = digitalio.DigitalInOut(board.D12)

spi = busio.SPI(board.SCK, board.MOSI, board.MISO)
esp = adafruit_esp32spi.ESP_SPIcontrol(spi, cs, rdy, rst)

#-------------------------------------Wlan-Setup---------------------------------------
# set wifi ssid, password
WIFI_SSID = config.WIFI_NAME
WIFI_PASSWORD = config.WIFI_PW

# ThingSpeak settings
TS_WRITE_API_KEY = config.API_KEY
TS_HTTP_SERVER = "api.thingspeak.com"
TS_MQTT_BROKER = config.TS_MQTT_BROKER

# while loop for wlan connection
while not esp.is_connected:
    print("\nConnecting to Wi-Fi...")
    try:
        esp.connect_AP(WIFI_SSID, WIFI_PASSWORD)
        rgb_led.setColorRGB(0, 0, 255, 0)
    except ConnectionError as e:
        print("Cannot connect to Wi-Fi", e)
        rgb_led.setColorRGB(0, 255, 0, 0)
        continue

# print connection status
print("Wi-Fi connected to", str(esp.ap_info.ssid, "utf-8"))
print("IP address", esp.pretty_ip(esp.ip_address))

# Initialize HTTP POST client
pool = adafruit_connection_manager.get_radio_socketpool(esp)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(esp)
requests = adafruit_requests.Session(pool, ssl_context)

# print microcontroller status
print("Successfull connected, press button to start measurements")

# setup server url to ThingSpeak
post_url = "https://" + TS_HTTP_SERVER + "/update"

#-------------------------------------measurement-functions-------------------------------------
# measurement of all sensors
def measure_all():
    """
    Measure temperature, humidity, light value, distance to next wall and voltage.

    Returns:
        A tuple containing the measured values for temperature, humidity, light value, distance, and voltage.
    """
    # Read the temperature and convert it to integer
    temperature = int(round(dht.temperature))

    # Read the humidity and convert it to integer
    humidity = int(round(dht.humidity))

    # Read distance from ultrasonic rangers
    distance = int(round(sonar.get_distance()))

    # Read the light_value and voltage and convert it to integer
    light_value = sensor_light.value
    voltage = round((light_value * 3.3) / 65536)

    return temperature, humidity, distance, light_value, voltage

# # create function for sending measurment to ThingSpeak
def send_to_thingspeak(api_key, temperature, humidity, distance, light_value, voltage):
    """
    Sends the provided temperature, humidity, light value, and voltage readings to the specified ThingSpeak channel
    using the provided API key.

    api_key: str, the ThingSpeak API key
    temperature: int, the temperature reading
    humidity: int, the humidity reading
    distance: float, the distance value reading
    light_value: int, the light value reading
    voltage: int, the voltage reading
    """
    try:
        # Create payload
        payload = "api_key=" + api_key + \
                  "&field1=" + str(temperature) + \
                  "&field2=" + str(humidity) + \
                  "&field3=" + str(distance) + \
                  "&field4=" + str(light_value) + \
                  "&field5=" + str(voltage)

        # Send a single message
        response = requests.post(post_url, data=payload)

        # change rgb color to yellow
        time.sleep(0.5)
        rgb_led.setColorRGB(0, 255, 255, 0)

        # Print the http status code; should be 200
        print("Data successfully transported to ThingSpeak, response status: " + str(response.status_code))

        # change rgb color to blue
        time.sleep(0.5)
        rgb_led.setColorRGB(0, 0, 0, 255)
        response.close()

    except RuntimeError as e:
        # change rgb color to red
        time.sleep(0.5)
        rgb_led.setColorRGB(0, 255, 0, 0)
        # Reading doesn't always work! Just print error and we'll try again
        print("|Timestamp {:d}:{:02d}:{:02d} | Temperature {:g} | Humidity {:g} | Distance {:g} | Light_value {:g} | Voltage {:g} |"
        .format(t.tm_hour, t.tm_min, t.tm_sec, -1, -1, -1, -1, -1))

#-------------------------------------Receive-Data-Functions-------------------------------------
def handle_connect(client, userdata, flags, rc):
    print("Connected to {0}".format(client.broker))
    client.subscribe('iot-data-collection')

def handle_subscribe(client, userdata, topic, granted_qos):
    print("Subscribed to {0} with QOS {1}".format(topic, granted_qos))

def handle_message(client, topic, message):
    print("Received on {0}: {1}".format(topic, message))

    # display.show("H001")
    # display.set_colon(True)
    # time.sleep(1)

    # actuator.value = True
    # led.value = True
    # time.sleep(0.1)

    # actuator.value = False
    # led.value = False
    # print("Akusignal")

    # # The first parameter: NUMBER_OF_LEDS - 1; Other parameters: the RGB values.
    # rgb_led.setColorRGB(0, 255, 0, 0) # Rot
    # time.sleep(2)
    # rgb_led.setColorRGB(0, 0, 255, 0) # Gruen
    # time.sleep(1)
    # rgb_led.setColorRGB(0, 0, 0, 255) # Blau
    # time.sleep(1)

def receive_thinkspeak_mqtt():
    mqtt_client = adafruit_minimqtt.MQTT(broker=TS_MQTT_BROKER, is_ssl=False)

    # Set callback handlers
    mqtt_client.on_connect = handle_connect
    mqtt_client.on_subscribe = handle_subscribe
    mqtt_client.on_message = handle_message

    print("\nConnecting to {0}".format(TS_MQTT_BROKER))
    mqtt_client.connect()

    while True:
        mqtt_client.loop()

def receive_and_display_measurements_mqtt_sub():
    receive_thinkspeak_mqtt()


#-------------------------------------Measurments-Parameters-------------------------------------
# Constants for measurements
dht_INTERVAL = 5

# Variable for measurement start
measurement_on = False

# index_display
index_display = 0

# String format for measurments
measurement_format = "|Timestamp {:d}:{:02d}:{:02d} | Temperature {:g} | Humidity {:g} | Distance {:g} | Light_value {:g} | Voltage {:g} |"

#-------------------------------------------Main-Loop---------------------------------------------
# Main loop
while True:
    # check if button is pressed once
    if sensor_button.value == True and not measurement_on:

        # start measurment
        measurement_on = True

        while measurement_on:
            # Take a measurement
            start = time.time()
            t = time.localtime(start)

            # call measure_all() funktion to get measured values
            temperature, humidity, distance, light_value, voltage = measure_all()

            # create a  list of measurement
            measurements = [str(temperature) + " C", str(humidity) + " H", f"{distance:03}" + "D", str(light_value // 100) + "L", str(voltage // 1) + "V"]

            # select measurment by index_display
            value = measurements[index_display]

            # display them on hardware
            display.show(value)
            # check numb of index_display
            if index_display == 3:
            # reset index_display to 0
                index_display = 0
            else:
                # increment index_display by 1
                index_display += 1

            # Print timestamp, temperatur, humidity
            print(measurement_format.format(t.tm_hour, t.tm_min, t.tm_sec, temperature, humidity, distance, light_value, voltage))

            # try to send data to thingspeak
            send_to_thingspeak(TS_WRITE_API_KEY, temperature, humidity, distance, light_value, voltage)

            end = time.time()
            # Wait for the remaining
            time.sleep(dht_INTERVAL)


            #receive_and_display_measurements_mqtt_sub()

# --------------------------------------END----------------------------------------------------------------------------------
