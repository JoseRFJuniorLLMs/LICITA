from domain.models.bid import Bid

class AnalyzeBidUseCase:
    def execute(self, bid: Bid) -> bool:
        print(f'Analisando viabilidade do edital: {bid.code}')
        return bid.value > 100000.0
