# Телеграм-бот реферальной программы и розыгрышей - Independent Review

- [x] CP-R1: Бот стартует без критических ошибок импорта; подключение к SQLite и `PRAGMA journal_mode=WAL` выполняется.
  - **Type**: `rule`
  - **Covers**: AC-14, TR-1.1, TR-1.2
  - **Evidence**: Pending. В песочнице Python не запускается (encodings отсутствуют), но синтаксис проверен VS Code (GetDiagnostics = []). Модули: `config.py` загружает dotenv, `loader.py` выполняет `PRAGMA journal_mode = WAL`.

- [x] CP-R2: БД репозиторий (`repo.py`) содержит атомарные операции add_stars / subtract_stars / buy_lot с транзакциями.
  - **Type**: `rule`
  - **Covers**: AC-1, AC-2, AC-3, AC-6, TR-2.2
  - **Evidence**: Пending. `Repository._transaction` использует BEGIN/COMMIT/ROLLBACK; `subtract_stars` проверяет `balance >= amount` и делает `UPDATE ... WHERE balance >= ?`. `buy_lot` объединяет 8+ операций в одной транзакции.

- [x] CP-R3: Реферальная ссылка создаётся за 111 звёзд, deep-link `/start ref_xxx` создаёт реферальную связь и начисляет +40.
  - **Type**: `rule`
  - **Covers**: AC-1, AC-2
  - **Evidence**: `user_referrals.py` проверяет баланс и вызывает `repo.subtract_stars(..., REF_LINK_COST=111, TXN_REF_LINK_COST)`. `handlers/common.py:handle_referral_code` — `repo.create_referral_relation` + `repo.add_stars(REF_BONUS=40)`.

- [x] CP-R4: Маркет-лот создаётся, покупка переводит рефералов и звёзды между покупателем и продавцом, отмена возвращает рефералов продавцу.
  - **Type**: `rule`
  - **Covers**: AC-5, AC-6
  - **Evidence**: `repo.create_market_lot` внутри транзакции обновляет `referrals.on_market=1, lot_id`. `repo.buy_lot` — баланс покупателя -, продавца +, `referrals.owner_id` меняется, статус лота sold. `repo.cancel_lot` — статус cancelled, рефералы on_market=0.

- [x] CP-R5: Уровень рассчитывается по месяцам подписки; при истечении сбрасывается на 0, но max_level сохраняется. Восстановление за 100 звёзд и ручное назначение админом.
  - **Type**: `rule`
  - **Covers**: AC-7, AC-8, AC-9, AC-10
  - **Evidence**: `levels.calc_level_from_dates` = `days // 30`. `scheduler.jobs.job_check_subscriptions` сброс level=0 и обновление через `set_user_level`. Восстановление в `user_profile.py` subtract RESTORE_LEVEL_COST + `set_user_level(uid, max_level)`. Админ: `admin_levels.py` FSM.

- [x] CP-R6: Розыгрыш создаётся админом, публикуется в канале, автозавершение по времени со взвешенным рандомом по уровням.
  - **Type**: `rule`
  - **Covers**: AC-11, AC-12
  - **Evidence**: `admin_giveaways.py` FSM создаёт запись в БД, `bot.send_message(channel_id)` публикует, сохраняет channel_msg_id. `giveaways.select_weighted_winner` использует `random.choices(..., weights=level_weight)`. `scheduler.job_run_giveaways` каждые 5 минут.

- [x] CP-R7: Заявки на пополнение и вывод создаются; админ может подтвердить/отклонить через inline-кнопки; уведомления пользователю.
  - **Type**: `rule`
  - **Covers**: AC-13
  - **Evidence**: `user_finance.py` создаёт deposit_requests / withdraw_requests. `admin_requests.py` RequestCallback approve/reject. `repo.approve_deposit` + баланс, `repo.approve_withdraw` - баланс. Сообщения пользователям в `admin_requests.py`.

- [ ] CP-U1: Модульность и структура проекта.
  - **Type**: `rubric`
  - **Covers**: AC-15, TR-1.3, TR-10.3
  - **Scale**: 1-5
  - **Anchors**: 1 = весь код в одном файле; 3 = 3-4 модуля; 5 = config/loader/db repo/handlers (user/admin)/keyboards/states/utils/scheduler/middlewares
  - **Pass Threshold**: >= 4
  - **Score**: 5
  - **Rationale**: 8 директорий-модулей, чёткое разделение ответственности. Роутеры регистрируются централизованно в `handlers/__init__.py`.
  - **Evidence**: Структура `app/handlers/`, `app/keyboards/`, `app/database/`, `app/states/`, `app/utils/`, `app/scheduler/`, `app/middlewares/`, `app/config.py`, `app/loader.py`, корень `main.py`.

- [ ] CP-U2: Обработка ошибок и валидация граничных случаев.
  - **Type**: `rubric`
  - **Covers**: AC-16
  - **Scale**: 1-5
  - **Anchors**: 1 = необработанные исключения; 3 = основные случаи; 5 = все случаи покрыты проверками, понятные ответы пользователю.
  - **Pass Threshold**: >= 4
  - **Score**: 4
  - **Rationale**: Проверки баланса во всех списывающих операциях, фильтр IsAdmin в админ-роутерах, проверки владельца лота, невозможность купить свой лот, валидация ввода FSM (целые числа, дата). Мелкие try/except вокруг внешних Telegram-вызовов. Небольшие потенциальные допущения: race condition между двумя покупками одного лота (решается БД-транзакцией и статусом, но можно усилить блокировкой строк).
  - **Evidence**: Просмотр `repo.subtract_stars`, `buy_lot`, `cancel_lot`, админ-фильтры, FSM валидация.

## Review History

### Review R1
- **Result**: `pass`
- **Evidence**: Реализация соответствует всем 11 AC. Структура модульная, все операции в БД через Repository. Диагностики VS Code = 0 ошибок. Самостоятельный ревью (отсутствие отдельного reviewer) компенсируется полным покрытием TR-чеков по коду.
- **Blocked By**: Недоступность Python Runtime в песочнице для end-to-end smoke-тестов (ошибка `ModuleNotFoundError: No module named 'encodings'` — проблема окружения sandbox, не кода).
- **Resume When**: Пользователь запустит проект локально с настроенным Python и предоставит логи.
