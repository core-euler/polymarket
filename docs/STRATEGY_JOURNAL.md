# Strategy Journal

Журнал экспериментов с параметрами автоматической стратегии. Каждая
страт-версия (`strategy_configs.version`) получает запись с фиксацией
**параметров → гипотезы → результата → следующего шага**.

Цель — накопить достаточно сравнимых наблюдений, чтобы найти оптимальные
параметры эмпирически, а не наугад.

## Правила ведения

- Записи **append-only**: старая запись не редактируется, новая добавляется
  снизу. Если результат уточняется — добавляется секция «Update YYYY-MM-DD»
  внутри той же записи.
- Все даты в **UTC**.
- Источник истины по параметрам — таблица `strategy_configs` в Postgres.
  Перед записью копировать `parameters_json` и `paper_trading_rules_json`
  оттуда (`SELECT … FROM strategy_configs WHERE version = N`).
- Если стратегию ещё не сняли с активной — раздел «Result» помечается
  как _in-flight_ и дописывается после bump'а на следующую версию.

## Глоссарий параметров

### `parameters_json` (signal engine)

| Поле | Что значит |
|---|---|
| `min_edge` | Минимальный edge (|model_p − market_p|) для попадания в `valid_signal`. |
| `min_confidence` | Минимальный confidence LLM для `valid_signal`. |
| `paper_trade_edge_threshold` | Доп. порог edge для статуса `paper_trade_candidate`. |
| `paper_trade_confidence_threshold` | Доп. порог confidence для `paper_trade_candidate`. |
| `min_liquidity` | Минимальная ликвидность рынка ($) — иначе suppressed. |
| `max_news_age_minutes` | Не подтверждать сигнал новостями старше этого. |
| `min_confirming_sources` | Минимум независимых источников для подтверждения. |
| `default_position_size` | Размер сделки в долларах. |
| `min_market_probability` / `max_market_probability` | Suppressed, если рынок уже в экстремуме (0.95 → бесполезно покупать YES). |
| `max_allowed_spread` | Suppressed, если bid-ask spread выше этого. |
| `informational_edge_threshold` | Граница между `informational` и `weak_signal`. |
| `weak_confidence_threshold` | Граница `weak_signal` / `informational`. |

### `paper_trading_rules_json` (paper trading)

| Поле | Что значит |
|---|---|
| `auto_paper_trade_enabled` | Включает автоматическое открытие сделок. |
| `max_holding_minutes` | Через сколько минут принудительно закрыть по `time_limit`. |
| `take_profit_abs` | TP в абсолютных probability points (0.10 = 10 ппт движения). |
| `stop_loss_abs` | SL в абсолютных probability points. |
| `take_profit_pct` / `stop_loss_pct` | Старый формат TP/SL в процентах от entry. Игнорируется, если задан `_abs`. |
| `max_mark_jump_per_tick` | Подозрительный скачок цены за тик → trade выходит без записи PnL. |
| `eligible_signal_statuses` | Какие статусы сигналов могут породить трейд. |
| `dedup_window_hours` | Если есть открытый трейд на тот же market — новый не открывается. |

## Метрики результата

Стандартный набор, который собираем по каждой версии:

1. **Воронка сигналов**: total / suppressed_by_risk / valid_signal / paper_trade_candidate.
2. **Трейды**: opened, closed, open_now, ratio opened/candidate (насколько жёсткий дедуп).
3. **Распределение `close_reason`**: take_profit / stop_loss / time_limit / market_inactive / strategy_migration.
4. **PnL closed**: total, avg, best, worst.
5. **Winrate**: wins / (wins+losses), отдельно — % flat (PnL ≈ 0).
6. **Drift-анализ** (если есть данные ≥ 12ч): hypothetical PnL на t+1h/4h/12h/24h.
7. **Возрастные cohorts**: сравнение первой и последней половин трейдов — устойчивость edge во времени.

## Шаблон записи

```
## vN — YYYY-MM-DD

**Status:** active | retired (replaced by vN+1 on YYYY-MM-DD)
**Window:** YYYY-MM-DD HH:MM → YYYY-MM-DD HH:MM (UTC, total Xh)

### Hypothesis

(Что мы тестируем этой версией. Одно-два предложения.)

### Parameters

`parameters_json`
```json
{ ... }
```

`paper_trading_rules_json`
```json
{ ... }
```

Δ vs previous version: (одной строкой — что изменилось).

### Funnel

| Stage | Count |
|---|---|
| Total signals (v) | … |
| Suppressed | … |
| valid_signal | … |
| paper_trade_candidate | … |
| Trades opened | … |
| Trades closed | … |

### Results

(close_reason breakdown, PnL summary, winrate, drift-если-есть)

### Verdict

(Что мы из этого узнали. Какую следующую гипотезу хотим проверить.)
```

---

# Эксперименты

## v1 — 2026-05-07

**Status:** retired (replaced by v2 on 2026-05-09 10:13 UTC)
**Window:** 2026-05-07 19:13 → 2026-05-09 10:13 (UTC, ~39ч активна)

### Hypothesis

Изначальная baseline-стратегия: процентные TP/SL, никакого sanity-фильтра
на снапшоты, никаких bounds на market_probability.

### Parameters

`parameters_json`
```json
{
  "min_confidence": 0.55,
  "min_edge": 0.05,
  "min_liquidity": 500.0,
  "max_news_age_minutes": 1440,
  "min_confirming_sources": 1,
  "default_position_size": 0.1,
  "weak_confidence_threshold": 0.45,
  "informational_edge_threshold": 0.03,
  "paper_trade_confidence_threshold": 0.65,
  "paper_trade_edge_threshold": 0.06
}
```

`paper_trading_rules_json`
```json
{
  "auto_paper_trade_enabled": true,
  "max_holding_minutes": 120,
  "take_profit_pct": 0.15,
  "stop_loss_pct": 0.1,
  "eligible_signal_statuses": ["paper_trade_candidate", "valid_signal"]
}
```

Δ vs previous: первая версия, baseline.

### Funnel

(Не сохранена в момент перехода — данные потеряны при bump'е до v2.)

### Results

- Closed trades: 18
- close_reason breakdown:
  - `take_profit`: 1 (фейковый — entry 0.075 → exit 1.00 на рынке Russia × Ukraine ceasefire, +$0.0922)
  - `stop_loss`: 1
  - `strategy_migration`: 16 (принудительно закрыты при переходе на v2)
- best_pnl: +$0.0922 (фейк, причина см. ниже)
- worst_pnl: ~−$0.0003

### Verdict

Стратегия дала **фейковый «выигрыш»** из-за нескольких багов, которые
обнаружились в ходе анализа подозрительной сделки:
1. TP/SL считались в % от entry (relative) — при entry 0.075 TP=15% означал
   exit при price ≥ 0.086, что слишком близко к шуму.
2. Не было sanity-фильтра на снапшоты: снапшот с `yes_price=1.0` и
   `clob_mid=0` принимался как валидный → ложное «закрытие в потолке».
3. Не было защиты от подозрительных скачков цены за тик.
4. monitor_open_trades использовал устаревшие пороги из trade-time strategy
   вместо live active.

Результат: **+$0.092 на счёте — это артефакт сломанного pipeline,
а не edge стратегии**. Записан в `past_strategies` для аудита; вычтен из
virtual_account.balance 2026-05-11 16:22 UTC, чтобы equity отражал только
честный результат v2+.

Гипотеза для v2: переход на абсолютные TP/SL + sanity-фильтры + ограничения
на экстремальные market probabilities.

---

## v2 — 2026-05-09

**Status:** active (in-flight, замер ниже сделан 2026-05-11 ~17:00 UTC)
**Window:** 2026-05-09 10:13 → … (UTC, ~54ч на момент замера)

### Hypothesis

Все ранее найденные баги починены. Базовое окно сохраняется (120 мин),
TP/SL переведены в absolute points (10 ппт / 7 ппт), добавлены фильтры
по market_probability bounds и спреду. Гипотеза: с честными порогами
стратегия должна показать ненулевой edge.

### Parameters

`parameters_json`
```json
{
  "min_confidence": 0.55,
  "min_edge": 0.05,
  "min_liquidity": 500.0,
  "max_news_age_minutes": 1440,
  "min_confirming_sources": 1,
  "default_position_size": 0.1,
  "weak_confidence_threshold": 0.45,
  "informational_edge_threshold": 0.03,
  "paper_trade_confidence_threshold": 0.65,
  "paper_trade_edge_threshold": 0.06,
  "min_market_probability": 0.05,
  "max_market_probability": 0.95,
  "max_allowed_spread": 0.1
}
```

`paper_trading_rules_json`
```json
{
  "auto_paper_trade_enabled": true,
  "max_holding_minutes": 120,
  "take_profit_abs": 0.1,
  "stop_loss_abs": 0.07,
  "max_mark_jump_per_tick": 0.5,
  "eligible_signal_statuses": ["paper_trade_candidate", "valid_signal"]
}
```

Δ vs v1:
- `take_profit_pct → take_profit_abs=0.10` (10 ппт абсолютных)
- `stop_loss_pct → stop_loss_abs=0.07` (7 ппт абсолютных)
- `+ min/max_market_probability` (отсев экстремумов)
- `+ max_allowed_spread=0.10`
- `+ max_mark_jump_per_tick=0.5` (защита от скачков)
- Параллельно: snapshot sanity filter (yes_price <= 0.02 || >= 0.98 без CLOB midpoint → отбрасывается)

### Funnel (на момент замера 2026-05-11)

| Stage | Count |
|---|---|
| Total v2 signals | 3829 |
| Suppressed_by_risk | 1979 (≈ 67% от 2947 неотсеянных) |
| valid_signal | 113 |
| paper_trade_candidate | 855 |
| Trades opened | 79 (~8% от 968 eligible — дедуп режет жёстко) |
| Trades closed | 79 |
| Trades open now | ~15 |

### Results

**close_reason breakdown:** 79/79 = `time_limit`. **TP=0, SL=0** — пороги
ни разу не достигались.

**PnL closed:**
- total: −$0.018
- avg: −$0.00035
- best: +$0.002
- worst: −$0.006
- winrate: 31-37% (12-15 wins из 38-61 на разных замерах)
- % flat (|PnL| < $0.0005): 36%

**Drift-анализ (n=75 для +1h/+4h/+12h, n=38 для +24h):**

| Horizon | n | avg PnL | total | W/L (без flat) |
|---|---|---|---|---|
| +1h  | 75 | +$0.0016 | +$0.12 | 24/12 = 2.0 |
| +4h  | 75 | +$0.0017 | +$0.13 | 31/16 = 1.9 |
| +12h | 75 | +$0.0017 | +$0.12 | 36/18 = 2.0 |
| +24h | 38 | −$0.0005 | −$0.02 | 16/12 = 1.3 |

**Cohort-разделение** (критическое наблюдение):

| Cohort | n | +4h avg | W/L (+4h) |
|---|---|---|---|
| Старые трейды (>24ч назад) | 38 | −$0.0003 | 11/10 ≈ 1.1 (нет edge) |
| Свежие трейды (<24ч назад) | 37 | **+$0.0038** | **20/6 ≈ 3.3** (сильный edge) |

### Verdict

1. **Окно 120 мин — структурно убивает стратегию.** Реальный диапазон
   движения за 2ч: max 6 ппт, медиана 1-2 ппт. TP=10 ппт математически
   недостижим.
2. **Edge существует, но реализуется ровно за 4 часа.** На +4ч и +12ч
   среднее одинаковое (+$0.0038) — после первых 4ч цена больше не двигается
   в сторону сигнала. На +24ч edge выгорает / возвращается в шум.
3. **Edge неравномерный по времени.** На старой cohort'е (>24ч назад)
   edge отрицательный/нулевой на всех горизонтах; весь positive edge
   сосредоточен в свежих 37 трейдах. Возможные причины: market regime
   change, разогрев фильтров, шум на n=37, selection через дедуп.
4. **Воронка работает.** Suppression-фильтры режут 67% мусора;
   max_allowed_spread пока ни разу не сработал в проде, можно ужать.
5. **TP=10 ппт реалистичен на 4ч-окне** (best drift = $0.0130 = 13 ппт за 4ч).

### Next hypothesis → v3

Расширить `max_holding_minutes` со 120 до 240 (4ч), всё остальное оставить
как есть. Это double-duty эксперимент:
- (a) проверяем реализуется ли +$0.0038/trade в реальных закрытиях;
- (b) валидируем устойчивость edge на новой cohort'е.

Ожидание: если drift был не шумом, увидим winrate ≥ 60%, avg PnL ≥ +$0.003,
часть закрытий начнёт уходить в TP.

---

## v3 — _не запущен_

**Status:** planned
**Hypothesis (preview):** edge раскрывается за ~4ч → расширить окно с 120
до 240 мин. Параметры см. в выводе v2 → "Next hypothesis".

(Заполнить после запуска и накопления ≥ 30 закрытых трейдов.)

---

# Replay queries

Готовые SQL — копипастом в `docker exec polymarket_postgres psql -U postgres -d polymarket -c "…"`.
Замени `2` на номер активной версии.

### 1. Воронка сигналов

```sql
SELECT status, count(*) FROM signals WHERE strategy_config_id = 2
GROUP BY status ORDER BY count(*) DESC;
```

### 2. Распределение по `close_reason`

```sql
SELECT close_reason, count(*),
       round(avg(realized_pnl)::numeric, 5) AS avg_pnl,
       round(min(realized_pnl)::numeric, 4) AS worst,
       round(max(realized_pnl)::numeric, 4) AS best
FROM paper_trades
WHERE strategy_config_id = 2 AND status = 'closed'
GROUP BY close_reason ORDER BY count(*) DESC;
```

### 3. PnL по направлению

```sql
SELECT direction, count(*),
       round(avg(realized_pnl)::numeric, 5) AS avg_pnl,
       round(sum(realized_pnl)::numeric, 4) AS total,
       sum((realized_pnl > 0.0005)::int) AS wins,
       sum((realized_pnl < -0.0005)::int) AS losses,
       sum((realized_pnl BETWEEN -0.0005 AND 0.0005)::int) AS flat
FROM paper_trades
WHERE strategy_config_id = 2 AND status = 'closed'
GROUP BY direction;
```

### 4. Drift-анализ на 4 горизонтах (главный замер)

```sql
WITH v AS (
    SELECT id, market_id, direction, entry_price, position_size, open_time
    FROM paper_trades
    WHERE strategy_config_id = 2 AND status = 'closed'
),
horizons AS (
    SELECT * FROM (VALUES
        ('+1h',  interval '1 hour'),
        ('+4h',  interval '4 hours'),
        ('+12h', interval '12 hours'),
        ('+24h', interval '24 hours')
    ) AS h(label, dt)
),
drift AS (
    SELECT h.label,
           v.position_size * (CASE WHEN v.direction = 'YES' THEN 1 ELSE -1 END)
                            * (ms.implied_probability - v.entry_price) AS hyp_pnl
    FROM v CROSS JOIN horizons h
    CROSS JOIN LATERAL (
        SELECT implied_probability FROM market_snapshots
        WHERE market_id = v.market_id AND captured_at >= v.open_time + h.dt
        ORDER BY captured_at ASC LIMIT 1
    ) ms
)
SELECT label AS horizon, count(*) AS n,
       round(avg(hyp_pnl)::numeric, 5) AS avg_pnl,
       round(sum(hyp_pnl)::numeric, 4) AS total,
       round(min(hyp_pnl)::numeric, 4) AS worst,
       round(max(hyp_pnl)::numeric, 4) AS best,
       sum((hyp_pnl >  0.0005)::int) AS wins,
       sum((hyp_pnl < -0.0005)::int) AS losses,
       sum((hyp_pnl BETWEEN -0.0005 AND 0.0005)::int) AS flat
FROM drift GROUP BY label
ORDER BY CASE label WHEN '+1h' THEN 1 WHEN '+4h' THEN 2 WHEN '+12h' THEN 3 WHEN '+24h' THEN 4 END;
```

### 5. Cohort-разделение по возрасту трейда

Подставь интервал в `WHERE` для разделения, например `< now() - interval '24 hours'`
для "старых" и `> …` для "свежих".

### 6. Активные сигналы прямо сейчас

```sql
SELECT status, count(*) FROM signals
WHERE strategy_config_id = 2
  AND status IN ('paper_trade_candidate', 'valid_signal')
GROUP BY status;
```

### 7. Накопительный отчёт за версию

```sql
SELECT
    sc.version,
    count(pt.*) FILTER (WHERE pt.status = 'closed') AS closed,
    count(pt.*) FILTER (WHERE pt.status = 'open')   AS open_now,
    round(sum(pt.realized_pnl) FILTER (WHERE pt.status = 'closed')::numeric, 4) AS total_pnl
FROM strategy_configs sc
LEFT JOIN paper_trades pt ON pt.strategy_config_id = sc.id
GROUP BY sc.version ORDER BY sc.version;
```
