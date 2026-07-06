# hohoupbit 현재 상태 컨텍스트

## 프로젝트 개요
FastAPI 기반 Upbit 자동매매 봇. TradingView 웹훅 수신 → Upbit 주문 → 텔레그램 알림.

---

## 서버 환경
- **서버 도메인**: `frontline.p-e.kr` (SSL 인증서 있음)
- **서버 IP**: `101.79.23.117`
- **FastAPI 포트**: `8000`
- **웹훅 URL**: `https://frontline.p-e.kr/webhook` 또는 `https://101.79.23.117/webhook` (둘 다 작동)
- **nginx**: `/etc/nginx/sites-available/frontline` (symlink) → `/webhook` location → `localhost:8000`
- **서버 실행**: `nohup uvicorn main:app --host 0.0.0.0 --port 8000 >> /tmp/hohoupbit.log 2>&1 &`
- **로그**: `/tmp/hohoupbit.log`

---

## 인증 정보 (.env)
```
UPBIT_ACCESS_KEY=x2cWwgqZQqlyeJxGTYpmJbN1wuRfb1lP3wDQsqz6
UPBIT_SECRET_KEY=w2dOUwdPxQSykGL9xd9uHt5fsBWjixzU6UMfiSKO
TELEGRAM_BOT_TOKEN=8639258768:AAGu3ap6L385YcZAvUOIfa0xWKN0xVWsfUk
TELEGRAM_CHAT_ID=5221080267
```

---

## 핵심 파일 현재 상태

### main.py
서버 시작 시 `restore_positions()` 호출 → 실제 Upbit 잔고 기반 `state.positions` 자동 복구.
코인 잔고 > 0인 모든 티커를 `"long"`으로 설정. 서버 재시작 시 포지션 유실 방지.
```python
async def restore_positions():
    balances = await upbit.get_all_balances()
    for b in balances:
        currency = b.get("currency", "")
        balance = float(b.get("balance", 0))
        if currency == "KRW" or balance <= 0:
            continue
        ticker = f"KRW-{currency}"
        state.positions[ticker] = "long"
```

### app/state.py
```python
@dataclass
class AppState:
    enabled: bool = True   # 서버 시작 시 자동 활성화
    positions: dict = field(default_factory=dict)  # {"KRW-BTC": "long"}
state = AppState()
```

### app/webhook.py 주요 로직
- `await request.body()` → raw body 로깅 후 JSON 파싱 시도
- **JSON 파싱 실패 시 plain text fallback 파싱** (TradingView 기본 템플릿 지원)
  - 정규식: `(?:order|오더)\s+(buy|sell).*?(?:on|필드 온)\s+(\w+)`
  - 영어/한국어 TradingView 기본 템플릿 둘 다 지원
- symbol 변환: `body.get("ticker") or body.get("symbol")` → suffix 제거 → KRW- 접두사 추가
  - 제거 suffix 목록: `("USDT", "USD", "BUSD", "PERP", "KRW")`
  - 예: `ONGKRW` → `KRW-ONG`, `0GKRW` → `KRW-0G`, `MIRAKRW` → `KRW-MIRA`
- 매수: `state.positions.get(ticker) == "long"` 이면 무시 (중복 방지)
- 매도: `state.positions.get(ticker) != "long"` 이면 무시

### app/upbit_service.py (호가 기반 지정가)
```python
BUY_RATIO = 0.9995

# 매수: 매도1호가로 지정가 주문
async def buy_market_order(ticker):
    orderbook = await _get_orderbook(ticker)
    ask_price = orderbook['orderbook_units'][0]['ask_price']
    volume = round(krw * BUY_RATIO / ask_price, 8)
    result = upbit.buy_limit_order(ticker, ask_price, volume)

# 매도: 매수1호가로 지정가 주문
async def sell_market_order(ticker):
    orderbook = await _get_orderbook(ticker)
    bid_price = orderbook['orderbook_units'][0]['bid_price']
    qty = get_balance_coin(ticker)
    result = upbit.sell_limit_order(ticker, bid_price, qty)

# pyupbit get_orderbook() 반환 타입 호환 처리 (신버전 dict, 구버전 list)
async def _get_orderbook(ticker):
    result = await loop.run_in_executor(None, lambda: pyupbit.get_orderbook(ticker))
    if isinstance(result, list):
        return result[0] if result else {}
    return result or {}
```
- 함수명은 `buy_market_order`/`sell_market_order` 그대로 유지 (webhook.py 호환)
- 실제로는 호가 기반 지정가 주문 (슬리피지 감소)

### 텔레그램 알림 형식
```
✅ 매수 완료
KRW-ONG
현재가: 82.87원   ← 소수점 2자리
```

---

## TradingView 웹훅 설정

### 지원하는 메시지 포맷 (둘 다 자동 처리)

**JSON 형식** (구버전, 여전히 지원):
```json
{"action":"{{strategy.order.action}}","symbol":"{{ticker}}","price":"{{close}}"}
```

**Plain text 기본 템플릿** (신규 추가, 한국어/영어 둘 다 OK):
```
Date RSI Strategy v3: 오더 {{strategy.order.action}} @ {{strategy.order.contracts}} 필드 온 {{ticker}}. 뉴 스트래티지 포지션은 {{strategy.position_size}}
```
→ TradingView 알림 설정 시 메시지를 기본값 그대로 두면 됨. 매번 JSON으로 바꿀 필요 없음.

- `price` 필드는 사용 안 함 (orderbook에서 직접 조회하므로 불필요)

### 제외된 티커
| 티커 | 이유 |
|------|------|
| KRW-AI | `not_supported_ord_type` (신규 코인 Upbit 제한) → 모니터링 안 함 |

### TradingView 중복 신호 문제
- TradingView가 동일 신호를 IP 2개에서 각각 전송 (`52.32.178.7`, `34.212.75.30`)
- `state.positions` 체크로 자동 중복 방지됨

---

## 알려진 이슈 및 해결 내역

| 이슈 | 원인 | 해결 |
|------|------|------|
| 405 Method Not Allowed | nginx에 /webhook location 없음 | nginx config에 proxy_pass 추가 |
| ONGKRW → KRW-ONGKRW 오변환 | suffix 목록에 KRW 없음 | `("USDT","USD","BUSD","PERP","KRW")` 추가 |
| KRW-AI 매수 실패 | `not_supported_ord_type` (Upbit 제한) | AI 티커 모니터링 제외 |
| 슬리피지 문제 | 시장가 주문 | 호가 기반 지정가 주문으로 변경 |
| 500 에러 (KRW-AHT, KRW-MOC 등 신규 티커) | pyupbit get_orderbook() dict 반환으로 변경 | isinstance 체크로 list/dict 모두 처리 |
| 서버 재시작 포지션 초기화 → sell 무시, KRW 묶임 | in-memory state | main.py restore_positions()로 시작 시 자동 복구 |
| plain text 파싱 실패 (0G, MIRA 등) | 정규식이 영어 "order"만 처리 | 한국어 "오더", "필드 온"도 포함하도록 정규식 수정 |
| UnderMinTotalBid | 포지션 초기화로 KRW 묶임 → 잔고 없이 매수 시도 | restore_positions()로 근본 원인 해결 |

---

## 서버 재시작 방법
```bash
pkill -f uvicorn
sleep 2
cd /root/hohoupbit
source venv/bin/activate
nohup uvicorn main:app --host 0.0.0.0 --port 8000 >> /tmp/hohoupbit.log 2>&1 &
```

## 주의사항
- 재시작 시 `restore_positions()`가 실행되어 포지션 자동 복구됨
- 단, `locked` 잔고(미체결 지정가 주문)는 `get_balance()` 기준으로 잡히지 않을 수 있음
- KRW 잔고 부족 시 `UnderMinTotalBid` 에러로 매수 실패 (Upbit 최소 주문 5,000원)
