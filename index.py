import requests
import time
import random
from datetime import datetime
import json

class OBDSimulator:
    """
    Simulador OBD-II Simplificado.
    Envia:
    - Velocidade (km/h)
    - Distância Percorrida no Intervalo (km)
    - Consumo Instantâneo (km/L) -> Valor direto, sem cálculo de litros aqui.
    """
    
    def __init__(self, api_url, carro_id):
        self.api_url = api_url
        self.carro_id = carro_id
        self.endpoint = f"{api_url}/api/vehicle/{carro_id}/dados-obd"
        
        # Estado inicial do veículo
        self.velocidade_atual = 0
        self.rpm_atual = 800  
        self.temperatura = 60  
        
    def gerar_dados(self, modo='rodando', intervalo_segundos=2):
        
        # 1. Definir comportamento e Consumo Instantâneo (km/L)
        # Note que agora 'eficiencia' É o dado que enviamos como 'consumoInstantaneo'
        consumo_kml = 0 
        
        if modo == 'parado':
            self.velocidade_atual = 0
            self.rpm_atual = random.randint(700, 900)
            consumo_kml = 0 # Parado faz 0 km/L (Backend vai tratar isso)
            
        elif modo == 'acelerando':
            self.velocidade_atual = min(self.velocidade_atual + random.randint(5, 15), 120)
            self.rpm_atual = random.randint(2000, 4500)
            consumo_kml = random.uniform(4.0, 6.0) # Bebe muito
            
        elif modo == 'rodando':
            self.velocidade_atual = random.randint(60, 90)
            self.rpm_atual = random.randint(1500, 2500)
            consumo_kml = random.uniform(10.0, 14.0) # Econômico
            
        elif modo == 'freando':
            self.velocidade_atual = max(self.velocidade_atual - random.randint(10, 20), 0)
            self.rpm_atual = random.randint(1000, 2000)
            consumo_kml = random.uniform(18.0, 25.0) # Cut-off (quase infinito)
        
        # Simula temperatura
        if self.temperatura < 90: self.temperatura += 0.5
        else: self.temperatura = random.uniform(88, 95)
        
        # 2. Calcular Distância (Física básica: v * t)
        distancia_intervalo_km = (self.velocidade_atual / 3600) * intervalo_segundos
        
        # 3. Monta payload (Simples e direto)
        dados_obd = {
            "velocidade": round(self.velocidade_atual, 1),
            "rpm": self.rpm_atual,
            "temperatura": round(self.temperatura, 1),
            "nivelCombustivel": random.randint(40, 90),
            
            # AQUI ESTÁ A MUDANÇA: Enviamos km/L direto
            "consumoInstantaneo": round(consumo_kml, 2), 
            
            # E a distância percorrida neste intervalo
            "distanciaPercorrida": float(f"{distancia_intervalo_km:.6f}"),
            
            "milStatus": False,
            "dtcCount": 0,
            "fonte": "simulador_v3_simples"
        }
            
        return dados_obd
    
    def enviar_dados(self, dados_obd):
        try:
            response = requests.put(
                self.endpoint,
                json=dados_obd,
                headers={"Content-Type": "application/json"},
                timeout=5
            )
            return response.status_code == 200
        except Exception as e:
            print(f"Erro: {e}")
            return False
    
    def simular_viagem(self, duracao_segundos=60):
        print(f"\n🚗 SIMULANDO (Enviando km/L direto)...")
        inicio = time.time()
        intervalo = 2 
        
        while (time.time() - inicio) < duracao_segundos:
            tempo = time.time() - inicio
            
            if tempo < 10: modo = 'parado'
            elif tempo < 25: modo = 'acelerando'
            elif tempo < 50: modo = 'rodando'
            else: modo = 'freando'
            
            dados = self.gerar_dados(modo, intervalo)
            self.enviar_dados(dados)
            
            print(f"Vel: {dados['velocidade']}km/h | Consumo: {dados['consumoInstantaneo']} km/L | Dist: {dados['distanciaPercorrida']:.4f}km")
            time.sleep(intervalo)
        
        print(f"✓ FIM")

if __name__ == "__main__":
    API_URL = "http://localhost:3000"
    CARRO_ID = "6926671eaec10accf19cab99" # SEU ID AQUI
    
    simulador = OBDSimulator(API_URL, CARRO_ID)
    simulador.simular_viagem(duracao_segundos=60)