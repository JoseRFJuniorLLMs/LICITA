import time

def run_worker():
    print('[Worker] Iniciando agente de processamento de IA... Press Ctrl+C to stop.')
    while True:
        # Loop de processamento assíncrono
        time.sleep(10)
