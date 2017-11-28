from .marketplayer import MarketPlayer
from .arbitrageur import Arbitrageur
from .banker import Banker
from .randomizer import Randomizer
from .centralbank import CentralBank
from .speculator import HavvenSpeculator
from .nomin_shorter import NominShorter, HavvenEscrowNominShorter
from .merchant import Merchant, Buyer

# player names for the UI sliders
player_names = {
    # 'CentralBank': CentralBank,
    'Arbitrageur': Arbitrageur,
    'Banker': Banker,
    'Randomizer': Randomizer,
    'NominShorter': NominShorter,
    'HavvenEscrowNominShorter': HavvenEscrowNominShorter,
    'HavvenSpeculator': HavvenSpeculator,
    'Merchant': Merchant,
    'Buyer': Buyer
}
