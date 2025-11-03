import asyncio
import requests
import socket
from datetime import datetime, timedelta
from pymodbus.server import ModbusTcpServer
from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext
from pymodbus.datastore import ModbusSequentialDataBlock
from pymodbus.device import ModbusDeviceIdentification

# --- API Settings ---
API_KEY = "25494b2dafc5219903db155852e77031"
LAT = 32.051
LON = 34.856
WEATHER_URL = f"http://api.openweathermap.org/data/2.5/forecast?lat={LAT}&lon={LON}&appid={API_KEY}&units=metric"

# --- Decision Parameters ---
CLOUD_THRESHOLD = 22
TEMP_THRESHOLD = 24
SOLAR_WEATHER_CODES = ['clear sky', 'few clouds']

# --- Modbus Setup ---
store = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, [0]*100))
context = ModbusServerContext(slaves=store, single=True)

identity = ModbusDeviceIdentification()
identity.VendorName = 'Schneider'
identity.ProductCode = 'PLC'
identity.VendorUrl = 'http://example.com'
identity.ProductName = 'Modbus Server'
identity.ModelName = 'PythonModbus'
identity.MajorMinorRevision = '1.0'

# --- Weather Logic ---
def get_tomorrow_weather_and_decision():
    print("--- Reading Tomorrow's Noon Forecast ---")
    try:
        tomorrow = datetime.now() + timedelta(days=1)
        target_time_str = tomorrow.strftime('%Y-%m-%d 12:00:00')

        response = requests.get(WEATHER_URL)
        response.raise_for_status()
        data = response.json()

        target_forecast = None
        for item in data.get('list', []):
            if item.get('dt_txt') == target_time_str:
                target_forecast = item
                break

        if not target_forecast and len(data.get('list', [])) >= 8:
            target_forecast = data['list'][8]
        elif not target_forecast:
            print("No forecast found. Fail-safe ON.")
            return 1, 100, 15, 99

        cloud_percent = target_forecast.get('clouds', {}).get('all', 100)
        temperature = target_forecast.get('main', {}).get('temp', 15)
        description = target_forecast.get('weather', [{}])[0].get('description', 'heavy rain').lower()

        is_low_cloud = cloud_percent <= CLOUD_THRESHOLD
        is_solar_favorable = description in SOLAR_WEATHER_CODES
        is_warm = temperature >= TEMP_THRESHOLD

        solar_is_sufficient = is_low_cloud and is_solar_favorable and is_warm
        decision_flag = 0 if solar_is_sufficient else 1

        weather_code = {
            'clear sky': 1,
            'few clouds': 2,
            'scattered clouds': 3,
            'broken clouds': 4,
            'shower rain': 5,
            'rain': 6,
            'thunderstorm': 7,
            'snow': 8,
            'mist': 9
        }.get(description, 99)

        print(f"Decision: {decision_flag}, Cloud: {cloud_percent}, Temp: {temperature}, Desc: {description}")
        return decision_flag, cloud_percent, temperature, weather_code

    except Exception as e:
        print(f"Error: {e}")
        return 1, 100, 15, 99

# --- Daily Update Loop ---
async def update_weather_daily():
    while True:
        now = datetime.now()
        if now.hour == 3:
            print("⏰ Running daily weather update...")
            decision, cloud, temp, code = get_tomorrow_weather_and_decision()
            store.setValues(3, 30, [decision])
            store.setValues(3, 31, [int(cloud)])
            store.setValues(3, 32, [int(temp)])
            store.setValues(3, 33, [code])
            await asyncio.sleep(3600)  # Wait an hour to avoid duplicate run
        else:
            await asyncio.sleep(60)  # Check again in a minute

# --- Async Server ---
async def run_server():
    # Get local IP address
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    print(f"🌐 Server starting on IP: {local_ip}, port: 5020")

    server = ModbusTcpServer(context, identity=identity, address=("0.0.0.0", 5020), defer_start=True)
    await asyncio.gather(
        server.serve_forever(),
        update_weather_daily()
    )

if __name__ == "__main__":
    asyncio.run(run_server())