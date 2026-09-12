# Телеграм-бот реферальной программы и розыгрышей - Implementation Plan

## Task 1: Инициализация проекта и окружения
- **Status**: `pending`
- **Priority**: high
- **Depends On**: None
- **Description**:
  - Создать структуру директорий проекта: `app/`, `app/handlers/`, `app/keyboards/`, `app/database/`, `app/states/`, `app/utils/`, `app/scheduler/`
  - Создать `requirements.txt` с зависимостями: aiogram==3.31, aiosqlite, python-dotenv, apscheduler
  - Создать `.env.example` со всеми переменными: BOT_TOKEN, ADMIN_IDS, CHANNEL_ID, DB_PATH
  - Создать `app/config.py` с загрузкой переменных через dotenv
  - Создать `app/loader.py` с инициализацией бота, диспетчера, подключения к БД (WAL)
- **Acceptance Criteria Addressed**: AC-14, AC-15
- **Test Requirements**:
  - `rule` TR-1.1: `pip install -r requirements.txt` завершается без ошибок
  - `rule` TR-1.2: При импорте loader создаётся подключение к БД; `PRAGMA journal_mode` возвращает `wal`
  - `rubric` TR-1.3: Структура проекта; scale 1-5; anchors 1=корневая каша, 3=3 модуля, 5=полное разделение config/loader/db/handlers/keyboards/states/utils; threshold >= 4; evidence `ls -R app`

## Task 2: Слой базы данных — модели и репозиторий
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - `app/database/models.sql` (или миграция) со схемой таблиц:
    - `users` (id, tg_id, username, full_name, balance INT DEFAULT 0, level INT DEFAULT 0, max_level INT DEFAULT 0, subscription_end DATETIME NULL, referred_by INT NULL, created_at)
    - `referral_links` (id, owner_id, code, chat_id, invite_link, active, created_at)
    - `referrals` (id, referee_id, owner_id, level_snapshot, on_market INT DEFAULT 0, lot_id INT NULL, created_at)
    - `market_lots` (id, seller_id, count, price_per_one, total_price, level_min, level_max, status active/sold/cancelled, created_at)
    - `market_lot_items` (id, lot_id, referral_id)
    - `giveaways` (id, admin_id, title, prize, text, channel_id, channel_msg_id, ends_at, min_level INT NULL, max_level INT NULL, winner_id INT NULL, status active/ended, created_at)
    - `deposit_requests` (id, user_id, amount, screenshot/file_id, status pending/approved/rejected, handled_by, created_at)
    - `withdraw_requests` (id, user_id, amount, details, status pending/approved/rejected, handled_by, created_at)
    - `transactions` (id, user_id, amount, type ref_bonus/renewal_bonus/market_sell/market_buy/lot_cancel/referral_link_cost/restore_level/deposit/withdraw/other, related_id, created_at)
  - `app/database/repo.py` с асинхронным классом Repository: методы CRUD для всех таблиц + методы начисления/списания баланса (в одной транзакции)
  - Инициализация схемы при старте, если таблиц нет
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11, AC-13, AC-14
- **Test Requirements**:
  - `rule` TR-2.1: После запуска скрипта init все 9 таблиц существуют в БД
  - `rule` TR-2.2: `repo.add_stars(user, 50)` + `repo.subtract_stars(user, 20)` работают атомарно при балансе=0: subtract возвращает False и не изменяет баланс
  - `rule` TR-2.3: PRAGMA проверка на WAL повторяется успешно после перезапуска
  - `rubric` TR-2.4: Читаемость и полнота методов репозитория; scale 1-5; anchors 1=сырые sql в хендлерах, 3=репозиторий с 50% методов, 5=все операции в репозитории, транзакции обёрнуты; threshold >= 4; evidence просмотр repo.py

## Task 3: Клавиатуры, FSM-состояния и общие утилиты
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - `app/keyboards/user_kb.py`: Reply и Inline клавиатуры главного меню, подменю Профиль/Баланс/Рефералы/Маркет/Розыгрыши/Топ
  - `app/keyboards/admin_kb.py`: Админ-меню, кнопки для розыгрышей, управления заявками, назначения уровней
  - `app/states/form_states.py`: FSM-состояния (aiogram.fsm):
    - CreateRefLinkState
    - CreateLotState (количество, цена)
    - BuyLotState
    - CreateGiveawayState (текст, приз, время, мин/макс уровень)
    - DepositRequestState (сумма, скрин)
    - WithdrawRequestState (сумма, реквизиты)
    - AdminSetLevelState (user_id, level)
  - `app/utils/formatters.py`: форматирование чисел, дат, строк профилей
  - `app/utils/levels.py`: функция расчёта уровня по датам подписки, веса для розыгрыша
- **Acceptance Criteria Addressed**: AC-15
- **Test Requirements**:
  - `rule` TR-3.1: В каждом модуле kb можно импортировать клавиатуры без ошибок импорта
  - `rule` TR-3.2: Все FSM StateGroup классы наследуются от StatesGroup, поля корректно типизированы (State)
  - `rubric` TR-3.3: Удобство клавиатур (логичная группировка); scale 1-5; anchors 1=все Reply без подменю, 3=группировка 2 уровня, 5=чёткое меню с понятными лейблами; threshold >= 3; evidence просмотр kb

## Task 4: Базовые пользовательские хендлеры — старт, профиль, баланс, топ
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - `app/handlers/user_start.py`: `/start` с deep-link параметром (для реф-ссылок) — регистрация пользователя, сохранение реферера если есть. Команда «меню».
  - `app/handlers/user_profile.py`: Профиль с балансом, текущим уровнем, макс.уровнем, датой окончания подписки, кнопкой «Восстановить уровень за 100 звёзд» (если level<max_level).
  - `app/handlers/user_top.py`: Топ рефоводов — пагинация (по 10-20 человек), с количеством рефералов.
  - Регистрация роутеров в `app/handlers/__init__.py` и прицепка к dp в loader.
- **Acceptance Criteria Addressed**: AC-4, AC-9, AC-15
- **Test Requirements**:
  - `rule` TR-4.1: `/start?startapp=ref_abc` или `/start ref_abc` корректно записывает referred_by в users
  - «Нет» → на балансе <100 кнопка восстановления не работает, выдаёт сообщение «Недостаточно средств»
  - `rule` TR-4.3: «Топ рефоводов» показывает список сортированный DESC с позициями 1,2,3...
  - `rubric` TR-4.4: Читабельность сообщений профиля и топа; scale 1-5; threshold >= 3

## Task 5: Реферальная система — ссылки, список рефералов, бонусы
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 4
- **Description**:
  - `app/handlers/user_referrals.py`:
    - «Создать реф-ссылку (111 звёзд)» — FSM или прямая кнопка, списание, создание через `bot.create_chat_invite_link(channel_id, name=...)` с уникальным именем
    - «Мои рефералы» — список с именем/ID, уровнем каждого; кнопка «Выставить N на продажу»
  - В `user_start.py` при первом старте с `ref=XXX` найти владельца ссылки, активировать подписку на 1 месяц (условно), начислить пригласившему 40 звёзд (если подписка ещё не была активирована раньше)
  - `app/utils/subscription.py`: функция продления подписки, которая начисляет владельцу реферала 20 звёзд
- **Acceptance Criteria Addressed**: AC-1, AC-2, AC-3
- **Test Requirements**:
  - `rule` TR-5.1: Пользователь с балансом < 111 при нажатии «Создать ссылку» получает отказ
  - `rule` TR-5.2: У пользователя с 111+ звёзд после создания ссылки баланс -111 и в БД есть invite_link
  - `rule` TR-5.3: Переход по ссылке → реферер получает +40 звёзд
  - `rule` TR-5.4: Функция продления продлевает subscription_end на 30 дней и начисляет 20 звёзд владельцу реферала
  - `rubric` TR-5.5: Ясность уведомлений о бонусах; scale 1-5; threshold >= 3

## Task 6: Маркет рефералов — продажа, покупка, отмена
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - `app/handlers/user_market.py`:
    - «Выставить рефералов на продажу» (FSM: выбор рефералов из тех, что не на маркете, количество, цена за штуку) — создание лота и lot_items
    - «Маркет рефералов» — список активных лотов (продавец username, кол-во, цена/шт, мин/макс ур лота, всего), кнопка «Купить»
    - «Мои лоты» — отменить активный лот (возвращает рефералов в распоряжение продавца)
    - Обработка покупки: проверка баланса, транзакция: списание с покупателя, начисление продавцу, перевод владельца в referrals, закрытие лота (sold)
  - Ограничения: нельзя купить собственный лот; нельзя купить лот частично (сразу весь)
- **Acceptance Criteria Addressed**: AC-5, AC-6
- **Test Requirements**:
  - `rule` TR-6.1: Создание лота → в market_lots запись active, у выбранных рефералов on_market=1
  - `rule` TR-6.2: Покупка своего лота отклоняется
  - `rule` TR-6.3: При покупке чужого лота: баланс покупателя -total, продавца +total; referrals.owner всех lot_items = покупатель; лот sold
  - `rule` TR-6.4: Отмена своего лота → лот cancelled, on_market=0 у всех рефералов лота; звёзды не списываются
  - `rule` TR-6.5: Повторно выставить реферала из активного лота нельзя
  - `rubric` TR-6.6: Информационность карточки лота (уровень, цена, продавец); scale 1-5; threshold >= 4

## Task 7: Уровневая система и планировщик
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - `app/scheduler/__init__.py` + `app/scheduler/jobs.py`
  - `APScheduler (AsyncIOScheduler)`:
    - `job_check_subscriptions` (каждые 24 часа):
      - Для пользователей с истекшей subscription_end: сброс level=0 (сохраняя max_level)
      - Для пользователей с активной подпиской: пересчитать level на основе (subscription_end - start) или количества месяцев с момента первой активации; обновить level и max_level при росте
    - `job_run_giveaways` (каждые 5 минут): запускать розыгрыши, у которых ends_at <= now и status active
  - `app/handlers/admin_levels.py`: админ-команда `/setlevel <user_id> <level>` или FSM через кнопку «Назначить уровень»
- **Acceptance Criteria Addressed**: AC-7, AC-8, AC-10
- **Test Requirements**:
  - `rule` TR-7.1: Юзер с подпиской 2.5 месяца назад и активной подпиской получает уровень 2 после job_check_subscriptions
  - `rule` TR-7.2: Юзер с истёкшей подпиской (3 дня назад) и level=5 получает level=0, max_level=5
  - `rule` TR-7.3: Админ-команда /setlevel меняет уровень; не-админ — отказ
  - `rule` TR-7.4: Новый max_level при ручном повышении — сохраняется (для будущего восстановления)
  - `rubric` TR-7.5: Точность расчёта уровня по месяцам; scale 1-5; threshold >= 4

## Task 8: Розыгрыши — создание админом, автоматическое завершение
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 7
- **Description**:
  - `app/handlers/admin_giveaways.py`: FSM создания розыгрыша (админ-меню):
    1. Текст объявления (или описание)
    2. Приз
    3. Дата/время завершения (парсинг `%d.%m.%Y %H:%M`)
    4. (опционально) мин. уровень / макс. уровень для участия
  - По завершении FSM:
    - Создать запись giveaways
    - Отправить пост в CHANNEL_ID через `bot.send_message` с форматированным текстом розыгрыша (приз, время окончания, условие, фильтр по уровням)
    - Сохранить `channel_msg_id`
  - `app/utils/giveaways.py`:
    - `select_weighted_winner(giveaway)`:
      1. Выбрать всех пользователей с активной подпиской (subscription_end > now)
      2. Отфильтровать по min_level/max_level розыгрыша
      3. Веса = уровень участника (минимальный вес=1, если уровень=0)
      4. Взвешенный случайный выбор `random.choices(users, weights=..., k=1)`
    - `run_giveaway(giveaway)`:
      - Выбрать победителя
      - Обновить giveaways (winner_id, status=ended)
      - Отправить сообщение-поздравление в канал (ответом/редактированием)
      - Отправить победителю ЛС уведомление
  - В scheduler job `job_run_giveaways` вызывать `run_giveaway`
- **Acceptance Criteria Addressed**: AC-11, AC-12
- **Test Requirements**:
  - `rule` TR-8.1: FSM создания розыгрыша админом создаёт запись и постит сообщение в канал (mock), возвращает message_id
  - `rule` TR-8.2: Не-админ не может открыть FSM розыгрыша
  - `rule` TR-8.3: 10000 запусков `select_weighted_winner` с L2 против L3 (L1 отфильтрован) — доля побед L2 ≈ 2/5 ± 2%, L3 ≈ 3/5 ± 2%; L1 никогда не побеждает
  - `rule` TR-8.4: По наступлению ends_at планировщик меняет статус на ended и публикует победителя (проверка по истечении времени)
  - `rubric` TR-8.5: Оформление поста розыгрыша; scale 1-5; threshold >= 3

## Task 9: Финансовый модуль — заявки на пополнение и вывод + админ-обработка
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - `app/handlers/user_finance.py`:
    - «Пополнить баланс» (FSM DepositRequestState): ввести сумму → опционально прикрепить скрин → заявка создаётся.
    - «Вывести звёзды» (FSM WithdrawRequestState): сумма, реквизиты → проверка баланса ≥ суммы → freeze суммы (вычитаем из доступного, но помещаем в pending) → заявка создаётся, уведомление идёт всем ADMIN_IDS.
  - `app/handlers/admin_requests.py`:
    - Админ получает уведомление о заявке с Inline-кнопками: «Подтвердить», «Отклонить»
    - Подтверждение пополнения: +amount на баланс, статус approved, транзакция deposit
    - Подтверждение вывода: замороженную сумму списываем, статус approved, транзакция withdraw
    - Отклонение вывода: возвращаем замороженную сумму на баланс, статус rejected
  - История транзакций (список последних 20) в подменю баланса
- **Acceptance Criteria Addressed**: AC-13
- **Test Requirements**:
  - `rule` TR-9.1: Создание заявки на вывод суммой > баланс — отказ
  - `rule` TR-9.2: При создании заявки на вывод админ получает уведомление; баланс пользователя уменьшается на сумму (заморозка)
  - `rule` TR-9.3: Отклонение вывода → замороженная сумма возвращается на баланс
  - `rule` TR-9.4: Подтверждение пополнения → баланс +amount
  - `rubric` TR-9.5: Понятная админ-панель заявок; scale 1-5; threshold >= 4

## Task 10: Сборка, точка входа, регистрация роутеров, запуск
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Tasks 4,5,6,8,9
- **Description**:
  - `main.py` в корне: асинхронная `main()` → загрузка config, создание бота/dp/БД из loader, регистрация роутеров, мидлвари (передача repo в данные dp["repo"]), запуск scheduler, start_polling.
  - `app/middlewares/db.py` (опционально): middleware, передающий сессию БД в хендлеры (или repo уже созданный singleton)
  - Проверка на права админа через фильтр `IsAdmin` (фабрика фильтров aiogram 3.x)
  - Логгирование ошибок и unhandled updates
- **Acceptance Criteria Addressed**: AC-15, AC-16
- **Test Requirements**:
  - `rule` TR-10.1: `python main.py` запускается без критических ошибок импорта (останавливаем сразу после успешного старта polling)
  - `rule` TR-10.2: Не-админ при вызове админ-команд вида /admin /setlevel /giveaway получает «Нет доступа» и не крашит бота
  - `rubric` TR-10.3: Чистота точки входа и разделение ответственности; scale 1-5; threshold >= 4

## Task 11: Smoke-тест основных пользовательских сценариев
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 10
- **Description**:
  - Сценарий 1: Регистрация → создание реф-ссылки → переход вторым пользователем по ссылке → проверка бонусов 40 и реф-связи.
  - Сценарий 2: Продавец выставляет 2 реферала на маркет → покупатель покупает → проверка перехода права.
  - Сценарий 3: Админ создаёт розыгрыш, 3 участника с L0/L2/L3, фильтр L>=2 → запуск → подтверждение взвешенного выбора.
  - Сценарий 4: Просрочка подписки → сброс уровня → восстановление за 100 звёзд.
- **Acceptance Criteria Addressed**: AC-1..AC-13
- **Test Requirements**:
  - `rubric` TR-11.1: Прохождение всех 4 сценариев без необработанных исключений; scale 1-5; anchors 1=краш на каждом шаге, 3=частичные проблемы, 5=всё ок; threshold >= 4
  - `rule` TR-11.2: Во всех сценариях балансы сходятся (сумма всех звёзд в системе — константа, кроме операций пополнения/вывода)
