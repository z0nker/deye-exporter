# Deye Inverter Prometheus Exporter

[![Docker Build](https://github.com/z0nker/deye-exporter/actions/workflows/docker-build.yml/badge.svg)](https://github.com/z0nker/deye-exporter/actions/workflows/docker-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Prometheus exporter for Deye solar inverter metrics. This exporter collects various metrics from Deye inverters using the Modbus protocol and exposes them in Prometheus format.

## Features

- Collects metrics from Deye inverters using Modbus protocol
- Supports both numeric and string metrics
- Configurable through environment variables or config file
- Docker support with multi-arch images
- Automatic metric type detection (Gauge for numbers, Info for strings)
- Proper Prometheus naming conventions

## Quick Start

The easiest way to run the exporter is using Docker:

```bash
docker run -d \
  -p 9877:9877 \
  -v $(pwd)/config.ini:/app/config.ini:ro \
  -e INVERTER_HOST=192.168.100.102 \
  -e INVERTER_PORT=8899 \
  -e INVERTER_SERIAL=2999999999 \
  ghcr.io/z0nker/deye-exporter:main
```

Or using Docker Compose:

```bash
docker compose up -d
```

## Requirements

For local installation:
- Python 3.6+
- prometheus_client
- deye_controller
- pysolarmanv5

For Docker installation:
- Docker
- Docker Compose (optional)

## Installation

### Using Docker (Recommended)

1. Create a config.ini file (see Configuration section)
2. Run with Docker Compose:
```bash
docker compose up -d
```

### Local Installation

1. Clone the repository:
```bash
git clone https://github.com/z0nker/deye-exporter.git
cd deye-exporter
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the exporter:
```bash
python exporter.py
```

## Configuration

The exporter can be configured using either a configuration file (`config.ini`) or environment variables.
Environment variables take precedence over the configuration file.

### Available Registers

To see all available registers that can be monitored, use the `--list-registers` command:

```bash
# With Python
python exporter.py --list-registers

# With Docker
docker run --rm ghcr.io/z0nker/deye-exporter:main python exporter.py --list-registers
```

This will display a list of all available registers with their descriptions and units. You can use these register names in your configuration.

### Configuration Options

| Parameter | Config File Section | Config Key | Environment Variable | Default | Description |
|-----------|-------------------|------------|---------------------|---------|-------------|
| Exporter Port | exporter | port | EXPORTER_PORT | 9877 | The port on which the exporter web server runs |
| Collection Interval | exporter | collection_interval | COLLECTION_INTERVAL | 15 | How often to collect metrics (in seconds) |
| Inverter Host | inverter | host | INVERTER_HOST | 192.168.100.102 | IP address of the Deye inverter |
| Inverter Port | inverter | port | INVERTER_PORT | 8899 | Port of the Deye inverter |
| Inverter Serial | inverter | serial_number | INVERTER_SERIAL | 2999999999 | Serial number of the Deye inverter |
| Metrics Selection | metrics | selection | INVERTER_METRICS | [] | Comma-separated list of metrics to collect |

### Example config.ini

```ini
[exporter]
port = 9877
collection_interval = 15

[inverter]
host = 192.168.100.102
port = 8899
serial_number = 2999999999

[metrics]
selection = BatteryChargeToday,BatteryDischargeToday,BatteryChargeTotal,BMSChargedVoltage,BMSDischargedVoltage,BMSChargingCurrentLimit,BMSDischargeCurrentLimit,BMSBatteryCapacity,BMSBatteryVoltage,BMSBatteryCurrent
```

## Available Metrics

The following metrics are available (configure which ones you want in config.ini).
Metrics are automatically exposed as either Gauge (for numeric values) or Info (for string values) based on their actual value type.

For example metrics (actual names may vary based on register descriptions):
- `deye_battery_charge_today` (kWh)
- `deye_battery_discharge_today` (kWh)
- `deye_battery_charge_total` (kWh)
- `deye_bms_charged_voltage` (V)
- `deye_bms_discharged_voltage` (V)
- `deye_bms_charging_current_limit` (A)
- `deye_bms_discharge_current_limit` (A)
- `deye_bms_battery_capacity` (%)
- `deye_bms_battery_voltage` (V)
- `deye_bms_battery_current` (A)

For string values, the metric will be exposed with an `_info` suffix, for example:
- `deye_battery_status_info` (if the value is non-numeric)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
