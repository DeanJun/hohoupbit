import asyncio
import pyupbit
from app.config import settings

BUY_RATIO = 0.9995  # 수수료 고려 99.95%

_upbit: pyupbit.Upbit | None = None


def get_upbit() -> pyupbit.Upbit:
    global _upbit
    if _upbit is None:
        _upbit = pyupbit.Upbit(settings.upbit_access_key, settings.upbit_secret_key)
    return _upbit


async def get_balance_krw() -> float:
    loop = asyncio.get_event_loop()
    upbit = get_upbit()
    result = await loop.run_in_executor(None, lambda: upbit.get_balance("KRW"))
    return float(result or 0)


async def get_balance_coin(ticker: str) -> float:
    loop = asyncio.get_event_loop()
    upbit = get_upbit()
    coin = ticker.replace("KRW-", "")
    result = await loop.run_in_executor(None, lambda: upbit.get_balance(coin))
    return float(result or 0)


async def get_current_price(ticker: str) -> float:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: pyupbit.get_current_price(ticker))
    return float(result or 0)


async def _get_orderbook(ticker: str) -> dict:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: pyupbit.get_orderbook(ticker))
    if isinstance(result, list):
        return result[0] if result else {}
    return result or {}


async def buy_market_order(ticker: str) -> dict:
    import logging
    logger = logging.getLogger(__name__)
    loop = asyncio.get_event_loop()
    upbit = get_upbit()

    orderbook = await _get_orderbook(ticker)
    ask_price = orderbook['orderbook_units'][0]['ask_price']

    krw = await get_balance_krw()
    volume = round(krw * BUY_RATIO / ask_price, 8)

    logger.info(f"[BUY] ticker={ticker} krw={krw} ask_price={ask_price} volume={volume}")
    try:
        result = await loop.run_in_executor(None, lambda: upbit.buy_limit_order(ticker, ask_price, volume))
    except Exception as e:
        logger.error(f"[BUY] exception={e}")
        return None
    logger.info(f"[BUY] result={result}")
    return result


async def sell_market_order(ticker: str) -> dict:
    import logging
    logger = logging.getLogger(__name__)
    loop = asyncio.get_event_loop()
    upbit = get_upbit()

    orderbook = await _get_orderbook(ticker)
    bid_price = orderbook['orderbook_units'][0]['bid_price']

    qty = await get_balance_coin(ticker)

    logger.info(f"[SELL] ticker={ticker} bid_price={bid_price} qty={qty}")
    try:
        result = await loop.run_in_executor(None, lambda: upbit.sell_limit_order(ticker, bid_price, qty))
    except Exception as e:
        logger.error(f"[SELL] exception={e}")
        return None
    logger.info(f"[SELL] result={result}")
    return result


async def get_all_balances() -> list[dict]:
    loop = asyncio.get_event_loop()
    upbit = get_upbit()
    result = await loop.run_in_executor(None, upbit.get_balances)
    return result or []
