# pyaltherma_mqtt
Provides a MQTT bridge for [pyaltherma](https://github.com/tadasdanielius/pyaltherma).

## Installation

All you have to do is to install the dependencies in your python environment.

```
$ pip install pyaltherma
$ pip install paho-mqtt
```

Before you start the script as a service, take a look at the configurable environment variables. Some of them are mandatory.

| ENV                             | Default value | Mandatory | Description                                                                  |
|---------------------------------|---------------|-----------|------------------------------------------------------------------------------|
| `PYALTHERMA_MQTT_HOST`          | localhost     | yes       | The host of the MQTT broker. Could be a hostename or IP.                     |
| `PYALTHERMA_MQTT_PORT`          | 1883          | no        | The port of the MQTT broker. For Mosquitto it is 1883 by default.            |
| `PYALTHERMA_MQTT_USERNAME`      | None          | no        | The username for the MQTT broker. If omitted, the password will not be used. |
| `PYALTHERMA_MQTT_PASSWORD`      | None          | no        | The password for the MQTT broker. Mandatory if username is set.              |
| `PYALTHERMA_MQTT_TOPIC_PREFIX`  | pyaltherma    | no        | The prefix for all MQTT messages.                                            |
| `PYALTHERMA_MQTT_ONETOPIC`      | None          | no        | If set, a single message will be sent, with all attributes as JSON.          |
| `PYALTHERMA_POLL_TIMEOUT`       | 5             | no        | The inverval attributes should be polled from the Daikin API.                |
| `PYALTHERMA_DAIKIN_HOST`        | None          | yes       | The host of the Daikin controller. Could be a hostname or IP.                |
| `PYALTHERMA_DAIKIN_DEVICE_MOCK` | None          | no        | If set, the internal mock will be used in place of the daikin api.           |

Copy/paste template for bash/zsh:

```
export PYALTHERMA_MQTT_HOST="localhost"
export PYALTHERMA_MQTT_PORT="1883"
export PYALTHERMA_MQTT_USERNAME="<replace_me_or_delete_line>"
export PYALTHERMA_MQTT_PASSWORD="<replace_me_or_delete_line>"
export PYALTHERMA_MQTT_TOPIC_PREFIX="pyaltherma"
export PYALTHERMA_MQTT_ONETOPIC="one"
export PYALTHERMA_POLL_TIMEOUT="5"
export PYALTHERMA_DAIKIN_HOST="<replace_me>"
export PYALTHERMA_DAIKIN_DEVICE_MOCK="<replace_me_or_delete_line>"
```

The resulting topics would be:

| Type  | Topic                                              |
|-------|----------------------------------------------------|
| Read  | `{PYALTHERMA_MQTT_TOPIC_PREFIX}/state/{attribute}` |
| Write | `{PYALTHERMA_MQTT_TOPIC_PREFIX}/set/{attribute}`   |

Examples with default configuration:

| Type  | Topic                            |
|-------|----------------------------------|
| Read  | `pyaltherma/state/dhw_temp`      |
| Write | `pyaltherma/set/dhw_target_temp` |

Example with PYALTHERMA_MQTT_ONETOPIC set to `one`:

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

## Implemented attributes

| Attribute                         | Description                                  | Read | Write | Values                                                       | Limitations                                                                                      |
|-----------------------------------|----------------------------------------------|------|-------|--------------------------------------------------------------|--------------------------------------------------------------------------------------------------|
| dhw_power                         | Domestic hot water power                     | X    | X     | "1" [On], "0" [Off]                                          |                                                                                                  |
| dhw_temp                          | Domestic hot water temperature               | X    |       |                                                              |                                                                                                  |
| dhw_target_temp                   | Domestic hot water target temperature        | X    | X     | between "30" and "80"                                        | only for "dhw_power" set to "1"                                                                  |
| dhw_powerful                      | Domestic hot water powerful mode             | X    | X     | "1" [On], "0" [Off]                                          |                                                                                                  |
| indoor_temp                       | Indoor temperature                           | X    |       |                                                              |                                                                                                  |
| outdoor_temp                      | Outdoor temperature                          | X    |       |                                                              |                                                                                                  |
| climate_control_heating_config    | Climate control heating configuration        | X    |       | "1" [WeatherDependent], "2" [Fixed]                          |                                                                                                  |
| climate_control_cooling_config    | Climate control cooling configuration        | X    |       | "1" [WeatherDependent], "2" [Fixed]                          |                                                                                                  |
| climate_control_power             | Climate control power                        | X    | X     | "1" [On], "0" [Off]                                          |                                                                                                  |
| climate_control_mode              | Climate control mode                         | X    | X     | "heating", "cooling", "auto", "heating_day", "heating_night" |                                                                                                  |
| leaving_water_temp_offset_heating | Leaving water temperature offset for heating | X    | X     | between "-5" and "5"                                         | only for "climate_control_mode" set to "heating" and "climate_control_heating_config" set to "1" |
| leaving_water_temp_offset_cooling | Leaving water temperature offset for cooling | X    | X     | between "-5" and "5"                                         | only for "climate_control_mode" set to "cooling" and "climate_control_cooling_config" set to "1" |
| leaving_water_temp_offset_auto    | Leaving water temperature offset for auto    | X    | X     | between "-5" and "5"                                         | only for "climate_control_mode" set to "auto"                                                    |
| leaving_water_temp_heating        | Leaving water temperature for heating        | X    |       |                                                              | only for "climate_control_mode" set to "heating" and "climate_control_heating_config" set to "2" |
| leaving_water_temp_cooling        | Leaving water temperature for cooling        | X    |       |                                                              | only for "climate_control_mode" set to "cooling" and "climate_control_cooling_config" set to "2" |
| leaving_water_temp_auto           | Leaving water temperature for auto           | X    |       |                                                              | only for "climate_control_mode" set to "auto"                                                    |

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

[Install]
WantedBy=multi-user.target
```

Just reload the daemon and start the service.

```
$ sudo systemctl daemon-reload
$ sudo systemctl enable pyaltherma_mqtt
$ sudo systemctl start pyaltherma_mqtt
```
