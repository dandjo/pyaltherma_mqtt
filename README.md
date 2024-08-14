# pyaltherma_mqtt
Provides a MQTT bridge for [pyaltherma](https://github.com/tadasdanielius/pyaltherma).

## Installation

All you have to do is to install the dependencies in your python environment.

```
$ pip install pyaltherma
$ pip install paho-mqtt
```

Before you start the script as a service, take a look at the configurable environment variables. Some of them are mandatory.

| ENV                            | Default value | Mandatory | Description                                                                  |
|--------------------------------|---------------|-----------|------------------------------------------------------------------------------|
| `PYALTHERMA_MQTT_HOST`         | localhost     | yes       | The host of the MQTT broker. Could be a hostename or IP.                     |
| `PYALTHERMA_MQTT_PORT`         | 1883          | no        | The port of the MQTT broker. For Mosquitto it is 1883 by default.            |
| `PYALTHERMA_MQTT_USERNAME`     | None          | no        | The username for the MQTT broker. If omitted, the password will not be used. |
| `PYALTHERMA_MQTT_PASSWORD`     | None          | no        | The password for the MQTT broker. Mandatory if username is set.              |
| `PYALTHERMA_MQTT_TOPIC_PREFIX` | pyaltherma    | no        | The prefix for all MQTT messages.                                            |
| `PYALTHERMA_MQTT_ONETOPIC`     | None          | no        | If set, a single message will be sent, with all properties as JSON.          |
| `PYALTHERMA_POLL_INTERVAL`     | 5             | no        | The inverval properties should be polled from the Daikin API.                |
| `PYALTHERMA_HOST`              | None          | yes       | The host of the Daikin controller. Must be the IP.                           |

Copy/paste template for environment file (e.g. `/etc/environment`):

```
PYALTHERMA_MQTT_HOST="localhost"
PYALTHERMA_MQTT_PORT="1883"
PYALTHERMA_MQTT_USERNAME="<replace_me_or_delete_line>"
PYALTHERMA_MQTT_PASSWORD="<replace_me_or_delete_line>"
PYALTHERMA_MQTT_TOPIC_PREFIX="pyaltherma"
PYALTHERMA_MQTT_ONETOPIC="one"
PYALTHERMA_POLL_INTERVAL="5"
PYALTHERMA_HOST="<replace_me>"
```

The resulting topics would be:

| Type  | Topic                                             |
|-------|---------------------------------------------------|
| Read  | `{PYALTHERMA_MQTT_TOPIC_PREFIX}/state/{property}` |
| Write | `{PYALTHERMA_MQTT_TOPIC_PREFIX}/set/{property}`   |

Examples with default configuration:

| Type  | Topic                            |
|-------|----------------------------------|
| Read  | `pyaltherma/state/dhw_temp`      |
| Write | `pyaltherma/set/dhw_target_temp` |

Example with `PYALTHERMA_MQTT_ONETOPIC` set to `one`:

| Type  | Topic                            |
|-------|----------------------------------|
| Read  | `pyaltherma/state/one`           |

## Usage

When you're set, run it:

```bash
$ python3 -m pyaltherma_mqtt
```

Or if not installed as module:

```bash
$ python3 /path/to/pyaltherma_mqtt.py
```

## Implemented properties

| Property                          | Description                                   | Read | Write | Values                                                       | Limitations                                                                                      |
|-----------------------------------|-----------------------------------------------|------|-------|--------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| dhw_power                         | Domestic hot water power                      | ✓    | ✓     | "ON", "OFF"                                                  |                                                                                                  |
| dhw_temp                          | Domestic hot water temperature                | ✓    |       |                                                              |                                                                                                  |
| dhw_target_temp                   | Domestic hot water target temperature         | ✓    | ✓     | between "30" and "80"                                        | only for "dhw_power" set to "ON"                                                                 |
| dhw_temp_heating                  | Domestic hot water target temperature heating | ✓    | ✓     | between "30" and "80"                                        | only for "dhw_power" set to "ON"                                                                 |
| dhw_powerful                      | Domestic hot water powerful mode              | ✓    | ✓     | "ON", "OFF"                                                  |                                                                                                  |
| indoor_temp                       | Indoor temperature                            | ✓    |       |                                                              |                                                                                                  |
| outdoor_temp                      | Outdoor temperature                           | ✓    |       |                                                              |                                                                                                  |
| climate_control_heating_config    | Climate control heating configuration         | ✓    |       | "1" (WeatherDependent), "2" (Fixed)                          |                                                                                                  |
| climate_control_cooling_config    | Climate control cooling configuration         | ✓    |       | "1" [WeatherDependent], "2" (Fixed)                          |                                                                                                  |
| climate_control_power             | Climate control power                         | ✓    | ✓     | "ON", "OFF"                                                  |                                                                                                  |
| climate_control_mode              | Climate control mode                          | ✓    | ✓     | "heating", "cooling", "auto", "heating_day", "heating_night" |                                                                                                  |
| leaving_water_temp_offset_heating | Leaving water temperature offset for heating  | ✓    | ✓     | between "-10" and "10"                                       | only for "climate_control_mode" set to "heating" and "climate_control_heating_config" set to "1" |
| leaving_water_temp_offset_cooling | Leaving water temperature offset for cooling  | ✓    | ✓     | between "-10" and "10"                                       | only for "climate_control_mode" set to "cooling" and "climate_control_cooling_config" set to "1" |
| leaving_water_temp_offset_auto    | Leaving water temperature offset for auto     | ✓    | ✓     | between "-10" and "10"                                       | only for "climate_control_mode" set to "auto"                                                    |
| leaving_water_temp_heating        | Leaving water temperature for heating         | ✓    |       |                                                              | only for "climate_control_mode" set to "heating" and "climate_control_heating_config" set to "2" |
| leaving_water_temp_cooling        | Leaving water temperature for cooling         | ✓    |       |                                                              | only for "climate_control_mode" set to "cooling" and "climate_control_cooling_config" set to "2" |
| leaving_water_temp_auto           | Leaving water temperature for auto            | ✓    |       |                                                              | only for "climate_control_mode" set to "auto"                                                    |

## Service implementation (systemd)

To run this module as a service, consider using a systemd definition.
Create the file `/etc/systemd/system/pyaltherma_mqtt.service` with following content:

```
[Unit]
Description=pyaltherma_mqtt
After=network.target

[Service]
Type=simple
EnvironmentFile=/path/to/file/with/env/variables
ExecStart=/usr/bin/python3 /path/to/pyaltherma_mqtt.py
Restart=always
RestartSec=10
StartLimitInterval=0

[Install]
WantedBy=multi-user.target
```

Just reload the daemon and start the service.

```
$ sudo systemctl daemon-reload
$ sudo systemctl enable pyaltherma_mqtt
$ sudo systemctl start pyaltherma_mqtt
```
