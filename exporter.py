#!/usr/bin/env python3

from prometheus_client import start_http_server, Gauge, Info
from typing import Dict, Union, Tuple
import time
import logging
import os
import configparser
import argparse
from pathlib import Path
from pysolarmanv5 import PySolarmanV5
from deye_controller.utils import group_registers, map_response
from deye_controller.modbus.protocol import HoldingRegisters

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define available registers with their descriptions and units
AVAILABLE_REGISTERS = [
    # Battery metrics
    ("BatteryChargeToday", "Battery Charge Today", "kWh"),
    ("BatteryDischargeToday", "Battery Discharge Today", "kWh"),
    ("BatteryChargeTotal", "Battery Charge Total", "kWh"),
    ("BatteryDischargeTotal", "Battery Discharge Total", "kWh"),
    ("BatteryTemp", "Battery Temperature", "°C"),
    ("BatteryVoltage", "Battery Voltage", "V"),
    ("BatterySOC", "Battery State of Charge", "%"),
    ("BatteryOutPower", "Battery Output Power", "W"),
    ("BatteryOutCurrent", "Battery Output Current", "A"),
    
    # BMS metrics
    ("BMSChargedVoltage", "BMS Charged Voltage", "V"),
    ("BMSDischargedVoltage", "BMS Discharged Voltage", "V"),
    ("BMSChargingCurrentLimit", "BMS Charging Current Limit", "A"),
    ("BMSDischargeCurrentLimit", "BMS Discharge Current Limit", "A"),
    ("BMSBatteryCapacity", "BMS Battery Capacity", "%"),
    ("BMSBatteryVoltage", "BMS Battery Voltage", "V"),
    ("BMSBatteryCurrent", "BMS Battery Current", "A"),
    ("BMSBatteryTemp", "BMS Battery Temperature", "°C"),
    
    # Grid metrics
    ("GRIDPhaseAVolt", "Grid Phase A Voltage", "V"),
    ("GRIDPhaseBVolt", "Grid Phase B Voltage", "V"),
    ("GRIDPhaseCVolt", "Grid Phase C Voltage", "V"),
    ("GRIDPhaseAPowerIn", "Grid Phase A Power In", "W"),
    ("GRIDPhaseBPowerIn", "Grid Phase B Power In", "W"),
    ("GRIDPhaseCPowerIn", "Grid Phase C Power In", "W"),
    ("GRIDActivePowerIn", "Grid Active Power In", "W"),
    ("GRIDFrequency", "Grid Frequency", "Hz"),
    
    # PV metrics
    ("PV1InPower", "PV1 Input Power", "W"),
    ("PV2InPower", "PV2 Input Power", "W"),
    ("PV3InPower", "PV3 Input Power", "W"),
    ("PV4InPower", "PV4 Input Power", "W"),
    ("PV1Voltage", "PV1 Voltage", "V"),
    ("PV1Current", "PV1 Current", "A"),
    ("PV2Voltage", "PV2 Voltage", "V"),
    ("PV2Current", "PV2 Current", "A"),
    ("PV3Voltage", "PV3 Voltage", "V"),
    ("PV3Current", "PV3 Current", "A"),
    ("PV4Voltage", "PV4 Voltage", "V"),
    ("PV4Current", "PV4 Current", "A"),
    
    # Daily/Total metrics
    ("TodayBuyGrid", "Today Bought From Grid", "kWh"),
    ("TodaySoldGrid", "Today Sold To Grid", "kWh"),
    ("TotalBuyGrid", "Total Bought From Grid", "kWh"),
    ("TotalSellGrid", "Total Sold To Grid", "kWh"),
    ("TodayToLoad", "Today To Load", "kWh"),
    ("TotalToLoad", "Total To Load", "kWh"),
    ("TodayFromPV", "Today From PV", "kWh"),
    ("TotalFromPV", "Total From PV", "kWh"),
]

def load_config():
    """
    Load configuration from config file and environment variables.
    Environment variables take precedence over config file values.
    """
    config = {
        'port': 9877,
        'collection_interval': 15,
        'host': '192.168.100.102',
        'port_inverter': 8899,
        'serial_number': 2999999999,
        'metrics': []  # Empty list means collect all metrics
    }
    
    # Try to load config file
    config_file = Path('config.ini')
    if config_file.exists():
        parser = configparser.ConfigParser()
        parser.read(config_file)
        
        if 'exporter' in parser:
            config['port'] = parser.getint('exporter', 'port', fallback=config['port'])
            config['collection_interval'] = parser.getint('exporter', 'collection_interval', 
                                                        fallback=config['collection_interval'])
        
        if 'inverter' in parser:
            config['host'] = parser.get('inverter', 'host', fallback=config['host'])
            config['port_inverter'] = parser.getint('inverter', 'port', fallback=config['port_inverter'])
            config['serial_number'] = parser.getint('inverter', 'serial_number', fallback=config['serial_number'])
        
        if 'metrics' in parser:
            metrics_str = parser.get('metrics', 'selection', fallback='')
            if metrics_str:
                config['metrics'] = [m.strip() for m in metrics_str.split(',') if m.strip()]
    
    # Environment variables override config file
    config['port'] = int(os.getenv('EXPORTER_PORT', config['port']))
    config['collection_interval'] = int(os.getenv('COLLECTION_INTERVAL', config['collection_interval']))
    config['host'] = os.getenv('INVERTER_HOST', config['host'])
    config['port_inverter'] = int(os.getenv('INVERTER_PORT', config['port_inverter']))
    config['serial_number'] = int(os.getenv('INVERTER_SERIAL', config['serial_number']))
    
    metrics_env = os.getenv('INVERTER_METRICS', '')
    if metrics_env:
        config['metrics'] = [m.strip() for m in metrics_env.split(',') if m.strip()]
    
    return config

def print_available_registers():
    """Print all available registers with their descriptions and units"""
    print("\nAvailable Deye Inverter Registers:")
    print("-" * 100)
    print(f"{'Register Name':<40} {'Description':<45} {'Unit':<10}")
    print("-" * 100)
    
    for reg_name, description, unit in AVAILABLE_REGISTERS:
        print(f"{reg_name:<40} {description:<45} {unit:<10}")
    
    print("\nTo use these registers, add them to your config.ini under the [metrics] section:")
    print("For example, to monitor battery and PV metrics:")
    print("""
[metrics]
selection = BatterySOC,BatteryVoltage,BatteryOutPower,PV1InPower,PV2InPower,TodayFromPV
    """)
    print("\nOr use the INVERTER_METRICS environment variable:")
    print('export INVERTER_METRICS="BatterySOC,BatteryVoltage,BatteryOutPower,PV1InPower,PV2InPower,TodayFromPV"')

class DeyeCollector:
    def __init__(self, config):
        """Initialize the collector with configuration"""
        self.config = config
        self.metrics = {}
        self.info_metrics = {}
        
        # Initialize connection
        self.inverter = PySolarmanV5(
            address=config['host'],
            serial=config['serial_number'],  # Changed from serial_number to serial
            port=config['port_inverter'],
            mb_slave_id=1,
            verbose=False
        )
        
        # Get all available registers if no specific metrics configured
        if not config['metrics']:
            iterator = HoldingRegisters.as_list()
            reg_groups = group_registers(iterator)
            for group in reg_groups:
                for reg in group:
                    if hasattr(reg, 'description'):
                        metric_name = reg.description.replace(' ', '')
                        self.create_metric(metric_name, reg)
        else:
            # Create metrics based on configuration
            for metric_name in config['metrics']:
                if hasattr(HoldingRegisters, metric_name):
                    reg = getattr(HoldingRegisters, metric_name)
                    self.create_metric(metric_name, reg)
                else:
                    logger.warning(f"Metric {metric_name} not found in HoldingRegisters")
    
    def create_metric(self, name, register):
        """Create a Prometheus metric based on register type"""
        description = register.description if hasattr(register, 'description') else name
        suffix = getattr(register, 'suffix', '')
        
        # Add unit to description if available
        if suffix:
            description = f"{description} ({suffix})"
        
        # Create appropriate metric type
        if isinstance(register, (IntType, FloatType, LongUnsignedType)):
            self.metrics[name] = Gauge(
                f"deye_{name.lower()}", 
                description
            )
        else:
            self.info_metrics[name] = Info(
                f"deye_{name.lower()}", 
                description
            )

    def _is_numeric_value(self, value) -> bool:
        """Check if a value should be treated as numeric"""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    
    def _update_metric(self, description: str, value: Union[float, str, int], suffix: str = ''):
        """Update a metric with the given value, automatically choosing the right type"""
        if self._is_numeric_value(value):
            # For numeric values, use Gauge
            if description in self.metrics:
                try:
                    self.metrics[description].set(float(value))
                    logger.debug(f"Updated numeric metric {description}: {value}")
                except (ValueError, TypeError) as e:
                    logger.error(f"Error converting value for metric {description}: {e}")
        else:
            # For string values, use Info
            if description in self.info_metrics:
                value_str = str(value)
                if suffix:
                    value_str = f"{value_str} {suffix}"
                self.info_metrics[description].info({'value': value_str})
                logger.debug(f"Updated string metric {description}: {value_str}")

    def collect_metrics(self):
        """Collect metrics from the inverter"""
        try:
            # Get register objects for configured metrics
            regs = [getattr(HoldingRegisters, attr) for attr in self.config['metrics'] if hasattr(HoldingRegisters, attr)]
            
            # Group registers for efficient reading
            groups = group_registers(regs)
            
            # Read each group of registers
            for group in groups:
                try:
                    res = self.inverter.read_holding_registers(group.start_address, group.len)
                    mapped_registers = map_response(res, group)
                    
                    # Update Prometheus metrics for each register in the group
                    for reg in group:  # RegistersGroup is directly iterable
                        if hasattr(reg, 'description'):
                            description = reg.description.title()
                            suffix = getattr(reg, 'suffix', '')
                            value = reg.value if hasattr(reg, 'value') else None
                            
                            if value is not None:
                                self._update_metric(description, value, suffix)
                        else:
                            logger.warning(f"Register without description: {reg}")
                
                except Exception as e:
                    logger.error(f"Error reading register group: {e}", exc_info=True)
                    
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}", exc_info=True)

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Deye Inverter Prometheus Exporter')
    parser.add_argument('--list-registers', action='store_true',
                       help='List all available registers and exit')
    args = parser.parse_args()
    
    # If --list-registers is specified, print registers and exit
    if args.list_registers:
        print_available_registers()
        return
    
    # Load configuration
    config = load_config()
    
    # Start up the server to expose the metrics
    start_http_server(config['port'])
    logger.info(f"Exporter started on port {config['port']}")
    
    # Create collector
    collector = DeyeCollector(config)
    
    # Update metrics based on collection interval
    while True:
        collector.collect_metrics()
        time.sleep(config['collection_interval'])

if __name__ == '__main__':
    main()
