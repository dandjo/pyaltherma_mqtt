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
from pyaltherma.controllers import AlthermaController
from pyaltherma.const import ClimateControlMode


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
POLL_INTERVAL = os.environ.get('PYALTHERMA_POLL_INTERVAL', 5)
ALTHERMA_HOST = os.environ.get('PYALTHERMA_HOST')


class AsyncioHelper:
    def __init__(self, loop, mqttc):
        self.loop = loop
        self.mqttc = mqttc
        self.mqttc.on_socket_open = self.on_socket_open
        self.mqttc.on_socket_close = self.on_socket_close
        self.mqttc.on_socket_register_write = self.on_socket_register_write
        self.mqttc.on_socket_unregister_write = self.on_socket_unregister_write

    def on_socket_open(self, mqttc, userdata, sock):
        self.loop.add_reader(sock, lambda: mqttc.loop_read())
        self.misc = self.loop.create_task(self.misc_loop())

    def on_socket_close(self, mqttc, userdata, sock):
        self.loop.remove_reader(sock)
        self.misc.cancel()

    def on_socket_register_write(self, mqttc, userdata, sock):
        self.loop.add_writer(sock, lambda: mqttc.loop_write())

    def on_socket_unregister_write(self, mqttc, userdata, sock):
        self.loop.remove_writer(sock)

    async def misc_loop(self):
        while self.mqttc.loop_misc() == mqtt.MQTT_ERR_SUCCESS:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break


class PyalthermaException(Exception):
    pass


class PyalthermaMessenger:
    def __init__(self, loop, mqttc, altherma):
        self._loop = loop
        self.mqttc = mqttc
        self.mqttc.subscribe('%s/#' % MQTT_TOPIC_PREFIX_SET)
        self.altherma = altherma
        self.future = None

    async def loop(self):
        while True:
            try:
                await self.await_message()
            except asyncio.CancelledError:
                break
            except PyalthermaException as e:
                logger.warning('Messenger loop stopped: %s' % e)
                break

    async def await_message(self):
        self.future = self._loop.create_future()
        msg = await self.future
        if msg.topic.startswith('%s/' % MQTT_TOPIC_PREFIX_SET):
            topic = msg.topic.replace('%s/' % MQTT_TOPIC_PREFIX_SET, '')
            await self.handle_message(topic, msg.payload.decode())
        self.future = None

    def notify(self, msg):
        if self.future:
            self.future.set_result(msg)

    def stop(self, reason=None):
        if self.future and not self.future.done():
            self.future.set_exception(PyalthermaException(reason))

    async def handle_message(self, topic, payload):
        if topic == 'dhw_power':
            if payload.upper() == 'ON' or payload == '1':
                await self.altherma.hot_water_tank.turn_on()
            if payload.upper() == 'OFF' or payload == '0':
                await self.altherma.hot_water_tank.turn_off()
        elif topic == 'dhw_target_temp':
            await self.altherma.hot_water_tank.set_target_temperature(float(payload))
        elif topic == 'dhw_powerful':
            if payload.upper() == 'ON' or payload == '1':
                await self.altherma.hot_water_tank.set_powerful(True)
            if payload.upper() == 'OFF' or payload == '0':
                await self.altherma.hot_water_tank.set_powerful(False)
        elif topic == 'climate_control_power':
            if payload.upper() == 'ON' or payload == '1':
                await self.altherma.climate_control.turn_on()
            if payload.upper() == 'OFF' or payload == '0':
                await self.altherma.climate_control.turn_off()
        elif topic == 'climate_control_mode':
            await self.altherma.climate_control.set_operation_mode(ClimateControlMode(payload))
        elif topic == 'leaving_water_temp_offset_heating':
            await self.altherma.climate_control.set_leaving_water_temperature_offset_heating(round(float(payload)))
        elif topic == 'leaving_water_temp_offset_cooling':
            await self.altherma.climate_control.set_leaving_water_temperature_offset_cooling(round(float(payload)))
        elif topic == 'leaving_water_temp_offset_auto':
            await self.altherma.climate_control.set_leaving_water_temperature_offset_auto(round(float(payload)))
        elif topic == 'leaving_water_temp_heating':
            await self.altherma.climate_control.set_leaving_water_temperature_heating(round(float(payload)))
        elif topic == 'leaving_water_temp_cooling':
            await self.altherma.climate_control.set_leaving_water_temperature_cooling(round(float(payload)))
        elif topic == 'leaving_water_temp_auto':
            await self.altherma.climate_control.set_leaving_water_temperature_auto(round(float(payload)))

    async def publish_messages(self):
        await self.altherma.get_current_state()
        msgs = {
            'dhw_power': 'ON' if await self.altherma.hot_water_tank.is_turned_on else 'OFF',
            'dhw_temp': str(await self.altherma.hot_water_tank.tank_temperature),
            'dhw_target_temp': str(await self.altherma.hot_water_tank.target_temperature),
            'dhw_powerful': 'ON' if await self.altherma.hot_water_tank.powerful else 'OFF',
            'indoor_temp': str(await self.altherma.climate_control.indoor_temperature),
            'climate_control_heating_config': str(self.altherma.climate_control.climate_control_heating_configuration.value),
            'climate_control_cooling_config': str(self.altherma.climate_control.climate_control_cooling_configuration.value),
            'climate_control_power': 'ON' if await self.altherma.climate_control.is_turned_on else 'OFF',
            'climate_control_mode': str((await self.altherma.climate_control.operation_mode).value),
            'leaving_water_temp_current': str(await self.altherma.climate_control.leaving_water_temperature_current),
            'leaving_water_temp_offset_heating': str(await self.altherma.climate_control.leaving_water_temperature_offset_heating),
            'leaving_water_temp_offset_cooling': str(await self.altherma.climate_control.leaving_water_temperature_offset_cooling),
            'leaving_water_temp_offset_auto': str(await self.altherma.climate_control.leaving_water_temperature_offset_auto),
            'leaving_water_temp_heating': str(await self.altherma.climate_control.leaving_water_temperature_heating),
            'leaving_water_temp_cooling': str(await self.altherma.climate_control.leaving_water_temperature_cooling),
            'leaving_water_temp_auto': str(await self.altherma.climate_control.leaving_water_temperature_auto),
        }
        if MQTT_ONETOPIC:
            self.mqttc.publish(MQTT_TOPIC_ONETOPIC, json.dumps(msgs))
        else:
            for topic, payload in msgs.items():
                self.mqttc.publish('%s/%s' % (MQTT_TOPIC_PREFIX_STATE, topic), payload)


class PyalthermaPublisher:
    def __init__(self, loop, messenger):
        self._loop = loop
        self.messenger = messenger
        self.task = None

    async def loop(self):
        while True:
            try:
                start_time = time.time()
                await self.messenger.publish_messages()
                await asyncio.sleep(start_time - time.time() + int(POLL_INTERVAL))
            except asyncio.CancelledError:
                break

    def _on_task_done(self, task):
        if not self.messenger.future.done():
            self.messenger.future.set_exception(task.exception() or asyncio.CancelledError)

    def start(self):
        self.task = self._loop.create_task(self.loop())
        self.task.add_done_callback(self._on_task_done)

    def stop(self, reason=None):
        self.task.cancel()


class PyalthermaMqtt:
    def __init__(self, loop):
        self.loop = loop
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: [t.cancel() for t in asyncio.all_tasks(loop=loop)])

    def on_connect(self, client, userdata, connect_flags, reason_code, properties):
        self.connected_future.set_result(reason_code)

    def on_message(self, client, userdata, msg):
        if self.messenger:
            self.messenger.notify(msg)

    def on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        self.disconnected_future.set_result(reason_code)
        if self.publisher:
            self.publisher.stop(reason=reason_code)
        if self.messenger:
            self.messenger.stop(reason=reason_code)

    async def main(self):
        self.connected_future = self.loop.create_future()
        self.disconnected_future = self.loop.create_future()
        # connecto to mqtt broker
        self.mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=MQTT_CLIENT_ID)
        self.mqttc.on_connect = self.on_connect
        self.mqttc.on_message = self.on_message
        self.mqttc.on_disconnect = self.on_disconnect
        if MQTT_USERNAME:
            self.mqttc.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        AsyncioHelper(self.loop, self.mqttc)
        self.mqttc.connect(MQTT_HOST, port=MQTT_PORT, keepalive=60)
        self.mqttc.socket().setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 2048)
        await self.connected_future
        # connect to daikin api
        self.altherma = AlthermaController(DaikinWSConnection(aiohttp.ClientSession(), ALTHERMA_HOST))
        await self.altherma.discover_units()
        self.messenger = PyalthermaMessenger(self.loop, self.mqttc, self.altherma)
        # message publisher
        self.publisher = PyalthermaPublisher(self.loop, self.messenger)
        self.publisher.start()
        # messenger loop
        await self.messenger.loop()
        # graceful shutdown
        self.publisher.stop()
        await self.altherma.ws_connection.close()
        self.mqttc.disconnect()
        await self.disconnected_future


loop = asyncio.new_event_loop()
loop.run_until_complete(PyalthermaMqtt(loop).main())
loop.close()
