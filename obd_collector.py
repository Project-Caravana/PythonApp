"""
Real OBD-II Data Collector - Individual Vehicle Script
Connects to actual OBD-II device via Bluetooth/Serial
NO SIMULATION - Real hardware only
"""

import obd
import time
import json
import requests
from datetime import datetime
import os

# ====== CONFIGURATION ======
#For each vehicle we need to program the IoT device with its ID
#You have register the vehicle in the Dashboard and take the given ID to configure the IoT  - 
#we have the same script for all vehicles, but the ID is different
VEHICLE_ID = os.getenv("VEHICLE_ID", "MEU-PEUGOET")
VEHICLE_TYPE = "delivery_van"

# OBD Connection (adjust to your device)
COM_PORT = "COM3"  # Windows: COM3, COM4, etc. | Linux: /dev/rfcomm0 | Mac: /dev/tty.OBD-II
BAUD_RATE = None  # None for auto-detect, or specify: 9600, 38400, etc.

# API Configuration
API_ENDPOINT = os.getenv("API_ENDPOINT", "http://localhost:5000/api/vehicle-data")
SEND_TO_API = False

# Storage Configuration
LOCAL_STORAGE_DIR = "vehicle_data"
LOCAL_JSON_FILE = f"{LOCAL_STORAGE_DIR}/{VEHICLE_ID}_data.json"

# Update interval (seconds)
UPDATE_INTERVAL = 2

# Retry configuration
MAX_CONNECTION_RETRIES = 3
RETRY_DELAY = 5

os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)

# ====== REAL OBD CONNECTION ======

class RealOBDCollector:
    """Collects data from real OBD-II device"""
    
    def __init__(self, vehicle_id, vehicle_type, com_port, baud_rate=None):
        self.vehicle_id = vehicle_id
        self.vehicle_type = vehicle_type
        self.com_port = com_port
        self.baud_rate = baud_rate
        self.connection = None
        self.all_readings = []
        
        # Distance tracking
        self.distance = 0.0
        self.last_time = time.time()
        self.trip_start = datetime.now().isoformat()
        
        # Cached VIN (read once)
        self.vin = None
    
    def connect(self):
        """Connect to real OBD-II device"""
        print(f"🔧 [{self.vehicle_id}] Connecting to OBD-II on {self.com_port}...")
        
        try:
            if self.baud_rate:
                self.connection = obd.OBD(self.com_port, baudrate=self.baud_rate)
            else:
                self.connection = obd.OBD(self.com_port)
            
            if not self.connection.is_connected():
                print(f" [{self.vehicle_id}] Failed to connect to OBD-II")
                print(f"   Make sure:")
                print(f"   - OBD-II device is plugged into car")
                print(f"   - Car ignition is ON")
                print(f"   - Bluetooth is paired (if using Bluetooth)")
                print(f"   - Correct COM port: {self.com_port}")
                return False
            
            print(f" [{self.vehicle_id}] Connected to OBD-II!")
            print(f"   Protocol: {self.connection.protocol_name()}")
            print(f"   Port: {self.connection.port_name()}")
            
            # Get VIN once
            self._read_vin()
            
            # Check supported commands
            self._check_supported_commands()
            
            return True
            
        except Exception as e:
            print(f" [{self.vehicle_id}] Connection error: {e}")
            return False
    
    def _read_vin(self):
        """Read VIN from vehicle (once)"""
        try:
            vin_response = self.connection.query(obd.commands.VIN)
            if not vin_response.is_null():
                self.vin = str(vin_response.value)
                print(f"   VIN: {self.vin}")
            else:
                print(f"   VIN: Not available")
        except:
            pass
    
    def _check_supported_commands(self):
        """Check which OBD commands are supported by the vehicle"""
        print(f"\n📋 Checking supported commands...")
        
        commands_to_check = [
            ("Engine Coolant Temp", obd.commands.COOLANT_TEMP),
            ("Engine RPM", obd.commands.RPM),
            ("Vehicle Speed", obd.commands.SPEED),
            ("Fuel Level", obd.commands.FUEL_LEVEL),
            ("MAF (Air Flow)", obd.commands.MAF),
            ("Throttle Position", obd.commands.THROTTLE_POS),
            ("Engine Load", obd.commands.ENGINE_LOAD),
            ("Intake Temp", obd.commands.INTAKE_TEMP),
        ]
        
        supported = []
        not_supported = []
        
        for name, cmd in commands_to_check:
            if cmd in self.connection.supported_commands:
                supported.append(name)
            else:
                not_supported.append(name)
        
        if supported:
            print(f"   ✅ Supported: {', '.join(supported)}")
        if not_supported:
            print(f"   ⚠️  Not supported: {', '.join(not_supported)}")
        print()
    
    def get_current_snapshot(self):
        """Get current vehicle data snapshot from real OBD-II"""
        
        # Query all parameters
        temp_resp = self.connection.query(obd.commands.COOLANT_TEMP)
        rpm_resp = self.connection.query(obd.commands.RPM)
        speed_resp = self.connection.query(obd.commands.SPEED)
        fuel_resp = self.connection.query(obd.commands.FUEL_LEVEL)
        maf_resp = self.connection.query(obd.commands.MAF)
        dtc_resp = self.connection.query(obd.commands.GET_DTC)
        
        # Extract values (handle null responses)
        temp = self._extract_value(temp_resp)
        rpm = self._extract_value(rpm_resp)
        speed = self._extract_value(speed_resp, unit="km/h")
        fuel = self._extract_value(fuel_resp)
        maf = self._extract_value(maf_resp, unit="g/s")
        dtc = dtc_resp.value if not dtc_resp.is_null() else []
        
        # Calculate distance traveled
        now = time.time()
        dt = now - self.last_time
        if speed is not None:
            self.distance += speed * (dt / 3600)  # km
        self.last_time = now
        
        # Calculate fuel consumption
        km_per_liter, fuel_flow = self._calculate_fuel_consumption(speed, maf)
        
        # Create snapshot
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "vehicle_id": self.vehicle_id,
            "vehicle_type": self.vehicle_type,
            "vin": self.vin,
            "coolant_temp_celsius": round(temp, 1) if temp is not None else None,
            "rpm": round(rpm, 0) if rpm is not None else None,
            "speed_kmh": round(speed, 1) if speed is not None else None,
            "fuel_level_percent": round(fuel, 1) if fuel is not None else None,
            "maf_g_s": round(maf, 2) if maf is not None else None,
            "fuel_consumption_kml": round(km_per_liter, 2) if km_per_liter else None,
            "fuel_flow_lh": round(fuel_flow, 2) if fuel_flow else None,
            "distance_traveled_km": round(self.distance, 3),
            "dtc_codes": self._format_dtc(dtc),
            "has_errors": bool(dtc and len(dtc) > 0),
            "trip_start": self.trip_start
        }
        
        return snapshot
    
    def _extract_value(self, response, unit=None):
        """Extract numeric value from OBD response"""
        if response.is_null():
            return None
        
        try:
            value = response.value
            
            if value is None:
                return None
            
            # Handle Pint quantities (with units)
            if hasattr(value, 'to') and unit:
                return float(value.to(unit).magnitude)
            elif hasattr(value, 'magnitude'):
                return float(value.magnitude)
            else:
                return float(value)
        except:
            return None
    
    def _format_dtc(self, dtc):
        """Format DTC codes"""
        if not dtc:
            return []
        
        try:
            formatted = []
            for code in dtc:
                if isinstance(code, tuple) and len(code) >= 1:
                    formatted.append({
                        "code": code[0],
                        "description": code[1] if len(code) > 1 else "Unknown"
                    })
                else:
                    formatted.append({
                        "code": str(code),
                        "description": "Unknown"
                    })
            return formatted
        except:
            return []
    
    def _calculate_fuel_consumption(self, speed, maf):
        """Calculate fuel consumption"""
        if speed is None or maf is None or speed == 0:
            return None, None
        
        try:
            AFR = 14.7  # Air-Fuel Ratio for gasoline
            GAS_DENSITY = 720  # g/L
            
            fuel_flow = (maf * 3600) / (AFR * GAS_DENSITY)  # L/h
            km_per_liter = speed / fuel_flow if fuel_flow > 0 else 0
            
            return km_per_liter, fuel_flow
        except:
            return None, None
    
    def save_local(self, snapshot):
        """Save data to local JSON file"""
        try:
            self.all_readings.append(snapshot)
            
            # Keep only last 1000 readings
            if len(self.all_readings) > 1000:
                self.all_readings = self.all_readings[-1000:]
            
            with open(LOCAL_JSON_FILE, 'w', encoding='utf-8') as f:
                json.dump({
                    "vehicle_id": self.vehicle_id,
                    "last_update": snapshot["timestamp"],
                    "total_readings": len(self.all_readings),
                    "latest": snapshot,
                    "history": self.all_readings
                }, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"⚠️  [{self.vehicle_id}] Failed to save locally: {e}")
            return False
    
    def send_to_api(self, snapshot):
        """Send data to API endpoint"""
        if not SEND_TO_API:
            return True
        
        try:
            response = requests.post(
                API_ENDPOINT,
                json=snapshot,
                timeout=5,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                return True
            else:
                return False
                
        except requests.exceptions.ConnectionError:
            return False
        except Exception as e:
            return False
    
    def stop(self):
        """Stop data collection and close connection"""
        if self.connection:
            self.connection.close()
        print(f"✅ [{self.vehicle_id}] Stopped data collection")
    
    def is_connected(self):
        """Check if still connected"""
        return self.connection and self.connection.is_connected()

# ====== MAIN ======

def main():
    """Main execution"""
    print(f"\n{'='*70}")
    print(f"Real OBD-II Data Collector - {VEHICLE_ID}")
    print(f"Port: {COM_PORT}")
    print(f"Local Storage: {LOCAL_JSON_FILE}")
    print(f"API Endpoint: {API_ENDPOINT if SEND_TO_API else 'DISABLED'}")
    print(f"{'='*70}\n")
    
    # Try to connect with retries
    collector = None
    for attempt in range(1, MAX_CONNECTION_RETRIES + 1):
        print(f"Connection attempt {attempt}/{MAX_CONNECTION_RETRIES}...")
        
        collector = RealOBDCollector(VEHICLE_ID, VEHICLE_TYPE, COM_PORT, BAUD_RATE)
        
        if collector.connect():
            break
        
        if attempt < MAX_CONNECTION_RETRIES:
            print(f"Retrying in {RETRY_DELAY} seconds...\n")
            time.sleep(RETRY_DELAY)
        else:
            print(f"\n Failed to connect after {MAX_CONNECTION_RETRIES} attempts")
            print(f"\n Troubleshooting tips:")
            print(f"   1. Check if OBD-II adapter is plugged into car's OBD port")
            print(f"   2. Turn car ignition to ON position (engine doesn't need to run)")
            print(f"   3. Pair Bluetooth device if using Bluetooth adapter")
            print(f"   4. Check COM port:")
            print(f"      - Windows: Device Manager > Ports (COM & LPT)")
            print(f"      - Linux: ls /dev/rfcomm* or /dev/ttyUSB*")
            print(f"      - Mac: ls /dev/tty.*")
            print(f"   5. Try different baud rates: 9600, 38400, 115200")
            return
    
    api_warning_shown = False
    
    try:
        iteration = 0
        print(f"\n{'='*70}")
        print(f" Starting data collection... (Press Ctrl+C to stop)")
        print(f"{'='*70}\n")
        
        while True:
            # Check if still connected
            if not collector.is_connected():
                print(f"\n Lost connection to OBD-II device!")
                break
            
            iteration += 1
            
            try:
                # Get current data snapshot
                snapshot = collector.get_current_snapshot()
                
                # Save locally
                local_saved = collector.save_local(snapshot)
                
                # Send to API
                api_sent = collector.send_to_api(snapshot)
                
                # Show API warning only once
                if not api_sent and not api_warning_shown and SEND_TO_API:
                    print(f"  [{VEHICLE_ID}] Cannot connect to API (is server running?)\n")
                    api_warning_shown = True
                
                # Display status
                print(f"[{iteration:04d}]  {snapshot['timestamp']}")
                
                # Main metrics
                temp_str = f"{snapshot['coolant_temp_celsius']}°C" if snapshot['coolant_temp_celsius'] else "N/A"
                rpm_str = f"{snapshot['rpm']}" if snapshot['rpm'] else "N/A"
                speed_str = f"{snapshot['speed_kmh']} km/h" if snapshot['speed_kmh'] else "N/A"
                
                print(f"    Temp: {temp_str} |  RPM: {rpm_str} | 🏎️  Speed: {speed_str}")
                
                # Fuel metrics
                fuel_str = f"{snapshot['fuel_level_percent']}%" if snapshot['fuel_level_percent'] else "N/A"
                cons_str = f"{snapshot['fuel_consumption_kml']} km/L" if snapshot['fuel_consumption_kml'] else "N/A"
                dist_str = f"{snapshot['distance_traveled_km']} km"
                
                print(f"   Fuel: {fuel_str} |  Consumption: {cons_str} | 📏 Distance: {dist_str}")
                
                # Status
                print(f"   Local: {'✓' if local_saved else '✗'} |   API: {'✓' if api_sent else '✗'}")
                
                # Errors
                if snapshot['has_errors']:
                    print(f"    Diagnostic Codes: {snapshot['dtc_codes']}")
                
                print()
                
            except Exception as e:
                print(f"  Error reading data: {e}")
            
            time.sleep(UPDATE_INTERVAL)
            
    except KeyboardInterrupt:
        print(f"\n\n Stopping {VEHICLE_ID}...")
        collector.stop()
        print(f" Total distance: {collector.distance:.2f} km")
        print(f" Final data saved to: {LOCAL_JSON_FILE}")
    except Exception as e:
        print(f"\n Unexpected error: {e}")
        if collector:
            collector.stop()


if __name__ == "__main__":
    main()
