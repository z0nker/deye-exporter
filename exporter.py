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
    # Default values
    config = {
        'port': 9877,
        'collection_interval': 15,
        'inverter': {
            'host': '192.168.100.102',
            'port': 8899,
            'serial_number': 2999999999
        },
        'metrics': []
    }
    
    # Load from config file
    config_parser = configparser.ConfigParser()
    config_path = Path(__file__).parent / 'config.ini'
    
    if config_path.exists():
        config_parser.read(config_path)
        if 'exporter' in config_parser:
            config['port'] = config_parser.getint('exporter', 'port', fallback=config['port'])
            config['collection_interval'] = config_parser.getint('exporter', 'collection_interval', 
                                                              fallback=config['collection_interval'])
        
        if 'inverter' in config_parser:
            config['inverter']['host'] = config_parser.get('inverter', 'host', 
                                                         fallback=config['inverter']['host'])
            config['inverter']['port'] = config_parser.getint('inverter', 'port', 
                                                            fallback=config['inverter']['port'])
            config['inverter']['serial_number'] = config_parser.getint('inverter', 'serial_number', 
                                                                     fallback=config['inverter']['serial_number'])
        
        if 'metrics' in config_parser:
            metrics_str = config_parser.get('metrics', 'selection', fallback='')
            config['metrics'] = [m.strip() for m in metrics_str.split(',') if m.strip()]
    
    # Environment variables take precedence
    config['port'] = int(os.getenv('EXPORTER_PORT', config['port']))
    config['collection_interval'] = int(os.getenv('EXPORTER_COLLECTION_INTERVAL', config['collection_interval']))
    config['inverter']['host'] = os.getenv('INVERTER_HOST', config['inverter']['host'])
    config['inverter']['port'] = int(os.getenv('INVERTER_PORT', config['inverter']['port']))
    config['inverter']['serial_number'] = int(os.getenv('INVERTER_SERIAL', config['inverter']['serial_number']))
    
    if os.getenv('INVERTER_METRICS'):
        config['metrics'] = [m.strip() for m in os.getenv('INVERTER_METRICS').split(',') if m.strip()]
    
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
        self.modbus = PySolarmanV5(
            self.config['inverter']['host'],
            self.config['inverter']['serial_number'],
            port=self.config['inverter']['port']
        )
        
        # Initialize metrics
        self.numeric_metrics = {}  # For Gauge metrics
        self.string_metrics = {}   # For Info metrics
        # Store register objects for reuse
        self.registers = {}
        self._setup_metrics()
    
    def _is_numeric_value(self, value) -> bool:
        """Check if a value should be treated as numeric"""
        try:
            float(value)
            return True
        except (ValueError, TypeError):
            return False
    
    def _create_metric_id(self, description: str, is_info: bool = False) -> str:
        """
        Create a Prometheus-compatible metric ID from description
        
        Args:
            description: The metric description
            is_info: Whether this is for an Info metric (adds _info suffix)
        """
        # Convert to lowercase and replace spaces/special chars with underscore
        metric_id = description.lower().replace(' ', '_')
        metric_id = ''.join(c if c.isalnum() or c == '_' else '_' for c in metric_id)
        base_id = f"deye_{metric_id}"
        return f"{base_id}_info" if is_info else base_id
    
    def _setup_metrics(self):
        """Setup Prometheus metrics based on configuration"""
        for metric_name in self.config['metrics']:
            # Get the register object
            register = getattr(HoldingRegisters, metric_name, None)
            if register is None:
                logger.warning(f"Unknown metric: {metric_name}, skipping")
                continue
            
            # Store register for reuse
            self.registers[metric_name] = register
            
            # Create a Prometheus metric using the description as the key
            description = register.description.title()
            suffix = getattr(register, 'suffix', '')
            full_description = f"{description} ({suffix})" if suffix else description
            
            # Create metrics with appropriate IDs
            self.numeric_metrics[description] = Gauge(
                self._create_metric_id(description),
                full_description
            )
            self.string_metrics[description] = Info(
                self._create_metric_id(description, is_info=True),
                full_description
            )
    
    def _update_metric(self, description: str, value: Union[float, str, int], suffix: str = ''):
        """Update a metric with the given value, automatically choosing the right type"""
        if self._is_numeric_value(value):
            # For numeric values, use Gauge
            if description in self.numeric_metrics:
                try:
                    self.numeric_metrics[description].set(float(value))
                    logger.debug(f"Updated numeric metric {description}: {value}")
                except (ValueError, TypeError) as e:
                    logger.error(f"Error converting value for metric {description}: {e}")
        else:
            # For string values, use Info
            if description in self.string_metrics:
                value_str = str(value)
                if suffix:
                    value_str = f"{value_str} {suffix}"
                self.string_metrics[description].info({'value': value_str})
                logger.debug(f"Updated string metric {description}: {value_str}")
    
    def collect_metrics(self):
        """Collect metrics from the inverter"""
        try:
            # Get register objects for configured metrics
            regs = [self.registers[attr] for attr in self.config['metrics'] if attr in self.registers]
            
            # Group registers for efficient reading
            groups = group_registers(regs)
            
            # Read each group of registers
            for group in groups:
                try:
                    res = self.modbus.read_holding_registers(group.start_address, group.len)
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
