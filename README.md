# pyaltherma_mqtt
Provides a MQTT bridge for [pyaltherma](https://github.com/tadasdanielius/pyaltherma).

## Installation

All you have to do is to install the dependencies and run the module as a service. Before you do so, take a look at the configurable environment variables. Some of them are mandatory.

| ENV                          | Default value | Mandatory |
|------------------------------|---------------|-----------|
| PYALTHERMA_MQTT_HOST         | localhost     | yes       |
| PYALTHERMA_MQTT_PORT         | 1883          | no        |
| PYALTHERMA_MQTT_USERNAME     | None          | no        |
| PYALTHERMA_MQTT_PASSWORD     | None          | no        |
| PYALTHERMA_MQTT_TOPIC_PREFIX | pyaltherma    | no        |
| PYALTHERMA_MQTT_ONETOPIC     | None          | no        |
| PYALTHERMA_POLL_TIMEOUT      | 5             | no        |
| PYALTHERMA_DAIKIN_HOST       | None          | yes       |

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
