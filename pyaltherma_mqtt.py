import asyncio
import aiohttp
import json
import os
import socket
import random
import signal
import time
import uuid
import paho.mqtt.client as mqtt
from pyaltherma.comm import DaikinWSConnection
from pyaltherma.controllers import AlthermaController, AlthermaClimateControlController, AlthermaUnitController, \
    AlthermaWaterTankController


mqtt_client_id = 'pyaltherma_mqtt/' + str(uuid.uuid4())
mqtt_host = os.environ.get('PYALTHERMA_MQTT_HOST', 'localhost')
mqtt_port = os.environ.get('PYALTHERMA_MQTT_PORT', 1883)
mqtt_username = os.environ.get('PYALTHERMA_MQTT_USERNAME')
mqtt_password = os.environ.get('PYALTHERMA_MQTT_PASSWORD')
mqtt_topic_prefix = os.environ.get('PYALTHERMA_MQTT_TOPIC_PREFIX', 'pyaltherma')
mqtt_onetopic = os.environ.get('PYALTHERMA_MQTT_ONETOPIC')
mqtt_topic_prefix_set = '%s/set' % mqtt_topic_prefix
mqtt_topic_prefix_state = '%s/state' % mqtt_topic_prefix
mqtt_topic_onetopic = '%s/state/%s' % (mqtt_topic_prefix, mqtt_onetopic)
poll_timeout = os.environ.get('PYALTHERMA_POLL_TIMEOUT', 5)
daikin_host = os.environ.get('PYALTHERMA_DAIKIN_HOST')
daikin_device_mock = os.environ.get('PYALTHERMA_DAIKIN_DEVICE_MOCK')


class AlthermaControllerMock():
    async def get_current_state(self):
        return {}

    def __getattr__(self, attr):
        return {
            'hot_water_tank': AlthermaControllerMock(),
            'climate_control': AlthermaControllerMock(),
            'is_turned_on': lambda: bool(random.randrange(2)),
            'tank_temperature': random.randrange(30, 60, 1),
            'target_temperature': random.randrange(35, 65, 5),
            'powerful': bool(random.randrange(2)),
            'indoor_temperature': random.randrange(22, 24, 1),
            'climate_control_heating_configuration': random.randrange(1, 3, 1),
            'climate_control_cooling_configuration': random.randrange(1, 2, 1),
            'operation_mode': ['auto', 'cooling', 'heating', 'heating_day', 'heating_night'][random.randrange(0, 5, 1)],
            'leaving_water_temperature_current': random.randrange(28, 35, 1),
            'leaving_water_temperature_offset_heating': random.randrange(-5, 5, 1),
            'leaving_water_temperature_offset_cooling': random.randrange(-5, 5, 1),
            'leaving_water_temperature_offset_auto': random.randrange(-5, 5, 1),
            'leaving_water_temperature_heating': random.randrange(25, 45, 1),
            'leaving_water_temperature_cooling': random.randrange(16, 23, 1),
            'leaving_water_temperature_auto': random.randrange(16, 45, 1),
            'turn_on': lambda: None,
            'turn_off': lambda: None,
            'set_target_temperature': lambda x: None,
            'set_powerful': lambda x: None,
            'set_operation_mode': lambda x: None,
            'set_leaving_water_temperature_offset_heating': lambda x: None,
            'set_leaving_water_temperature_offset_cooling': lambda x: None,
            'set_leaving_water_temperature_offset_auto': lambda x: None,
            'set_leaving_water_temperature_heating': lambda x: None,
            'set_leaving_water_temperature_cooling': lambda x: None,
            'set_leaving_water_temperature_auto': lambda x: None,
        }[attr]


class AsyncioHelper:
    def __init__(self, loop, client):
        self.loop = loop
        self.client = client
        self.client.on_socket_open = self.on_socket_open
        self.client.on_socket_close = self.on_socket_close
        self.client.on_socket_register_write = self.on_socket_register_write
        self.client.on_socket_unregister_write = self.on_socket_unregister_write

    def on_socket_open(self, client, userdata, sock):
        def cb():
            client.loop_read()
        self.loop.add_reader(sock, cb)
        self.misc = self.loop.create_task(self.misc_loop())

    def on_socket_close(self, client, userdata, sock):
        self.loop.remove_reader(sock)
        self.misc.cancel()

    def on_socket_register_write(self, client, userdata, sock):
        def cb():
            client.loop_write()
        self.loop.add_writer(sock, cb)

    def on_socket_unregister_write(self, client, userdata, sock):
        self.loop.remove_writer(sock)

    async def misc_loop(self):
        while self.client.loop_misc() == mqtt.MQTT_ERR_SUCCESS:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break


class AsyncMqtt:
    def __init__(self, loop):
        self.loop = loop

    def on_connect(self, client, userdata, flags, reason_code, properties):
        client.subscribe('%s/#' % mqtt_topic_prefix_set)

    def on_message(self, client, userdata, msg):
        if self.got_message and msg.topic.startswith('%s/' % mqtt_topic_prefix_set):
            self.got_message.set_result(msg)

    def on_disconnect(self, client, userdata, flags, reason_code, properties):
        self.disconnected.set_result(reason_code)

    async def handle_message(self, topic, payload):
        if topic == 'dhw_power':
            if payload.upper() == 'ON' or payload == '1':
                self.daikin_device.hot_water_tank.turn_on()
            if payload.upper() == 'off' or payload == '0':
                self.daikin_device.hot_water_tank.turn_off()
        elif topic == 'dhw_target_temp':
            self.daikin_device.hot_water_tank.set_target_temperature(float(payload))
        elif topic == 'dhw_powerful':
            if payload.upper() == 'ON' or payload == '1':
                self.daikin_device.hot_water_tank.set_powerful(True)
            if payload.upper() == 'OFF' or payload == '0':
                self.daikin_device.hot_water_tank.set_powerful(False)
        elif topic == 'climate_control_power':
            if payload.upper() == 'ON' or payload == '1':
                self.daikin_device.climate_control.turn_on()
            if payload.upper() == 'OFF' or payload == '0':
                self.daikin_device.climate_control.turn_off()
        elif topic == 'climate_control_mode':
            self.daikin_device.climate_control.set_operation_mode(payload)
        elif topic == 'leaving_water_temp_offset_heating':
            self.daikin_device.climate_control.set_leaving_water_temperature_offset_heating(round(float(payload)))
        elif topic == 'leaving_water_temp_offset_cooling':
            self.daikin_device.climate_control.set_leaving_water_temperature_offset_cooling(round(float(payload)))
        elif topic == 'leaving_water_temp_offset_auto':
            self.daikin_device.climate_control.set_leaving_water_temperature_offset_auto(round(float(payload)))
        elif topic == 'leaving_water_temp_heating':
            self.daikin_device.climate_control.set_leaving_water_temperature_heating(round(float(payload)))
        elif topic == 'leaving_water_temp_cooling':
            self.daikin_device.climate_control.set_leaving_water_temperature_cooling(round(float(payload)))
        elif topic == 'leaving_water_temp_auto':
            self.daikin_device.climate_control.set_leaving_water_temperature_auto(round(float(payload)))

    async def publish_loop(self):
        while True:
            start_time = time.time()
            await self.daikin_device.get_current_state()
            messages = {
                'dhw_power': 'ON' if self.daikin_device.hot_water_tank.is_turned_on() else 'OFF',
                'dhw_temp': str(self.daikin_device.hot_water_tank.tank_temperature),
                'dhw_target_temp': str(self.daikin_device.hot_water_tank.target_temperature),
                'dhw_powerful': 'ON' if self.daikin_device.hot_water_tank.powerful else 'OFF',
                'indoor_temp': str(self.daikin_device.climate_control.indoor_temperature),
                'climate_control_heating_config': self.daikin_device.climate_control.climate_control_heating_configuration,
                'climate_control_cooling_config': self.daikin_device.climate_control.climate_control_cooling_configuration,
                'climate_control_power': 'ON' if self.daikin_device.climate_control.is_turned_on() else 'OFF',
                'climate_control_mode': str(self.daikin_device.climate_control.operation_mode),
                'leaving_water_temp_current': str(self.daikin_device.climate_control.leaving_water_temperature_current),
                'leaving_water_temp_offset_heating': str(self.daikin_device.climate_control.leaving_water_temperature_offset_heating),
                'leaving_water_temp_offset_cooling': str(self.daikin_device.climate_control.leaving_water_temperature_offset_cooling),
                'leaving_water_temp_offset_auto': str(self.daikin_device.climate_control.leaving_water_temperature_offset_auto),
                'leaving_water_temp_heating': str(self.daikin_device.climate_control.leaving_water_temperature_heating),
                'leaving_water_temp_cooling': str(self.daikin_device.climate_control.leaving_water_temperature_cooling),
                'leaving_water_temp_auto': str(self.daikin_device.climate_control.leaving_water_temperature_auto),
            }
            if mqtt_onetopic:
                self.client.publish(mqtt_topic_onetopic, json.dumps(messages))
            else:
                for topic, payload in messages.items():
                    self.client.publish('%s/%s' % (mqtt_topic_prefix_state, topic), payload)
            await asyncio.sleep(start_time - time.time() + int(poll_timeout))

    async def main(self):
        self.disconnected = self.loop.create_future()
        self.got_message = None
        # connecto to mqtt broker
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=mqtt_client_id)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        if mqtt_username:
            self.client.username_pw_set(mqtt_username, mqtt_password)
        AsyncioHelper(self.loop, self.client)
        self.client.connect(mqtt_host, port=mqtt_port, keepalive=60)
        self.client.socket().setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2048)
        # connect to daikin api
        async with aiohttp.ClientSession() as session:
            if daikin_device_mock:
                self.daikin_device = AlthermaControllerMock()
            else:
                connection = DaikinWSConnection(session, daikin_host)
                self.daikin_device = AlthermaController(connection)
                await self.daikin_device.discover_units()
            # publish messages
            self.loop.create_task(self.publish_loop())
            # handle incoming messages
            while True:
                try:
                    self.got_message = self.loop.create_future()
                    msg = await self.got_message
                    if msg.topic.startswith('%s/' % mqtt_topic_prefix_set):
                        await self.handle_message(msg.topic.replace('%s/' % mqtt_topic_prefix_set, ''), msg.payload.decode())
                    self.got_message = None
                except asyncio.exceptions.CancelledError:
                    break
            if not daikin_device_mock:
                await connection.close()
        self.client.disconnect()
        await self.disconnected


def cancel_tasks():
    for task in asyncio.all_tasks():
        task.cancel()


loop = asyncio.new_event_loop()
for sig in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(sig, cancel_tasks)
loop.run_until_complete(AsyncMqtt(loop).main())
loop.close()
