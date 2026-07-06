import logging
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.webhook import router as webhook_router
from app.telegram_bot import build_app
from app.state import state
from app import upbit_service as upbit

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

logger = logging.getLogger(__name__)
_tg_app = None


async def restore_positions():
    try:
        balances = await upbit.get_all_balances()
        for b in balances:
            currency = b.get("currency", "")
            balance = float(b.get("balance", 0))
            if currency == "KRW" or balance <= 0:
                continue
            ticker = f"KRW-{currency}"
            state.positions[ticker] = "long"
            logger.info(f"[RESTORE] 포지션 복구: {ticker} ({balance})")
        logger.info(f"[RESTORE] 복구 완료: {state.positions}")
    except Exception as e:
        logger.error(f"[RESTORE] 포지션 복구 실패: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _tg_app
    await restore_positions()
    _tg_app = build_app()
    await _tg_app.initialize()
    await _tg_app.start()
    await _tg_app.updater.start_polling()
    yield
    await _tg_app.updater.stop()
    await _tg_app.stop()
    await _tg_app.shutdown()


app = FastAPI(title="HohoUpbit", lifespan=lifespan)
app.include_router(webhook_router)
