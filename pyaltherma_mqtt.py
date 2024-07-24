import asyncio
import aiohttp
import json
import logging
import os
import socket
import random
import signal
import time
import paho.mqtt.client as mqtt
from pyaltherma.comm import DaikinWSConnection
from pyaltherma.controllers import AlthermaController, AlthermaClimateControlController, AlthermaUnitController, \
    AlthermaWaterTankController


logger = logging.getLogger(__name__)


MQTT_CLIENT_ID = 'pyaltherma_mqtt'
MQTT_HOST = os.environ.get('PYALTHERMA_MQTT_HOST', 'localhost')
MQTT_PORT = os.environ.get('PYALTHERMA_MQTT_PORT', 1883)
MQTT_USERNAME = os.environ.get('PYALTHERMA_MQTT_USERNAME')
MQTT_PASSWORD = os.environ.get('PYALTHERMA_MQTT_PASSWORD')
MQTT_TOPIC_PREFIX = os.environ.get('PYALTHERMA_MQTT_TOPIC_PREFIX', 'pyaltherma')
MQTT_ONETOPIC = os.environ.get('PYALTHERMA_MQTT_ONETOPIC')
MQTT_TOPIC_PREFIX_SET = '%s/set' % MQTT_TOPIC_PREFIX
MQTT_TOPIC_PREFIX_STATE = '%s/state' % MQTT_TOPIC_PREFIX
MQTT_TOPIC_ONETOPIC = '%s/state/%s' % (MQTT_TOPIC_PREFIX, MQTT_ONETOPIC)
POLL_TIMEOUT = os.environ.get('PYALTHERMA_POLL_TIMEOUT', 5)
DAIKIN_HOST = os.environ.get('PYALTHERMA_DAIKIN_HOST')
DAIKIN_DEVICE_MOCK = os.environ.get('PYALTHERMA_DAIKIN_DEVICE_MOCK')


class AlthermaControllerMock():
    def __getattr__(self, attr):
        return {
            'ws_connection': AlthermaControllerMock(),
            'close': lambda: asyncio.sleep(0),
            'get_current_state': lambda: asyncio.sleep(0),
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
    def __init__(self, loop, mqtt_client):
        self.loop = loop
        self.mqtt_client = mqtt_client
        self.mqtt_client.on_socket_open = self.on_socket_open
        self.mqtt_client.on_socket_close = self.on_socket_close
        self.mqtt_client.on_socket_register_write = self.on_socket_register_write
        self.mqtt_client.on_socket_unregister_write = self.on_socket_unregister_write

    def on_socket_open(self, mqtt_client, userdata, sock):
        def cb():
            mqtt_client.loop_read()
        self.loop.add_reader(sock, cb)
        self.misc = self.loop.create_task(self.misc_loop())

    def on_socket_close(self, mqtt_client, userdata, sock):
        self.loop.remove_reader(sock)
        self.misc.cancel()

    def on_socket_register_write(self, mqtt_client, userdata, sock):
        def cb():
            mqtt_client.loop_write()
        self.loop.add_writer(sock, cb)

    def on_socket_unregister_write(self, mqtt_client, userdata, sock):
        self.loop.remove_writer(sock)

    async def misc_loop(self):
        while self.mqtt_client.loop_misc() == mqtt.MQTT_ERR_SUCCESS:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break


class MqttDisconnectError(Exception):
    pass


class AsyncMqtt:
    def __init__(self, loop):
        self.loop = loop

    def on_connect(self, client, userdata, connect_flags, reason_code, properties):
        self.mqtt_conn_future.set_result(reason_code)

    def on_message(self, client, userdata, msg):
        if self.main_future:
            self.main_future.set_result(msg)

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.mqtt_disconn_future.set_result(reason_code)
        if self.main_future and not self.main_future.done():
            self.main_future.set_exception(MqttDisconnectError(reason_code))

    def handle_message(self, topic, payload):
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

    def publish_messages(self):
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
        if MQTT_ONETOPIC:
            self.mqtt_client.publish(MQTT_TOPIC_ONETOPIC, json.dumps(messages))
        else:
            for topic, payload in messages.items():
                self.mqtt_client.publish('%s/%s' % (MQTT_TOPIC_PREFIX_STATE, topic), payload)

    def task_done_callback(self, task):
        try:
            self.main_future.set_exception(task.exception() or asyncio.CancelledError)
        except asyncio.CancelledError:
            pass

    async def publish_loop(self):
        while True:
            start_time = time.time()
            await self.daikin_device.get_current_state()
            self.publish_messages()
            await asyncio.sleep(start_time - time.time() + int(POLL_TIMEOUT))

    async def main_loop(self):
        while True:
            try:
                self.main_future = self.loop.create_future()
                msg = await self.main_future
                if msg.topic.startswith('%s/' % MQTT_TOPIC_PREFIX_SET):
                    self.handle_message(msg.topic.replace('%s/' % MQTT_TOPIC_PREFIX_SET, ''), msg.payload.decode())
                self.main_future = None
            except asyncio.CancelledError:
                break
            except MqttDisconnectError as e:
                logger.error('MQTT disconnected: %s' % e)
                break

    async def main(self):
        self.main_future = None
        self.mqtt_conn_future = self.loop.create_future()
        self.mqtt_disconn_future = self.loop.create_future()
        # connecto to mqtt broker
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.on_disconnect = self.on_disconnect
        if MQTT_USERNAME:
            self.mqtt_client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        AsyncioHelper(self.loop, self.mqtt_client)
        self.mqtt_client.connect(MQTT_HOST, port=MQTT_PORT, keepalive=60)
        self.mqtt_client.socket().setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2048)
        await self.mqtt_conn_future
        self.mqtt_client.subscribe('%s/#' % MQTT_TOPIC_PREFIX_SET)
        # connect to daikin api
        if DAIKIN_DEVICE_MOCK:
            self.daikin_device = AlthermaControllerMock()
        else:
            self.daikin_device = AlthermaController(DaikinWSConnection(aiohttp.ClientSession(), DAIKIN_HOST))
            await self.daikin_device.discover_units()
        # publish messages
        publish_task = self.loop.create_task(self.publish_loop())
        publish_task.add_done_callback(self.task_done_callback)
        # main loop
        await self.main_loop()
        # graceful shutdown
        publish_task.cancel()
        await self.daikin_device.ws_connection.close()
        self.mqtt_client.disconnect()
        await self.mqtt_disconn_future


loop = asyncio.new_event_loop()
for sig in (signal.SIGINT, signal.SIGTERM):
    loop.add_signal_handler(sig, lambda: [t.cancel() for t in asyncio.all_tasks()])
loop.run_until_complete(AsyncMqtt(loop).main())
loop.close()
