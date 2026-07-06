import logging
from fastapi import APIRouter, Request
from app.state import state
from app import upbit_service as upbit
from app.config import settings
from telegram import Bot

logger = logging.getLogger(__name__)
router = APIRouter()


async def _notify(text: str):
    try:
        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(chat_id=settings.telegram_chat_id, text=text)
    except Exception as e:
        logger.error(f"텔레그램 알림 실패: {e}")


@router.post("/webhook")
async def webhook(request: Request):
    import json as _json
    raw = await request.body()
    logger.info(f"[RAW] headers={dict(request.headers)} body={raw.decode('utf-8', errors='replace')}")

    try:
        body = _json.loads(raw) if raw else {}
    except Exception:
        body = {}

    action = body.get("action", "").lower()
    raw_ticker = body.get("ticker") or body.get("symbol") or ""

    # JSON 파싱 실패 또는 필드 없을 때 TradingView 기본 plain text 파싱
    # 형식: "Strategy: order buy @ 0.5 filled on TAIKOKRW. New strategy position is 1"
    if not action or not raw_ticker:
        import re
        text = raw.decode("utf-8", errors="replace")
        m = re.search(r"(?:order|오더)\s+(buy|sell).*?(?:on|필드 온)\s+(\w+)", text, re.IGNORECASE)
        if m:
            action = m.group(1).lower()
            raw_ticker = m.group(2)
    raw_ticker = raw_ticker.upper()
    for suffix in ("USDT", "USD", "BUSD", "PERP", "KRW"):
        if raw_ticker.endswith(suffix):
            raw_ticker = raw_ticker[:-len(suffix)]
            break
    ticker = f"KRW-{raw_ticker}" if raw_ticker and not raw_ticker.startswith("KRW-") else raw_ticker

    logger.info(f"[PARSED] action={action} ticker={ticker}")

    if not action or not ticker:
        return {"status": "ignored", "reason": "action/ticker 누락"}

    if not state.enabled:
        return {"status": "ignored", "reason": "봇 비활성화 상태"}

    if action == "buy":
        if state.positions.get(ticker) == "long":
            return {"status": "ignored", "reason": f"{ticker} 이미 보유 중"}

        result = await upbit.buy_market_order(ticker)
        if result:
            state.positions[ticker] = "long"
            price = await upbit.get_current_price(ticker)
            await _notify(f"✅ 매수 완료\n{ticker}\n현재가: {price:,.2f}원")
            logger.info(f"매수 완료: {ticker} {result}")
        else:
            await _notify(f"❌ 매수 실패: {ticker}")
            logger.error(f"매수 실패: {ticker} {result}")

    elif action == "sell":
        if state.positions.get(ticker) != "long":
            return {"status": "ignored", "reason": f"{ticker} 보유 포지션 없음"}

        result = await upbit.sell_market_order(ticker)
        if result:
            state.positions[ticker] = None
            price = await upbit.get_current_price(ticker)
            await _notify(f"✅ 매도 완료\n{ticker}\n현재가: {price:,.2f}원")
            logger.info(f"매도 완료: {ticker} {result}")
        else:
            await _notify(f"❌ 매도 실패: {ticker}")
            logger.error(f"매도 실패: {ticker} {result}")

    else:
        return {"status": "ignored", "reason": f"알 수 없는 action: {action}"}

    return {"status": "ok", "action": action, "ticker": ticker}
