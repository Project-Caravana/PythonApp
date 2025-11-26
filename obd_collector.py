"""
Real OBD-II Data Collector - Individual Vehicle Script
Connects to actual OBD-II device via Bluetooth/Serial
Sends data to Caravana API
NO SIMULATION - Real hardware only
"""

import obd
import time
import json
import requests
from datetime import datetime
import os

# ====== CONFIGURATION ======
# For each vehicle we need to program the IoT device with its ID
# You have register the vehicle in the Dashboard and take the given ID to configure the IoT
# We have the same script for all vehicles, but the ID is different
VEHICLE_ID = "692632362c0531487d94520a"  # ⭐ ID do carro no MongoDB

# OBD Connection (adjust to your device)
COM_PORT = "COM3"  # Windows: COM3, COM4, etc. | Linux: /dev/rfcomm0 | Mac: /dev/tty.OBD-II
BAUD_RATE = None  # None for auto-detect, or specify: 9600, 38400, etc.

# API Configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:3000/api")  # ⭐ Ou use sua URL do Render
SEND_TO_API = True  # ⭐ Mudei para True

# Storage Configuration
LOCAL_STORAGE_DIR = "vehicle_data"
LOCAL_JSON_FILE = f"{LOCAL_STORAGE_DIR}/{VEHICLE_ID}_data.json"

# Update interval (seconds)
UPDATE_INTERVAL = 5  # ⭐ Aumentei para 5 segundos (evita sobrecarga)

# Retry configuration
MAX_CONNECTION_RETRIES = 3
RETRY_DELAY = 5

os.makedirs(LOCAL_STORAGE_DIR, exist_ok=True)

# ====== REAL OBD CONNECTION ======

class RealOBDCollector:
    """Collects data from real OBD-II device"""
    
    def __init__(self, vehicle_id, com_port, baud_rate=None):
        self.vehicle_id = vehicle_id
        self.com_port = com_port
        self.baud_rate = baud_rate
        self.connection = None
        self.all_readings = []
        
        # Distance tracking (distância desde a última leitura)
        self.last_speed = 0
        self.last_time = time.time()
        self.trip_start = datetime.now().isoformat()
        
        # Cached VIN (read once)
        self.vin = None
        
        # Acumuladores para cálculo de consumo
        self.total_fuel_consumed = 0.0  # Litros totais consumidos
    
    def connect(self):
        """Connect to real OBD-II device"""
        print(f"🔧 [{self.vehicle_id}] Connecting to OBD-II on {self.com_port}...")
        
        try:
            if self.baud_rate:
                self.connection = obd.OBD(self.com_port, baudrate=self.baud_rate)
            else:
                self.connection = obd.OBD(self.com_port)
            
            if not self.connection.is_connected():
                print(f"❌ [{self.vehicle_id}] Failed to connect to OBD-II")
                print(f"   Make sure:")
                print(f"   - OBD-II device is plugged into car")
                print(f"   - Car ignition is ON")
                print(f"   - Bluetooth is paired (if using Bluetooth)")
                print(f"   - Correct COM port: {self.com_port}")
                return False
            
            print(f"✅ [{self.vehicle_id}] Connected to OBD-II!")
            print(f"   Protocol: {self.connection.protocol_name()}")
            print(f"   Port: {self.connection.port_name()}")
            
            # Get VIN once
            self._read_vin()
            
            # Check supported commands
            self._check_supported_commands()
            
            return True
            
        except Exception as e:
            print(f"❌ [{self.vehicle_id}] Connection error: {e}")
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
        voltage_resp = self.connection.query(obd.commands.CONTROL_MODULE_VOLTAGE)
        dtc_resp = self.connection.query(obd.commands.GET_DTC)
        
        # Extract values (handle null responses)
        temp = self._extract_value(temp_resp)
        rpm = self._extract_value(rpm_resp)
        speed = self._extract_value(speed_resp, unit="km/h")
        fuel = self._extract_value(fuel_resp)
        maf = self._extract_value(maf_resp, unit="g/s")
        voltage = self._extract_value(voltage_resp, unit="V")
        dtc = dtc_resp.value if not dtc_resp.is_null() else []
        
        # Calculate distance traveled (desde a última leitura)
        now = time.time()
        dt = now - self.last_time
        distance_traveled = 0
        
        if speed is not None and speed > 0:
            # Distância = velocidade média * tempo (em horas)
            avg_speed = (speed + self.last_speed) / 2
            distance_traveled = avg_speed * (dt / 3600)  # km
        
        self.last_speed = speed if speed is not None else 0
        self.last_time = now
        
        # Calculate fuel consumption and flow
        fuel_consumed_now, fuel_flow = self._calculate_fuel_consumption(speed, maf, dt)
        
        if fuel_consumed_now:
            self.total_fuel_consumed += fuel_consumed_now
        
        # ⭐ Create snapshot in the format expected by your API
        snapshot = {
            # Dados de telemetria (conforme LeituraOBD model)
            "velocidade": round(speed, 1) if speed is not None else 0,
            "rpm": round(rpm, 0) if rpm is not None else 0,
            "temperatura": round(temp, 1) if temp is not None else 0,
            "nivelCombustivel": round(fuel, 1) if fuel is not None else 0,
            "voltagem": round(voltage, 2) if voltage is not None else 12.0,
            "consumoInstantaneo": round(fuel_flow, 2) if fuel_flow else 0,
            "distanciaPercorrida": round(distance_traveled, 3),  # ⭐ Distância DESDE a última leitura
            "horasMotor": round((time.time() - time.mktime(time.strptime(self.trip_start, "%Y-%m-%dT%H:%M:%S.%f"))) / 3600, 2),
            
            # Diagnósticos
            "milStatus": bool(dtc and len(dtc) > 0),
            "dtcCount": len(dtc) if dtc else 0,
            "falhas": self._format_dtc_for_api(dtc),
            
            # Campos opcionais (se disponível)
            "pressaoOleo": None,  # Não disponível via OBD padrão
            
            # Metadados locais (não enviados para API, apenas para log)
            "_metadata": {
                "timestamp": datetime.now().isoformat(),
                "vehicle_id": self.vehicle_id,
                "vin": self.vin,
                "trip_start": self.trip_start,
                "total_fuel_consumed": round(self.total_fuel_consumed, 3)
            }
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
    
    def _format_dtc_for_api(self, dtc):
        """Format DTC codes for API (conforme LeituraOBD model)"""
        if not dtc:
            return []
        
        try:
            formatted = []
            for code in dtc:
                if isinstance(code, tuple) and len(code) >= 1:
                    formatted.append({
                        "codigo": code[0],
                        "descricao": code[1] if len(code) > 1 else "Unknown",
                        "status": "pendente",
                        "detectadoEm": datetime.now().isoformat()
                    })
                else:
                    formatted.append({
                        "codigo": str(code),
                        "descricao": "Unknown",
                        "status": "pendente",
                        "detectadoEm": datetime.now().isoformat()
                    })
            return formatted
        except:
            return []
    
    def _calculate_fuel_consumption(self, speed, maf, dt):
        """Calculate fuel consumption for this interval"""
        if speed is None or maf is None or speed == 0 or maf == 0:
            return None, None
        
        try:
            AFR = 14.7  # Air-Fuel Ratio for gasoline
            GAS_DENSITY = 720  # g/L
            
            # Fuel flow in L/h
            fuel_flow = (maf * 3600) / (AFR * GAS_DENSITY)
            
            # Fuel consumed in this interval (liters)
            fuel_consumed = fuel_flow * (dt / 3600)
            
            return fuel_consumed, fuel_flow
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
                    "last_update": snapshot["_metadata"]["timestamp"],
                    "total_readings": len(self.all_readings),
                    "latest": snapshot,
                    "history": self.all_readings
                }, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"⚠️  [{self.vehicle_id}] Failed to save locally: {e}")
            return False
    
    def send_to_api(self, snapshot):
        """Send data to API endpoint (conforme CarroController.atualizarDadosOBD)"""
        if not SEND_TO_API:
            return True
        
        try:
            # ⭐ Remove metadados antes de enviar
            api_data = {k: v for k, v in snapshot.items() if k != "_metadata"}
            
            # ⭐ URL correta da API
            url = f"{API_BASE_URL}/vehicle/{self.vehicle_id}/dados-obd"
            
            response = requests.put(
                url,
                json=api_data,
                timeout=10,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                return True
            else:
                print(f"⚠️  API error: {response.status_code} - {response.text}")
                return False
                
        except requests.exceptions.ConnectionError:
            return False
        except Exception as e:
            print(f"⚠️  API request failed: {e}")
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
    print(f"🚗 Real OBD-II Data Collector - Caravana System")
    print(f"Vehicle ID: {VEHICLE_ID}")
    print(f"Port: {COM_PORT}")
    print(f"API: {API_BASE_URL}")
    print(f"Local Storage: {LOCAL_JSON_FILE}")
    print(f"{'='*70}\n")
    
    # Try to connect with retries
    collector = None
    for attempt in range(1, MAX_CONNECTION_RETRIES + 1):
        print(f"Connection attempt {attempt}/{MAX_CONNECTION_RETRIES}...")
        
        collector = RealOBDCollector(VEHICLE_ID, COM_PORT, BAUD_RATE)
        
        if collector.connect():
            break
        
        if attempt < MAX_CONNECTION_RETRIES:
            print(f"Retrying in {RETRY_DELAY} seconds...\n")
            time.sleep(RETRY_DELAY)
        else:
            print(f"\n❌ Failed to connect after {MAX_CONNECTION_RETRIES} attempts")
            print(f"\n💡 Troubleshooting tips:")
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
        print(f"✅ Starting data collection... (Press Ctrl+C to stop)")
        print(f"{'='*70}\n")
        
        while True:
            # Check if still connected
            if not collector.is_connected():
                print(f"\n❌ Lost connection to OBD-II device!")
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
                    print(f"⚠️  [{VEHICLE_ID}] Cannot connect to API (is server running?)\n")
                    api_warning_shown = True
                
                # Display status
                metadata = snapshot["_metadata"]
                print(f"[{iteration:04d}] 🕒 {metadata['timestamp']}")
                
                # Main metrics
                print(f"    🌡️  Temp: {snapshot['temperatura']}°C | ⚡ RPM: {snapshot['rpm']} | 🚗 Speed: {snapshot['velocidade']} km/h")
                print(f"    ⛽ Fuel: {snapshot['nivelCombustivel']}% | 📊 Flow: {snapshot['consumoInstantaneo']} L/h | 📏 Distance: {snapshot['distanciaPercorrida']} km")
                print(f"    💾 Local: {'✓' if local_saved else '✗'} | 🌐 API: {'✓' if api_sent else '✗'}")
                
                # Errors
                if snapshot['milStatus']:
                    print(f"    ⚠️  Diagnostic Codes: {snapshot['dtcCount']} error(s)")
                
                print()
                
            except Exception as e:
                print(f"❌ Error reading data: {e}")
            
            time.sleep(UPDATE_INTERVAL)
            
    except KeyboardInterrupt:
        print(f"\n\n🛑 Stopping {VEHICLE_ID}...")
        collector.stop()
        print(f"📊 Total fuel consumed: {collector.total_fuel_consumed:.2f} L")
        print(f"💾 Final data saved to: {LOCAL_JSON_FILE}")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        if collector:
            collector.stop()


if __name__ == "__main__":
    main()