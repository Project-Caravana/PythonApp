"""
Car Data Collector - Individual Vehicle Script
Works with both real OBD-II and a custom simulator that actually generates data
"""

import time
import json
import requests
from datetime import datetime
import os
import random

# ====== CONFIGURATION ======
VEHICLE_ID = os.getenv("VEHICLE_ID", "CAR-SUBJECT-001")
VEHICLE_TYPE = "delivery_van"

USE_SIMULATOR = True  # Set to False for real OBD-II
COM_PORT = "COM3"

API_ENDPOINT = os.getenv("API_ENDPOINT", "http://localhost:5000/api/vehicle-data") #Here we'll use the deployed API endpoint
SEND_TO_API = True

LOCAL_STORAGE_DIR = "vehicle_data"
LOCAL_JSON_FILE = f"{LOCAL_STORAGE_DIR}/{VEHICLE_ID}_data.json"

UPDATE_INTERVAL = 2

os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)

# ====== CUSTOM SIMULATOR ======

class CustomOBDSimulator:
    """Custom OBD-II simulator that actually generates realistic data"""
    
    def __init__(self, vehicle_id):
        self.vehicle_id = vehicle_id
        self.distance = 0.0
        self.fuel_level = random.uniform(40, 95)
        self.speed = 0
        self.is_moving = False
        self.trip_start_time = time.time()
        self.last_time = time.time()
        
        # Vehicle-specific base values
        self.base_temp = random.uniform(82, 90)
        self.base_rpm_idle = random.uniform(700, 850)
        
        # Initialize with some movement
        if random.random() > 0.5:
            self.is_moving = True
            self.speed = random.uniform(30, 60)
        
        # VIN generation
        self.vin = f"1HGBH41JXMN{random.randint(100000, 999999)}"
        
        print(f"✅ [{vehicle_id}] Custom Simulator initialized")
    
    def update(self):
        """Update all vehicle parameters (called each iteration)"""
        # Update movement state occasionally (10% chance to change)
        if random.random() < 0.10:
            self.is_moving = not self.is_moving
            if self.is_moving:
                # Start moving with initial speed
                self.speed = random.uniform(20, 40)
        
        # Update speed with realistic patterns
        if self.is_moving:
            # Vary speed while moving (city driving pattern)
            change = random.uniform(-3, 5)
            self.speed += change
            # Keep speed in realistic range
            self.speed = max(10, min(self.speed, 85))
        else:
            # Gradually come to a stop
            self.speed = max(0, self.speed - random.uniform(8, 15))
        
        # Calculate distance
        now = time.time()
        dt = now - self.last_time
        if self.speed > 0:
            self.distance += self.speed * (dt / 3600)
        self.last_time = now
        
        # Update fuel consumption based on speed
        if self.speed > 0:
            # More fuel consumed at higher speeds
            consumption_rate = 0.002 + (self.speed / 10000)
            self.fuel_level -= consumption_rate
            self.fuel_level = max(5, self.fuel_level)
    
    def get_coolant_temp(self):
        """Get engine coolant temperature"""
        if self.speed > 40:
            temp = self.base_temp + random.uniform(2, 8)
        else:
            temp = self.base_temp + random.uniform(-3, 3)
        return max(75, min(temp, 105))
    
    def get_rpm(self):
        """Get engine RPM"""
        if self.speed < 1:
            # Idling
            return self.base_rpm_idle + random.uniform(-50, 50)
        else:
            # RPM increases with speed (more realistic formula)
            # Assuming gear ratios: ~40-50 RPM per km/h in higher gears
            base_rpm = self.base_rpm_idle + (self.speed * 40)
            return base_rpm + random.uniform(-100, 150)
    
    def get_speed(self):
        """Get vehicle speed in km/h"""
        return self.speed
    
    def get_fuel_level(self):
        """Get fuel level percentage"""
        return self.fuel_level
    
    def get_maf(self):
        """Get Mass Air Flow in g/s"""
        rpm = self.get_rpm()
        base_maf = (rpm / 1000) * 2.5
        return base_maf + random.uniform(-0.5, 0.5)
    
    def get_dtc_codes(self):
        """Get diagnostic trouble codes"""
        if random.random() < 0.02:  # 2% chance
            return [("P0128", "Coolant Thermostat Temperature")]
        return []
    
    def get_vin(self):
        """Get Vehicle Identification Number"""
        return self.vin
    
    def get_distance(self):
        """Get distance traveled"""
        return self.distance

# ====== REAL OBD CONNECTION ======

def connect_real_obd():
    """Connect to real OBD-II device"""
    try:
        import obd
        print(f"🔧 [{VEHICLE_ID}] Connecting to real OBD-II on {COM_PORT}...")
        connection = obd.Async(COM_PORT)
        
        if not connection.is_connected():
            print(f"❌ [{VEHICLE_ID}] Failed to connect to OBD-II")
            return None
        
        print(f"✅ [{VEHICLE_ID}] Connected to real OBD-II!")
        return connection
    except ImportError:
        print("❌ python-obd library not installed. Run: pip install obd")
        return None
    except Exception as e:
        print(f"❌ Error connecting to OBD-II: {e}")
        return None

# ====== DATA COLLECTOR ======

class VehicleDataCollector:
    """Collects and manages vehicle data"""
    
    def __init__(self, vehicle_id, vehicle_type, use_simulator=True):
        self.vehicle_id = vehicle_id
        self.vehicle_type = vehicle_type
        self.use_simulator = use_simulator
        self.all_readings = []
        
        if use_simulator:
            self.simulator = CustomOBDSimulator(vehicle_id)
            self.connection = None
        else:
            self.simulator = None
            self.connection = connect_real_obd()
            if not self.connection:
                raise Exception("Failed to connect to real OBD-II")
    
    def get_current_snapshot(self):
        """Get current vehicle data snapshot"""
        if self.use_simulator:
            # Update simulator state
            self.simulator.update()
            
            # Get values from simulator
            temp = self.simulator.get_coolant_temp()
            rpm = self.simulator.get_rpm()
            speed = self.simulator.get_speed()
            fuel = self.simulator.get_fuel_level()
            maf = self.simulator.get_maf()
            dtc = self.simulator.get_dtc_codes()
            vin = self.simulator.get_vin()
            distance = self.simulator.get_distance()
            
        else:
            # Get values from real OBD-II
            import obd
            temp_resp = self.connection.query(obd.commands.COOLANT_TEMP)
            rpm_resp = self.connection.query(obd.commands.RPM)
            speed_resp = self.connection.query(obd.commands.SPEED)
            fuel_resp = self.connection.query(obd.commands.FUEL_LEVEL)
            maf_resp = self.connection.query(obd.commands.MAF)
            dtc_resp = self.connection.query(obd.commands.GET_DTC)
            vin_resp = self.connection.query(obd.commands.VIN)
            
            temp = temp_resp.value.magnitude if temp_resp.value else None
            rpm = rpm_resp.value.magnitude if rpm_resp.value else None
            speed = speed_resp.value.to("km/h").magnitude if speed_resp.value else None
            fuel = fuel_resp.value.magnitude if fuel_resp.value else None
            maf = maf_resp.value.to("g/s").magnitude if maf_resp.value else None
            dtc = dtc_resp.value if dtc_resp.value else []
            vin = str(vin_resp.value) if vin_resp.value else None
            distance = 0  # Calculate separately for real OBD
        
        # Calculate fuel consumption
        km_per_liter, fuel_flow = self._calculate_fuel_consumption(speed, maf)
        
        # Create snapshot
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "vehicle_id": self.vehicle_id,
            "vehicle_type": self.vehicle_type,
            "vin": vin,
            "coolant_temp_celsius": round(temp, 1) if temp else None,
            "rpm": round(rpm, 0) if rpm else None,
            "speed_kmh": round(speed, 1) if speed else None,
            "fuel_level_percent": round(fuel, 1) if fuel else None,
            "maf_g_s": round(maf, 2) if maf else None,
            "fuel_consumption_kml": round(km_per_liter, 2) if km_per_liter else None,
            "fuel_flow_lh": round(fuel_flow, 2) if fuel_flow else None,
            "distance_traveled_km": round(distance, 3) if distance else None,
            "dtc_codes": [{"code": code[0], "description": code[1]} for code in dtc] if dtc else [],
            "has_errors": bool(dtc),
            "trip_start": self.simulator.trip_start_time if self.use_simulator else None
        }
        
        return snapshot
    
    def _calculate_fuel_consumption(self, speed, maf):
        """Calculate fuel consumption"""
        if speed is None or maf is None or speed == 0:
            return None, None
        
        try:
            AFR = 14.7
            GAS_DENSITY = 720  # g/L
            
            fuel_flow = (maf * 3600) / (AFR * GAS_DENSITY)
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
                print(f"⚠️  [{self.vehicle_id}] API returned status {response.status_code}")
                return False
                
        except requests.exceptions.ConnectionError:
            # Only print this once, not every iteration
            return False
        except Exception as e:
            print(f"⚠️  [{self.vehicle_id}] API error: {e}")
            return False
    
    def stop(self):
        """Stop data collection"""
        if self.connection:
            self.connection.stop()
        print(f"✅ [{self.vehicle_id}] Stopped data collection")

# ====== MAIN ======

def main():
    """Main execution"""
    print(f"\n{'='*70}")
    print(f"🚗 Vehicle Data Collector - {VEHICLE_ID}")
    print(f"📡 Mode: {'CUSTOM SIMULATOR' if USE_SIMULATOR else 'REAL DEVICE'}")
    print(f"💾 Local Storage: {LOCAL_JSON_FILE}")
    print(f"☁️  API Endpoint: {API_ENDPOINT if SEND_TO_API else 'DISABLED'}")
    print(f"{'='*70}\n")
    
    try:
        collector = VehicleDataCollector(VEHICLE_ID, VEHICLE_TYPE, USE_SIMULATOR)
    except Exception as e:
        print(f"❌ Failed to initialize: {e}")
        return
    
    # Initial delay
    time.sleep(1)
    
    api_warning_shown = False
    
    try:
        iteration = 0
        while True:
            iteration += 1
            
            # Get current data snapshot
            snapshot = collector.get_current_snapshot()
            
            # Save locally
            local_saved = collector.save_local(snapshot)
            
            # Send to API
            api_sent = collector.send_to_api(snapshot)
            
            # Show API warning only once
            if not api_sent and not api_warning_shown and SEND_TO_API:
                print(f"⚠️  [{VEHICLE_ID}] Cannot connect to API (is server running?)\n")
                api_warning_shown = True
            
            # Display status
            print(f"[{iteration:04d}] 🕐 {snapshot['timestamp']}")
            print(f"  🌡️  Temp: {snapshot['coolant_temp_celsius']}°C | "
                  f"⚡ RPM: {snapshot['rpm']} | "
                  f"🏎️  Speed: {snapshot['speed_kmh']} km/h")
            print(f"  ⛽ Fuel: {snapshot['fuel_level_percent']}% | "
                  f"📊 Consumption: {snapshot['fuel_consumption_kml']} km/L | "
                  f"📏 Distance: {snapshot['distance_traveled_km']} km")
            print(f"  💾 Local: {'✓' if local_saved else '✗'} | "
                  f"☁️  API: {'✓' if api_sent else '✗'}")
            
            if snapshot['has_errors']:
                print(f"  ⚠️  Errors: {snapshot['dtc_codes']}")
            
            print()
            
            time.sleep(UPDATE_INTERVAL)
            
    except KeyboardInterrupt:
        print(f"\n\n🛑 Stopping {VEHICLE_ID}...")
        collector.stop()
        if USE_SIMULATOR:
            print(f"📏 Total distance: {collector.simulator.distance:.2f} km")
        print(f"📁 Final data saved to: {LOCAL_JSON_FILE}")


if __name__ == "__main__":
    main()