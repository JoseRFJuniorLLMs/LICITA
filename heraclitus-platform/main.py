import sys
from pathlib import Path

# Adiciona a pasta 'domains' ao PATH para permitir imports limpos
sys.path.append(str(Path(__file__).parent / 'domains'))

def bootstrap():
    print('==================================================')
    print('🏛️  HERACLITUS ENTERPRISE PLATFORM - INITIALIZED 🏛️')
    print('==================================================')
    print('-> Verificando integridade dos módulos...')
    try:
        from procurement.domain.models.bid import Bid
        sample_bid = Bid(id='123', code='PNCP-2026', value=500000.00)
        print(f'[OK] Domínio Procurement carregado com sucesso!')
        print(f'[INFO] Objeto de teste criado: {sample_bid}')
    except Exception as e:
        print(f'[ERRO] Falha ao carregar domínios: {e}')

if __name__ == '__main__':
    bootstrap()
