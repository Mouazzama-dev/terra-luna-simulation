from collections import namedtuple
from decimal import Decimal as Dec
from typing import List, Tuple, Optional

from mesa import Agent

from core import orderbook as ob
from managers import HavvenManager as hm
from core import stats as st


Portfolio = namedtuple(
    "Portfolio", ["fiat", "escrowed_havvens", "havvens", "nomins", "issued_nomins"])


class MarketPlayer(Agent):
    """
    A generic agent with a fixed initial wealth in fiat,
    with which it must buy into the market.
    The agent may escrow havvens in order to issue nomins,
    and use various strategies in order to trade in the marketplace.
    Its aim is to increase its own wealth.
    """

    def __init__(self, unique_id: int, havven_model: "model.HavvenModel",
                 fiat: Dec = Dec(0), havvens: Dec = Dec(0),
                 nomins: Dec = Dec(0)) -> None:
        super().__init__(unique_id, havven_model)
        self.fiat: Dec = Dec(fiat)
        self.havvens: Dec = Dec(havvens)
        self.nomins: Dec = Dec(nomins)
        self.escrowed_havvens: Dec = Dec(0)
        self.issued_nomins: Dec = Dec(0)

        # values that are currently used in orders
        self.unavailable_fiat: Dec = Dec(0)
        self.unavailable_havvens: Dec = Dec(0)
        self.unavailable_nomins: Dec = Dec(0)

        self.initial_wealth: Dec = self.wealth()

        self.orders: List["ob.LimitOrder"] = []
        self.trades: List["ob.TradeRecord"] = []

    def __str__(self) -> str:
        return self.name

    def setup(self, initial_value: Dec) -> None:
        """
        A function that defines how to give the Player wealth based
        on the same initial value for everyone
        """
        pass

    @property
    def havven_fiat_market(self) -> "ob.OrderBook":
        """The havven-fiat market this player trades on."""
        return self.model.market_manager.havven_fiat_market

    @property
    def nomin_fiat_market(self) -> "ob.OrderBook":
        """The nomin-fiat market this player trades on."""
        return self.model.market_manager.nomin_fiat_market

    @property
    def havven_nomin_market(self) -> "ob.OrderBook":
        """The havven-nomin market this player trades on."""
        return self.model.market_manager.havven_nomin_market

    @property
    def name(self) -> str:
        """
        The name of this object; its type and its unique id.
        """
        return f"{self.__class__.__name__} {self.unique_id}"

    def _fraction(self, qty: Dec, divisor: Dec = Dec(3),
                  minimum: Dec = Dec(1)) -> Dec:
        """
        Return a fraction of the given quantity, with a minimum.
        Used for depleting reserves gradually.
        """
        return max(hm.round_decimal(qty / divisor), min(minimum, qty))

    def cancel_orders(self) -> None:
        """
        Cancel all of this agent's orders.
        """
        for order in list(self.orders):
            order.cancel()

    def wealth(self) -> Dec:
        """
        Return the total wealth of this agent at current fiat prices.
        """
        return self.model.fiat_value(havvens=(self.havvens + self.escrowed_havvens),
                                     nomins=(self.nomins - self.issued_nomins),
                                     fiat=self.fiat)

    def portfolio(self, fiat_values: bool = False
                  ) -> Tuple[Dec, Dec, Dec, Dec, Dec]:
        """
        Return the parts of the agent that dictate its wealth.
        If fiat_value is True, then return the equivalent fiat values at the going market rates.
        """

        fiat = self.fiat
        havvens = self.havvens
        escrowed_havvens = self.escrowed_havvens
        nomins = self.nomins
        issued_nomins = self.issued_nomins

        if fiat_values:
            v_f = self.model.fiat_value
            havvens = v_f(havvens=havvens)
            escrowed_havvens = v_f(havvens=escrowed_havvens)
            nomins = v_f(nomins=nomins)
            issued_nomins = v_f(nomins=issued_nomins)

        return Portfolio(fiat=fiat, havvens=havvens, escrowed_havvens=escrowed_havvens,
                         nomins=nomins, issued_nomins=issued_nomins)

    def reset_initial_wealth(self) -> Dec:
        """
        Reset this agent's initial wealth to the current wealth, returning the old value.
        """
        old = self.initial_wealth
        self.initial_wealth = self.wealth()
        return old

    def profit(self) -> Dec:
        """
        Return the total profit accrued over the initial wealth.
        May be negative.
        """
        return self.wealth() - self.initial_wealth

    def profit_fraction(self) -> Dec:
        """
        Return profit accrued as a fraction of initial wealth.
        May be negative.
        """
        if hm.round_decimal(self.initial_wealth) != 0:
            return hm.round_decimal(self.profit() / self.initial_wealth)
        else:
            return Dec('0')

    def transfer_fiat_to(self, recipient: "MarketPlayer",
                         value: Dec) -> bool:
        """
        Transfer a positive value of fiat to the recipient,
        if balance is sufficient. Return True on success.
        """
        return self.model.market_manager.transfer_fiat(self, recipient, value)

    def transfer_havvens_to(self, recipient: "MarketPlayer",
                            value: Dec) -> bool:
        """
        Transfer a positive value of havvens to the recipient,
        if balance is sufficient. Return True on success.
        """
        return self.model.market_manager.transfer_havvens(self, recipient, value)

    def transfer_nomins_to(self, recipient: "MarketPlayer",
                           value: Dec) -> bool:
        """
        Transfer a positive value of nomins to the recipient,
        if balance is sufficient. Return True on success.
        """
        return self.model.market_manager.transfer_nomins(self, recipient, value)

    def escrow_havvens(self, value: Dec) -> bool:
        """
        Escrow a positive value of havvens in order to be able to issue
        nomins against them.
        """
        return self.model.mint.escrow_havvens(self, value)

    def unescrow_havvens(self, value: Dec) -> bool:
        """
        Unescrow a quantity of havvens, if there are not too many
        issued nomins locking it.
        """
        return self.model.mint.unescrow_havvens(self, value)

    def available_escrowed_havvens(self) -> Dec:
        """
        Return the quantity of escrowed havvens which is not
        locked by issued nomins. May be negative.
        """
        return self.model.mint.available_escrowed_havvens(self)

    def unavailable_escrowed_havvens(self) -> Dec:
        """
        Return the quantity of locked escrowed havvens,
        having had nomins issued against it.
        May be greater than total escrowed havvens.
        """
        return self.model.mint.unavailable_escrowed_havvens(self)

    def max_issuance_rights(self) -> Dec:
        """
        The total quantity of nomins this agent has a right to issue.
        """
        return self.model.mint.max_issuance_rights(self)

    def remaining_issuance_rights(self) -> Dec:
        """
        Return the remaining quantity of tokens this agent can issued on the back of their
        escrowed havvens. May be negative.
        """
        return self.model.mint.remaining_issuance_rights(self)

    def issue_nomins(self, value: Dec) -> bool:
        """
        Issue a positive value of nomins against currently escrowed havvens,
        up to the utilisation ratio maximum.
        """
        return self.model.mint.issue_nomins(self, value)

    def burn_nomins(self, value: Dec) -> bool:
        """
        Burn a positive value of issued nomins, which frees up havvens.
        """
        return self.model.mint.burn_nomins(self, value)

    def _sell_quoted(self, book: "ob.OrderBook", quantity: Dec) -> Optional["ob.Bid"]:
        """
        Sell a quantity of the quoted currency into the given market.
        """
        remaining_quoted = self.__getattribute__(f"available_{book.quoted}")
        quantity = min(quantity, remaining_quoted)
        if quantity < Dec('0.0005'): # TODO: remove workaround, and/or factor into epsilon variable
            return None

        next_qty = hm.round_decimal(min(quantity, book.lowest_ask_quantity()) / book.lowest_ask_price())
        pre_sold = self.__getattribute__(f"available_{book.quoted}")
        bid = book.buy(next_qty, self)
        total_sold = pre_sold - self.__getattribute__(f"available_{book.quoted}")

        # Keep on bidding until we either run out of reserves or sellers, or we've bought enough.
        while bid is not None and not bid.active and total_sold < quantity and len(book.asks) == 0:
            next_qty = hm.round_decimal(min(quantity - total_sold, book.lowest_ask_quantity()) / book.lowest_ask_price())
            pre_sold = self.__getattribute__(f"available_{book.quoted}")
            bid = book.buy(next_qty, self)
            total_sold += pre_sold - self.__getattribute__(f"available_{book.quoted}")

        if total_sold < quantity:
            if bid is not None:
                bid.cancel()
            price = book.lowest_ask_price()
            bid = book.bid(price, hm.round_decimal((quantity - total_sold) / price), self)

        return bid

    def _sell_base(self, book: "ob.OrderBook", quantity: Dec) -> Optional["ob.Ask"]:
        """
        Sell a quantity of the base currency into the given market.
        """
        return book.sell(quantity, self)

    def sell_nomins_for_havvens(self, quantity: Dec) -> Optional["ob.Bid"]:
        """
        Sell a quantity of nomins to buy havvens.
        """
        return self._sell_quoted(self.havven_nomin_market, quantity)

    def sell_havvens_for_nomins(self, quantity: Dec) -> Optional["ob.Ask"]:
        """
        Sell a quantity of havvens to buy nomins.
        """
        return self._sell_base(self.havven_nomin_market, quantity)

    def sell_fiat_for_havvens(self, quantity: Dec) -> Optional["ob.Bid"]:
        """
        Sell a quantity of fiat to buy havvens.
        """
        return self._sell_quoted(self.havven_fiat_market, quantity)

    def sell_havvens_for_fiat(self, quantity: Dec) -> Optional["ob.Ask"]:
        """
        Sell a quantity of havvens to buy fiat.
        """
        return self._sell_base(self.havven_fiat_market, quantity)

    def sell_fiat_for_nomins(self, quantity: Dec) -> Optional["ob.Bid"]:
        """
        Sell a quantity of fiat to buy nomins.
        """
        return self._sell_quoted(self.nomin_fiat_market, quantity)

    def sell_nomins_for_fiat(self, quantity: Dec) -> Optional["ob.Ask"]:
        """
        Sell a quantity of nomins to buy fiat.
        """
        return self._sell_base(self.nomin_fiat_market, quantity)

    def _sell_quoted_with_fee(self, book: "ob.OrderBook", quantity: Dec) -> Optional["ob.Bid"]:
        """
        Sell a quantity of the quoted currency into the given market, including the
        fee, as calculated by the provided function.
        """
        price = book.lowest_ask_price()
        return book.buy(hm.round_decimal(book.quoted_qty_rcvd(quantity) / price), self)

    def _sell_base_with_fee(self, book: "ob.OrderBook", quantity: Dec) -> Optional["ob.Ask"]:
        """
        Sell a quantity of the base currency into the given market, including the
        fee, as calculated by the provided function.
        """
        return book.sell(book.base_qty_rcvd(quantity), self)

    def sell_nomins_for_havvens_with_fee(self, quantity: Dec) -> Optional["ob.Bid"]:
        """
        Sell a quantity of nomins (including fee) to buy havvens.
        """
        return self._sell_quoted_with_fee(self.havven_nomin_market, quantity)

    def sell_havvens_for_nomins_with_fee(self, quantity: Dec) -> Optional["ob.Ask"]:
        """
        Sell a quantity of havvens (including fee) to buy nomins.
        """
        return self._sell_base_with_fee(self.havven_nomin_market, quantity)

    def sell_fiat_for_havvens_with_fee(self, quantity: Dec) -> Optional["ob.Bid"]:
        """
        Sell a quantity of fiat (including fee) to buy havvens.
        """
        return self._sell_quoted_with_fee(self.havven_fiat_market, quantity)

    def sell_havvens_for_fiat_with_fee(self, quantity: Dec) -> Optional["ob.Ask"]:
        """
        Sell a quantity of havvens (including fee) to buy fiat.
        """
        return self._sell_base_with_fee(self.havven_fiat_market, quantity)

    def sell_fiat_for_nomins_with_fee(self, quantity: Dec) -> Optional["ob.Bid"]:
        """
        Sell a quantity of fiat (including fee) to buy nomins.
        """
        return self._sell_quoted_with_fee(self.nomin_fiat_market, quantity)

    def sell_nomins_for_fiat_with_fee(self, quantity: Dec) -> Optional["ob.Ask"]:
        """
        Sell a quantity of nomins (including fee) to buy fiat.
        """
        return self._sell_base_with_fee(self.nomin_fiat_market, quantity)

    def place_havven_fiat_bid(self, quantity: Dec, price: Dec) -> Optional["ob.Bid"]:
        """
        Place a bid for a quantity of havvens, at a price in fiat.
        """
        return self.havven_fiat_market.bid(price, quantity, self)

    def place_havven_fiat_ask(self, quantity: Dec, price: Dec) -> Optional["ob.Ask"]:
        """
        Place an ask for fiat with a quantity of havvens, at a price in fiat.
        """
        return self.havven_fiat_market.ask(price, quantity, self)

    def place_nomin_fiat_bid(self, quantity: Dec, price: Dec) -> Optional["ob.Bid"]:
        """
        Place a bid for a quantity of nomins, at a price in fiat.
        """
        return self.nomin_fiat_market.bid(price, quantity, self)

    def place_nomin_fiat_ask(self, quantity: Dec, price: Dec) -> Optional["ob.Ask"]:
        """
        Place an ask for fiat with a quantity of nomins, at a price in fiat.
        """
        return self.nomin_fiat_market.ask(price, quantity, self)

    def place_havven_nomin_bid(self, quantity: Dec, price: Dec) -> Optional["ob.Bid"]:
        """
        Place a bid for a quantity of havvens, at a price in nomins.
        """
        return self.havven_nomin_market.bid(price, quantity, self)

    def place_havven_nomin_ask(self, quantity: Dec, price: Dec) -> Optional["ob.Ask"]:
        """
        Place an ask for nomins with a quantity of havvens, at a price in nomins.
        """
        return self.havven_nomin_market.ask(price, quantity, self)

    def place_bid_with_fee(self, book: "ob.OrderBook", quantity: Dec, price: Dec) -> Optional["ob.Bid"]:
        """
        Place a bid for a quantity of the base currency at a price in the quoted
        currency in the given book, including the fee.
        """
        # Note, only works because the fee is multiplicative, we're calculating the fee not
        # on the quantity we are actually transferring, which is (quantity*price)
        return book.bid(price, book.quoted_qty_rcvd(quantity), self)

    def place_ask_with_fee(self, book: "ob.OrderBook", quantity: Dec, price: Dec) -> Optional["ob.Ask"]:
        """
        Place an ask for a quantity of the base currency at a price in the quoted
        currency in the given book, including the fee.
        """
        return book.ask(price, book.base_qty_rcvd(quantity), self)

    def place_havven_fiat_bid_with_fee(self, quantity: Dec, price: Dec) -> Optional["ob.Bid"]:
        """
        Place a bid for a quantity of havvens, at a price in fiat, including the fee.
        """
        return self.place_bid_with_fee(self.havven_fiat_market, quantity, price)

    def place_havven_fiat_ask_with_fee(self, quantity: Dec, price: Dec) -> Optional["ob.Ask"]:
        """
        Place an ask for fiat with a quantity of havvens, including the fee, at a price in fiat.
        """
        return self.place_ask_with_fee(self.havven_fiat_market, quantity, price)

    def place_nomin_fiat_bid_with_fee(self, quantity: Dec, price: Dec) -> Optional["ob.Bid"]:
        """
        Place a bid for a quantity of nomins, at a price in fiat, including the fee.
        """
        return self.place_bid_with_fee(self.nomin_fiat_market, quantity, price)

    def place_nomin_fiat_ask_with_fee(self, quantity: Dec, price: Dec) -> Optional["ob.Ask"]:
        """
        Place an ask for fiat with a quantity of nomins, including the fee, at a price in fiat.
        """
        return self.place_ask_with_fee(self.nomin_fiat_market, quantity, price)

    def place_havven_nomin_bid_with_fee(self, quantity: Dec, price: Dec) -> Optional["ob.Bid"]:
        """
        Place a bid for a quantity of havvens, at a price in nomins, including the fee.
        """
        return self.place_bid_with_fee(self.havven_nomin_market, quantity, price)

    def place_havven_nomin_ask_with_fee(self, quantity: Dec, price: Dec) -> Optional["ob.Ask"]:
        """
        Place an ask for nomins with a quantity of havvens, including the fee, at a price in nomins.
        """
        return self.place_ask_with_fee(self.havven_nomin_market, quantity, price)

    @property
    def available_fiat(self) -> Dec:
        """
        This agent's quantity of fiat not tied up in orders.
        """
        return self.model.manager.round_decimal(self.fiat - self.unavailable_fiat)

    @property
    def available_havvens(self) -> Dec:
        """
        This agent's quantity of havvens not being tied up in orders.
        """
        return self.model.manager.round_decimal(self.havvens - self.unavailable_havvens)

    @property
    def available_nomins(self) -> Dec:
        """
        This agent's quantity of nomins not being tied up in orders.
        """
        return self.model.manager.round_decimal(self.nomins - self.unavailable_nomins)

    def round_values(self) -> None:
        """
        Apply rounding to this player's nomin, fiat, havven values.
        """
        self.nomins = hm.round_decimal(self.nomins)
        self.fiat = hm.round_decimal(self.fiat)
        self.havvens = hm.round_decimal(self.havvens)

    def notify_cancelled(self, order: "ob.LimitOrder") -> None:
        """
        Notify this agent that its order was cancelled.
        """
        pass

    def notify_trade(self, record: "ob.TradeRecord") -> None:
        """
        Notify this agent that its order was filled.
        """
        self.trades.append(record)

    def step(self) -> None:
        # pass
        """
        The agent's behavior at each step of the simulation, including burning excess nomins.
        """
        # Calculate how many nomins to burn this step
        nomins_to_burn = self.calculate_burn_rate()
        print("in step function of makrketplayer : nomins to burn" , nomins_to_burn)

        # Burn the calculated amount of nomins
        if nomins_to_burn > Dec('0'):
            self.burn_nomins(nomins_to_burn)
    
    def calculate_burn_rate(self) -> Dec:
        """
        Calculate the burn rate based on the excess supply of nomins in the market.
        The excess supply could be determined by the difference between the current supply and a target supply.
        This is a simplified example for demonstration purposes.
        """
        # Define target supply for nomins (could be set based on market conditions or predefined)
        target_supply = Dec('10')  # Placeholder value

         # Get the current supply from the stats module function
        current_supply = Dec(st.nomin_supply(self.model))

        # If current supply is zero, we cannot perform division, so set burn rate to zero
        if current_supply == Dec('0'):
            return Dec('0')

        # Calculate excess supply
        excess_supply = max(current_supply - target_supply, Dec('0'))

        # Define a burn percentage, which could be a system parameter
        burn_percentage = Dec('0.01')  # 1% burn rate

        # Calculate the burn amount based on the burn rate and the agent's proportion of the excess supply
        agent_excess_nomins = max(self.nomins - self.issued_nomins, Dec('0'))
        # print("agent_excess_nomins" , agent_excess_nomins)
        agent_burn_amount = burn_percentage * (agent_excess_nomins / current_supply) * excess_supply
        # print("agent_burn_amount " , agent_burn_amount)

        return agent_burn_amount
