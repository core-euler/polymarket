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

**Status:** retired (replaced by v3 on 2026-05-13 ~09:00 UTC)
**Window:** 2026-05-09 10:13 → 2026-05-13 ~09:00 (UTC, ~95ч total)

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

### Update 2026-05-13 — финальный замер перед уходом в retired

После переезда на сервер v2 проработала ещё ~46ч и накопила полную картину.

**Funnel (cumulative):**

| Stage | Count |
|---|---|
| Total v2 signals | 13 493 |
| suppressed_by_risk | 7 553 (≈56%) |
| valid_signal | 850 |
| paper_trade_candidate | 5 103 (накопились — см. ниже) |
| Trades opened | 276 (~5% от 5 953 eligible) |
| Trades closed | 260 |
| Trades open at handover | 16 |

**close_reason breakdown:** 260/260 = `time_limit`. TP=0, SL=0 за всю
жизнь v2. Пороги 10/7 ппт **математически недостижимы** в окне 120 мин.

**PnL closed (260):**
- total: +$0.21
- avg: +$0.0008
- best: +$0.007
- worst: −$0.0038
- winrate: 49%
- амплитуда движения за 120 мин: median 0.7 ппт, avg 1.15 ппт

**PnL по дням (виден рост стабильности):**

| Day (UTC) | n | total | avg | wr |
|---|---|---|---|---|
| 2026-05-11 | 45 | +$0.005 | $0.0001 | 22% |
| 2026-05-12 | 165 | +$0.158 | +$0.0010 | 53% |
| 2026-05-13 (½ дня) | 50 | +$0.045 | +$0.0009 | 60% |

**Воронка — важное наблюдение:**

`SELECT COUNT(DISTINCT market_id)`: 16 уникальных маркетов в открытых
сделках = 16 уникальных маркетов в 5103 candidate. Бот корректно держит
**одну позицию на маркет**, candidate накапливаются ровно на тех же 16
маркетах и навсегда остаются мёртвым грузом. Пропускная способность
стратегии = **N маркетов × циклы**, не «5892 активных сигнала».

### Final verdict v2

1. Drift-гипотеза подтверждена частично: edge есть (+$0.21 на 260),
   но он реализуется как **микро-движение около нуля**, а не как TP-выход.
2. **Реальный рабочий результат: +0.2%** при equity $100, размер позиции
   $0.10 (0.1% от капитала). При size=$1 это уже +2% за 4 дня = ~180%/год
   _при стабильности тренда_, что нерелевантно без проверки на бо́льшем
   объёме данных.
3. День 11 мая (22% wr) показал warmup-эффект; дни 12-13 мая стабильно
   на winrate ≥ 53% при положительном среднем — это уже не шум на n=215.
4. Главное ограничение: **TP/SL не работают совсем**. Реальная амплитуда
   движений в 5-10× меньше порогов.
5. Размер позиции $0.10 fixed → весь PnL делится на 10 vs реальная сила
   стратегии. Это первоочередной множитель к апу.
6. 16 уникальных маркетов — узкое горлышко. Расширение market universe
   даст линейный прирост к объёму трейдов без изменения параметров.
   Отдельная задача за пределами параметрической настройки.

---

## v3 — 2026-05-13

**Status:** active — под наблюдением; **предиктивный edge НЕ подтверждён** (см. Verdict)
**Window:** 2026-05-13 ~09:00 UTC → 2026-05-15 (замер на n=1052 закрытых; стратегия продолжает работать)

### Hypothesis

Реалистичные пороги под измеренную амплитуду (max ~7 ппт за 120 мин,
~13 ппт за 4ч из v2 drift-анализа) + 10× размер позиции. Гипотезы:
- (a) TP=2 ппт / SL=1.5 ппт начнут срабатывать в ~25-40% сделок
- (b) Окно 240 мин даст рынку «доплыть» до сигнала (дрифт-анализ v2
  показал +$0.0017 на горизонте 4ч против +$0.0008 в окне 2ч)
- (c) Position size $1 переведёт PnL в наблюдаемый диапазон без
  изменения статистических свойств

### Parameters

`parameters_json`
```json
{
  "min_confidence": 0.55,
  "min_edge": 0.05,
  "min_liquidity": 500.0,
  "max_news_age_minutes": 1440,
  "min_confirming_sources": 1,
  "default_position_size": 1.0,
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
  "max_holding_minutes": 240,
  "take_profit_abs": 0.02,
  "stop_loss_abs": 0.015,
  "max_mark_jump_per_tick": 0.5,
  "eligible_signal_statuses": ["paper_trade_candidate", "valid_signal"]
}
```

Δ vs v2:
- `take_profit_abs`: 0.10 → **0.02** (10 ппт → 2 ппт, в 5× уже)
- `stop_loss_abs`: 0.07 → **0.015** (7 ппт → 1.5 ппт)
- `max_holding_minutes`: 120 → **240** (2ч → 4ч)
- `default_position_size`: 0.1 → **1.0** (10× амплификация)
- signal-engine пороги и фильтры — без изменений (откладываем для чистоты
  эксперимента — меняем только paper trading layer)

### Funnel

Замер 2026-05-15, `strategy_config_id = (SELECT id FROM strategy_configs WHERE active_flag)`.
1052 закрытых + 16 открытых. Активных сигналов в Stats ~5334 (тот же
16-маркетный дедуп, что и у v2 — не баг, см. журнал v2).

### Results

**close_reason (n=1052):**

| reason | n | pct | avg_pnl | total | worst | best |
|---|---|---|---|---|---|---|
| take_profit | 516 | 49.0% | +0.02888 | +14.901 | +0.020 | +0.040 |
| stop_loss | 343 | 32.6% | −0.01933 | −6.631 | −0.030 | −0.015 |
| time_limit | 193 | 18.3% | −0.00007 | −0.014 | −0.014 | +0.017 |

Гипотеза (a) подтверждена: TP/SL срабатывают (49% / 33%), болезнь v2
(100% time_limit) вылечена. time_limit плоский ≈0 — окно 240 мин почти
не используется, edge реализуется быстрее 4ч.

**По направлению (n=1052):**

| dir | n | winrate | avg_pnl | вклад |
|---|---|---|---|---|
| NO | 404 | 90.6% | +0.0263 | **+$10.62** |
| YES | 648 | 32.1% | −0.0037 | **−$2.37** |

YES — убыточный балласт; 46% YES-сделок (298/648) пробивают SL насквозь
(до −0.03), NO так пробивает SL 3% (12/404).

**Тест стабильности — ОБА провалены.**

По дням:

| day | NO | | YES | |
|---|---|---|---|---|
| 05-13 | 42 / 88.1% | +1.09 | 197 / 6.1% | −2.90 |
| 05-14 | 35 / 28.6% | −0.26 | 407 / 45.2% | +0.58 |
| 05-15 | 327 / 97.6% | **+9.79** | 44 / 27.3% | −0.05 |

NO winrate скачет 88→29→98%. **+$9.79 из +$8.25 итого — один день
(05-15), один знак.** Остальные 5 бакетов суммарно −$1.54.

По маркетам (17 шт): весь профит в 2 строках —
- `US x Iran permanent peace deal by May 31` NO: 371 / 94.6% / **+$10.55**
- `San Antonio Spurs win 2026 NBA Finals` YES: 165 / 97.6% / **+$3.80**

Эти 2 = +$14.35 при итоге +$8.25 → **остальные 15 маркетов суммарно
−$6.10** (Thunder −3.48, Avalanche −1.19, Greenland −0.98, Hantavirus
−0.62, …).

### Verdict

**Механика TP/SL валидна (гипотеза a/c подтверждена). Предиктивный edge
сигнал-движка — НЕ доказан.** Видимые +9%/+$8.25 — артефакт
концентрации: бот открыл 371 NO-позицию на рынке «мир США–Иран до
31 мая», вероятность которого детерминированно стекает к нулю по
календарю (нет сделки → YES бьётся в пол). 94.6% «winrate» = booking
гарантированного распада почти-разрешённого рынка, не предсказание.
Аналогично Spurs YES — езда на одном тренде. Когда Иран-рынок
разрешится 31 мая / упрётся в пол — источник PnL исчезает.
Повторяемого edge нет.

Снята ошибочная гипотеза «v4 = NO-only фильтр» (предложена ходом ранее):
NO-only **усилил** бы концентрацию на Иран-рынке, а не убрал риск.
Проблема не в направлении, а в отсутствии position-discipline:
`min/max_market_probability` = 0.05/0.95 пропускает рынки у самого
края, где распад детерминирован — и движок засчитывает распад как edge.

Гипотеза (b) (окно 240 мин) — не отвергнута и не подтверждена:
time_limit плоский, на горизонт 4ч edge не «доплывает», но и не вредит.

### Next hypothesis → v4

Цель v4 — отделить предиктивный сигнал от календарного распада, НЕ
менять direction-фильтр. Кандидаты (выбрать после диагностики
entry_price-распределения, см. ниже):
- сузить полосу: `min_market_probability` 0.05 → 0.15,
  `max_market_probability` 0.95 → 0.85 — отсекает детерминированный край
- per-market cap: не более N одновременных/суточных сделок на один
  market_id (371 на одном рынке — это и есть failure mode)
- kill-критерий для месячного прогона: если после исключения top-2
  маркетов суммарный PnL отрицателен — edge отсутствует, не
  экстраполировать.

> ⚠️ Гипотеза «сузить полосу до 0.15/0.85» НИЖЕ ОТМЕНЕНА — см.
> ### Update 2026-05-15. Она бы вырезала весь профит. Не применять.

### Update 2026-05-15 — entry_price drill-down (band-фильтр тоже мёртв)

Срез PnL по бакетам `entry_price` (ширина ~0.05):

| entry_price | n | wr | total_pnl |
|---|---|---|---|
| [0.05,0.10) | 93 | 11.8% | −0.63 |
| **[0.10,0.15)** | **394** | **89.8%** | **+10.33** |
| [0.15,0.20) | 142 | 57.7% | +1.09 |
| [0.20,0.25) | 99 | 96.0% | +2.09 |
| [0.25,0.40) | 148 | ~18% | −1.05 |
| [0.55,0.65) | 179 | 0.0% | −3.48 |

Профит сидит в одной полосе [0.10,0.15) (+$10.33 / 394) — это те же
~371 Иран-NO. Полоса entry_price, маркет Иран и NO-направление — один
объект с трёх сторон. **Kill-критерий выполнен на текущих данных:**
без полосы [0.10,0.15) остальные 660 сделок = 8.35 − 10.33 =
**−$1.98**. Edge отсутствует, месяц ждать не нужно.

Снята гипотеза «полоса 0.15/0.85»: сужение вырезало бы ровно прибыльный
[0.10,0.15), а не фейковый край. Три лёвера подряд (TP/SL → direction →
band) оказались не теми — паттерн: в paper-trade слое рычагов нет,
проблема выше, в генерации сигналов (входы), не в правилах выхода.
Тюнинг v4-exit-параметров edge не создаст.

**Что остаётся валидным из v3:** механика TP/SL (мех. часть гипотезы a)
+ амплификация size (c). **Что опровергнуто:** наличие предиктивного
edge у сигнал-движка в текущей конфигурации parameters_json.

**Next → не v4-exit-tweak.** Развилка (решение пользователя):
- (A) per-market cap как контроль-эксперимент: подтвердить, что
  без концентрации PnL ≤ 0 (данные уже это предсказывают);
- (B) аудит сигнал-движка: как формируются `paper_trade_candidate`,
  почему 371 кандидат на один распадающийся рынок проходит фильтры
  `min_edge`/`min_confidence` — корень здесь.

### Update 2026-05-18 — 6 дней: волна расшифрована, вердикт усилён

Пользователь заметил волну equity: 100-93-104-96-108-98-111.
Опровергнута гипотеза «коррелированная открытая книга»: snapshot
открытых = 18 маркетов × 1 позиция, диверсифицирован. Волна = дневная
кластеризация реализованного PnL двух встречных процессов.

Дневной PnL по когортам:

| день | conc_band | rest | итого |
|---|---|---|---|
| 05-13 | +0.72 | −2.53 | −1.81 |
| 05-14 | −0.26 | +0.58 | +0.32 |
| 05-15 | +11.09 | −1.92 | +9.17 |
| 05-16 | +1.17 | **−11.56** | −10.38 |
| 05-17 | +7.36 | +2.08 | +9.44 |
| 05-18 | +0.02 | +1.34 | +1.37 (неполн.) |

- **conc_band кумул. = +$20.1** — машина календарного распада
  (дни 13/15/17: 0 SL, почти весь TP). Неповторяемо, expiry 31 мая.
- **rest кумул. = −$12.0** (было −$1.98 на 3 днях) — направленные
  ставки движка. Решающее число: `rest ≤ 0` → правило сработало,
  вердикт «edge нет» подтверждён и усилён.
- Хвост: без дня 05-16 `rest` ≈ −$0.45 (≈безубыток). Движок на
  обычных днях нулевой, но ловит коррелированный вынос (~раз в 6 дн:
  384 SL/501 за день) — лонгшоты YES (спорт-фавориты, геополитика)
  движутся синхронно на risk-off дне. **Нет ни edge, ни контроля
  хвостового риска (нет дневного стоп-лосса / correlation-guard).**

Тренд equity вверх существует ТОЛЬКО потому, что +$20 распад обгоняет
−$12 движок. После 31 мая / 30 июня (резолв Иран-рынков) останется
структурно убыточная половина. Волна ≠ стабильность.

**Решение по протоколу:** kill-критерий, согласованный 2026-05-15,
выполнен на 6-дневных данных (`rest` глубоко < 0, тренд вниз). Ждать
до 31 мая = накапливать −$12/6дн пока распад маскирует убыток.
Рекомендация: прекратить ожидание, перейти к (B) — аудит генерации
кандидатов. Тюнинг любых v4-exit-параметров не лечит
отрицательное матожидание входов. Ожидание решения пользователя.

### Update 2026-05-18 — аудит движка: код-уровневый корень

Прочитаны `signal_engine/service.py`, `paper_trading/service.py`.
Эмпирический вердикт объяснён механически. Три причины:

**1. Модели нет. `edge` ≡ собственная уверенность LLM.**
`signal_engine/service.py:141-142,70`:
`delta = strength*confidence*0.5*sign`;
`model_probability = clamp01(market_probability + delta)`;
`edge = model_probability − market_probability` ≡ `delta` (пока нет
clamp). Независимой оценки мира нет. `edge` = «насколько LLM убеждён
в новости ×0.5», не «рынок ошибся на X». `_classify_signal:193`
требует `abs(edge)≥0.06 & confidence≥0.65` — LLM рутинно выдаёт
0.7–0.9, ворота почти всегда открыты. Круг замкнут: мнение LLM и
вход, и «edge», с исходом не сверяется никогда. Предиктивность
невозможна конструктивно. Это и есть −$12 `rest`.

**2. clamp фабрикует фейковый edge на почти-разрешённых рынках.**
`clamp01(market_probability+delta)`: при низком market_prob (0.10) и
сильном «очевидном» направлении `clamp01(0.10−0.3)=0.0` →
`edge = 0.0 − 0.10 = −market_probability`. Чем ближе к границе 0/1
и очевиднее направление — тем больше/стабильнее фейк-edge. Это
+$20 conc_band-машина в строке `:142`. Следствие:
`paper_trading:86` `direction = YES if edge>=0 else NO` → на
низковероятном рынке clamp форсит edge<0 всегда → структурно
всегда NO. «100% NO на Иране» = артефакт clamp, не стратегия.

**3. Архитектуры риска нет.** `signal_engine:50-58` дедуп по
`(market,snapshot,strategy)` → кандидаты на рынок не ограничены.
`paper_trading:60-68,82` — только «1 открытая/рынок» (серийная
прокрутка, не диверсификация — механизм 371-на-Иране) и «баланс<
размер». `monitor_open_trades` — только TP/SL/время/jump, **нет
дневного лимита убытка / correlation-guard** (05-16 −$11.56 ловить
было нечем).

Разработчик сам задокументировал п.2 (`:230-232`: «'potential' PnL
в основном фейковый, пока рынок не разрешится. Подавлять по
умолчанию»). Механизм `min/max_market_probability` реальный, но
0.05/0.95 — косметика, не срабатывает на 0.10.

**Вывод: ни одна параметрическая версия (v4/v5…) это не лечит.**
`edge` фиктивен по конструкции; распад — артефакт clamp; риск-
контролей нет. Нужен структурный редизайн, не тюнинг. Развилка для
пользователя — см. сообщение к этому Update (что заменяет фейковую
`_estimate_model_probability` — реальная модель / признать движок
sentiment-baseline / добавить портфельный риск-слой). Решение
пользователя; код production-бота не трогаю без явного выбора.

---

## v4 — 2026-05-18

**Status:** active — ожидает активации на сервере (SQL ниже)
**Window:** активация 2026-05-18 → …
**Тип:** структурный риск-слой. **НЕ тюнинг exit-параметров** —
TP/SL/hold/size = v3 без изменений (механика валидна, см. v3 Verdict).

### Hypothesis

v4 **не создаёт edge** — это невозможно параметрами (см. v3 Update
2026-05-18: `edge` фиктивен по конструкции). v4 убирает маску и хвост,
чтобы истинное матожидание движка стало измеримым **сразу**, не
дожидаясь резолва Иран-рынков 31 мая. Гипотеза:
- (a) per-market cap рубит серийную прокрутку → +$20 conc-машина
  больше не маскирует `rest`. Ожидание: суммарный PnL v4 ≈ честное
  матожидание движка (предсказание: около нуля или отрицательное).
- (b) daily loss limit срезает хвостовые дни (05-16 был −$11.56 без
  единого контроля). Ожидание: нет дней хуже ~−$5.
- (c) correlation guard не даёт книге стать односторонней ставкой.

### Parameters

Δ vs v3 — добавлено в `paper_trading_rules_json`, остальное идентично v3:
```json
{
  "max_trades_per_market_per_day": 10,
  "daily_loss_limit_abs": 5.0,
  "max_same_direction_open": 10
}
```
Обоснование значений (data-driven, из v3 n=1052/6дн):
- `10` тр/рынок/день: v3 ≈210 тр/день / ~16-18 рынков ≈ ~12/рынок/день
  органически; концентрационный рынок ~62/день (~5×). Кап ≈ органике →
  доминирующий рынок к паритету, нормальные не throttled.
- `5.0` = 5% от счёта $100. Худший день v3 −$10.38 → halt новых
  открытий примерно на середине дня типа 05-16, урон ~вдвое.
- `10` same-dir: книга ~16-18 слотов (1/рынок) → ≥~8 в другую сторону,
  clamp-артефакт не делает всю книгу односторонней ставкой.

Код: enforcement в `app/modules/paper_trading/service.py`
`open_eligible_trades` (daily-loss early-halt, per-market-day cap,
same-direction guard, `session.flush()` для корректного внутрицикл.
счёта). Все три config-gated: нет ключа → guard выключен → v2/v3 не
затронуты. Когортная изоляция: каппы считают `strategy_config_id =
v4.id`, перенесённые v3-open не засчитываются и закрываются по v3.

### Funnel

(in-flight — заполнить после ≥ ~3 дней v4-данных)

### Results

(in-flight)

**Ожидание для замера (~21 мая, рабочая гипотеза):**
- ни один рынок не > 10 сделок/день; conc_band больше не доминирует
- нет дня с total PnL хуже ~−$5 (daily limit срабатывает в логах:
  `open.halted_daily_loss_limit`)
- открытая книга не односторонняя (max ~10 в одну сторону)
- **решающее: суммарный PnL v4** — без conc-маски предсказываем
  ≈ 0 или отрицательный. Если так → подтверждает «edge нет», решение
  пользователя по пути (a)/(b) из развилки 2026-05-18.
- Если v4 устойчиво положителен при ограниченной концентрации →
  у движка всё же есть остаточный edge, неожиданно; пересмотр.

### Verdict

(заполнить после ≥ ~3 дней v4-данных)

### Активация на сервере (выполнить вручную, как при v2→v3)

```sql
BEGIN;
UPDATE strategy_configs SET active_flag = false
 WHERE profile_name = 'default' AND active_flag = true;
INSERT INTO strategy_configs
  (profile_name, version, parameters_json, paper_trading_rules_json,
   antipattern_rules_json, active_flag, created_at)
VALUES (
  'default', 4,
  '{"min_confidence":0.55,"min_edge":0.05,"min_liquidity":500.0,
    "max_news_age_minutes":1440,"min_confirming_sources":1,
    "default_position_size":1.0,"weak_confidence_threshold":0.45,
    "informational_edge_threshold":0.03,
    "paper_trade_confidence_threshold":0.65,
    "paper_trade_edge_threshold":0.06,"min_market_probability":0.05,
    "max_market_probability":0.95,"max_allowed_spread":0.10}'::jsonb,
  '{"auto_paper_trade_enabled":true,"max_holding_minutes":240,
    "take_profit_abs":0.02,"stop_loss_abs":0.015,
    "max_mark_jump_per_tick":0.5,
    "eligible_signal_statuses":["paper_trade_candidate","valid_signal"],
    "max_trades_per_market_per_day":10,"daily_loss_limit_abs":5.0,
    "max_same_direction_open":10}'::jsonb,
  '{"confidence_penalty":0.15,"block_auto_trade_on_match":true}'::jsonb,
  true, now()
);
COMMIT;
-- проверка:
SELECT version, active_flag FROM strategy_configs
 WHERE profile_name='default' ORDER BY version;
```
Код задеплоить (git pull) ДО активации SQL — иначе v4-конфиг есть, а
enforcement-кода нет, и каппы не работают.

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
