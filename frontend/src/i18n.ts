// src/i18n.ts
import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

const resources = {
  en: {
    translation: {
      // Navigation
      home: 'Game',
      profile: 'Profile',
      leaderboard: 'Leaderboard',
      store: 'Store',
      
      // Common
      loading: 'Loading...',
      balance: 'Balance',
      
      // Game (GameWebSocket.tsx)
      'game.connectingToServer': 'Connecting to server...',
      'game.connectionFailed': 'Connection failed',
      'game.tryAgain': '🔄 Try again',
      'game.canOnlyJoinWaiting': 'You can only join while waiting for a new round.',
      'game.userIdError': 'Error: Could not get user ID',
      'game.insufficientFunds': 'Insufficient funds! Need at least {{amount}} stars to bet.',
      'game.minBet': 'Minimum bet is 10 stars!',
      'game.joinError': 'Error joining game: ',
      'game.networkError': 'Network error when joining game.',
      'game.cashoutError': 'Cashout error: ',
      'game.wsConnected': '🟢 WebSocket connected',
      'game.wsConnecting': '🟡 Connecting...',
      'game.wsReconnecting': '🟡 Reconnecting...',
      'game.wsNoConnection': '🔴 No connection',
      'game.roundAlreadyStarted': '🔒 Round already started',
      'game.waitingForStart': '⏳ Waiting for round start{{countdown}}',
      'game.insufficientStars': '💸 Insufficient stars',
      'game.joinRound': '🎮 Join round',
      'game.joining': '⏳ Joining...',
      'game.startIn': 'Start in {{seconds}} sec.',
      'game.cashoutStars': '💰 Cash out stars',
      'game.cashing': '⏳ Cashing...',  
      'game.waitingForEnd': '⏳ Waiting for round end...',
      'game.bet': 'Bet:',
      'game.crash': '💥 CRASH!',
      'game.cashedOut': '✅ +{{amount}}⭐ x{{multiplier}}',
      
      // Profile (Profile.tsx)
      'profile.loadingProfile': 'Loading profile...',
      'profile.statistics': '📊 Statistics',
      'profile.gamesPlayed': 'Games won',
      'profile.totalWin': 'Total winnings',
      'profile.bestMultiplier': 'Best multiplier',
      'profile.avgMultiplier': 'Average multiplier',
      'profile.gifts': '🎁 Gifts',
      'profile.testing': '🧪 Testing (development only)',
      'profile.refundStars': 'Refund stars for testing:',
      'profile.refunding': '⏳ Refunding...',
      'profile.refund': '🔄 Refund {{amount}} ⭐',
      'profile.testingNote': '⚠️ This function is for testing only. Will be removed in production.',
      
      // Store (Store.tsx)
      'store.loadingGifts': 'Loading gifts...',
      'store.regular': '🎁 Regular',
      'store.unique': '⭐ Unique',
      'store.wageredBalance': '💰 Wagered balance: {{balance}} ⭐',
      'store.need50percent': '(need 50% of gift price)',
      'store.insufficientFunds': '💰 Insufficient funds',
      'store.needToWager': '🎯 Need to wager {{amount}} ⭐',
      'store.buy': '{{price}} ⭐',
      'store.sending': '⏳ Sending...',
      'store.giftsSentToTelegram': '💡 Gifts are sent to your Telegram',
      'store.purchaseError': 'Purchase failed',
      'store.dailyLimitExceeded': 'Daily gift purchase limit exceeded ({{limit}} pcs.)',
      'store.requestTimeout': 'Request timed out',
      
      // Leaderboard (Leaderboard.tsx)
      'leaderboard.loadingLeaderboard': 'Loading leaderboard...',
      'leaderboard.yourPlace': 'Your place:',
      'leaderboard.notInLeaderboard': 'Not in leaderboard',
      'leaderboard.emptyLeaderboard': 'Leaderboard is empty',
      'leaderboard.you': 'You',
      'leaderboard.player': 'Player',
      'leaderboard.gamesPlayed': 'Games won',
      'leaderboard.totalWin': 'Total winnings',
      'leaderboard.bestMultiplier': 'Best multiplier',
      'leaderboard.avgMultiplier': 'Average multiplier',
      
      // Payment Modal (PaymentModal.tsx)
      'payment.topUpBalance': '💰 Top up balance',
      'payment.amountOfStars': 'Amount of stars:',
      'payment.topUpWith': '💳 Top up with {{amount}} ⭐',
      'payment.toppingUp': '⏳ Topping up...',
      'payment.starsRange': 'Amount of stars should be from 10 to 1000000',
      'payment.paymentsUnavailable': 'Payments unavailable in your Telegram version',
      'payment.authDataError': 'Could not get authentication data',
      'payment.paymentError': 'Error occurred while creating payment',
      
      // Gift Requests (GiftRequests.tsx)
      'gifts.noRequests': 'No gift withdrawal requests',
      'gifts.buyUniqueGifts': 'Buy unique gifts in the store',
      'gifts.processing': 'Processing\n(up to 24 hours)',
      'gifts.sending': 'Being sent\n(15-45 min)',
      'gifts.sent': 'Gift sent',
      'gifts.rejected': 'Rejected',
      'gifts.created': 'Created:',
      'gifts.sentAt': 'Sent:',
      'gifts.contactSupport': '💬 Contact support for clarification',
      'gifts.cancelReasons.no_message': 'You did not send a message to the bot, please read the instructions again.',
      'gifts.cancelReasons.price_changed': 'During processing, the gift price changed.',
      'gifts.cancelReasons.suspect_act': 'We noticed strange activity on your account, we need time to investigate.',
      
      // Footer Navigation  
      'nav.home': 'Game',
      'nav.profile': 'Profile', 
      'nav.leaderboard': 'Leaderboard',
      'nav.store': 'Store',
      
      // Error Boundary
      'errors.occurred': 'An error occurred',
      'errors.networkOrApi': 'Network or API problem.',
      'errors.tryAgain': 'Try again',
      
      // Maintenance Screen
      'maintenance.title': 'Technical maintenance',
      'maintenance.message': 'Technical maintenance is currently underway.\nPlease try again later.',
      'maintenance.retry': '🔄 Try again',
      'maintenance.footer': 'Usually this takes a few minutes',
      
      // Common loading and alerts
      'common.loading': 'Loading...',
      'common.you': 'You',
      'common.player': 'Player',
      'alerts.linkCopied': 'Referral link copied!',
      'alerts.paymentCreated': '🎉 Payment for {{amount}} stars successfully created! Check your Telegram to complete the payment.',
      'alerts.invalidAmount': 'Invalid refund amount',
      'alerts.refundSuccess': '✅ Refunded {{amount}} stars. New balance: {{balance}}',
      'alerts.refundError': 'Error refunding stars: {{error}}',
      'alerts.channelBonusSuccess': 'Channel bonus granted successfully! You received {{amount}} ⭐',
      'alerts.channelBonusError': 'Channel bonus error: {{error}}',
      'alerts.userNotFound': 'User not found in Telegram channel. Make sure you have started the bot.',
      'alerts.notSubscribed': 'You are not subscribed to the channel. Please subscribe first.',
      'alerts.bonusAlreadyClaimed': 'You have already claimed the bonus for this channel.',
      'profile.bonusesTitle': '⚡️ Bonuses',
      'profile.bonusDescription': 'Subscribe to our <a href="https://t.me/crasherapp" target="_blank" rel="noopener noreferrer">channel</a> and get {{amount}} ⭐ bonus!',
      'profile.getBonusButton': '💎 Get bonus',
      'profile.checkingBonus': '⏳ Checking...',
      
      // GiftRequests specific (additional to existing ones)
      'gifts.historyTitle': 'Withdrawal request history',
      
      // Payment alerts
      'alerts.paymentInstructions': '💬 Payment invoice sent to bot chat.\n\n1️⃣ Go to chat with @crash_app_offical_bot\n2️⃣ Click "Pay ⭐️{{amount}}" button\n3️⃣ Confirm payment\n\n✅ Balance will update automatically after payment!',
      
      // Additional translations for hardcoded strings
      'game.coefficient': 'Coefficient',
      'common.seconds': 'sec',
      'common.seconds_short': 'sec.',
      'profile.statisticsTitle': '📊 Statistics',
      'profile.gamesPlayedLabel': 'Games won',
      'profile.totalWinLabel': 'Total winnings',
      'profile.bestMultiplierLabel': 'Best multiplier',
      'profile.avgMultiplierLabel': 'Average multiplier',
      'profile.giftsTitle': '🎁 Gifts',
      'profile.testingTitle': '🧪 Testing (development only)',
      'profile.refundStarsLabel': 'Refund stars for testing:',
      'profile.testingNoteText': '⚠️ This function is for testing only. Will be removed in production.',
      'store.loadingGiftsText': 'Loading gifts...',
      'store.regularTitle': '🎁 Regular',
      'store.uniqueTitle': '⭐ Unique',
      'store.regularWarning': '⚠️ WARNING! Regular gifts cannot be exchanged for stars or transferred!',
      'store.wageredBalanceText': '💰 Wagered balance: {{balance}} ⭐',
      'store.need50percentText': '(need 50% of gift price)',
      'store.giftsSentText': '💡 Gifts are sent to your Telegram',
      'store.importantWarning': '⚠️ IMPORTANT: After purchase, be sure to send any message to bot @{{giftBot}}, otherwise the gift will not be delivered!\n\nBalance will be charged immediately. Continue?',
      'store.regularGiftConfirm': 'The gift will be sent to your Telegram immediately.\n\These GIFTS CANNOT BE EXCHANGED FOR STARS OR TRANSFERRED!\n\n Extend?',
      'store.authDataFailed': 'Failed to get authentication data',
      'store.giftPurchaseSuccess': '🎉 {{message}}\n\n📬 Bot opened in new tab. Send it any message to activate delivery!',
      'store.dailyLimitMessage': 'Daily gift purchase limit exceeded ({{limit}} pcs.)',
      'console.telegramDataError': 'Failed to get Telegram data:',
      'console.statisticsError': 'Error getting statistics:',
      'console.refundError': 'Refund error:',
      'console.invoiceSentToChat': 'Invoice was sent to chat, you can pay manually',
      'console.leaderboardLoadError': 'Error loading leaderboard:',
      'alerts.referralLinkAlert': 'Referral link: {{link}}',
      'errors.unknown': 'Unknown error',
      'payment.invoiceTitle': 'Top up CRASHER balance',
      'payment.invoiceDescription': 'Purchase {{amount}} stars for the game',
      'store.giftSentFallback': 'Gift sent: {{name}}!',
      
      // Promo code restrictions
      'store.promoBalanceLocked': 'Insufficient available balance. Available: {{available}} stars. Locked by promo codes: {{locked}} stars. Top up your balance by {{required}} stars to unlock promo rewards.',
      'game.promoBalanceLocked': 'Insufficient available balance for betting. Available: {{available}} stars. Locked by promo codes: {{locked}} stars. Top up your balance to unlock promo rewards.',
      'store.promoBalanceTitle': 'Promo Code Restriction',
      
      // Promo code section
      'profile.promoCodeTitle': '🎫 Enter promo code',
      'profile.promoCodePlaceholder': 'Enter promo code',
      'profile.promoCodeActivate': 'Activate',
      'profile.promoCodeActivating': 'Activating...',
      'profile.promoCodeSuccess': 'Promo code activated!\nReceived: {{amount}} ⭐{{withdrawal}}',
      'profile.promoCodeWithdrawal': '\n⚠️ To withdraw these stars, you need to top up your balance by {{amount}} stars',
      'profile.promoCodeNotFound': 'Promo code not found or inactive',
      'profile.promoCodeAlreadyUsed': 'Promo code already used',
      'profile.promoCodeExpired': 'Promo code expired',
      'profile.promoCodeExhausted': 'Promo code exhausted',
      'profile.promoCodeInvalidFormat': 'Invalid promo code format',
      'profile.promoCodeError': 'Promo code activation error: {{error}}'
    },
  },
  ru: {
    translation: {
      // Navigation
      home: 'Игра',
      profile: 'Профиль',
      leaderboard: 'Рейтинг',
      store: 'Магазин',
      
      // Common
      loading: 'Загрузка...',
      balance: 'Баланс',
      
      // Game (GameWebSocket.tsx)
      'game.connectingToServer': 'Подключение к серверу...',
      'game.connectionFailed': 'Ошибка подключения',
      'game.tryAgain': '🔄 Попробовать снова',
      'game.canOnlyJoinWaiting': 'Можно вступить только в ожидании нового раунда.',
      'game.userIdError': 'Ошибка: не удалось получить ID пользователя',
      'game.insufficientFunds': 'Недостаточно средств! Нужно минимум {{amount}} звёзд для ставки.',
      'game.minBet': 'Минимальная ставка 10 звёзд!',
      'game.joinError': 'Ошибка вступления в игру: ',
      'game.networkError': 'Ошибка сети при вступлении в игру.',
      'game.cashoutError': 'Ошибка cashout: ',
      'game.wsConnected': '🟢 WebSocket подключен',
      'game.wsConnecting': '🟡 Подключение...',
      'game.wsReconnecting': '🟡 Переподключение...',
      'game.wsNoConnection': '🔴 Нет соединения',
      'game.roundAlreadyStarted': '🔒 Раунд уже начался',
      'game.waitingForStart': '⏳ Ожидание старта раунда{{countdown}}',
      'game.insufficientStars': '💸 Недостаточно звёзд',
      'game.joinRound': '🎮 Вступить в раунд',
      'game.joining': '⏳ Присоединение...',
      'game.startIn': 'Старт через {{seconds}} сек.',
      'game.cashoutStars': '💰 Вывести звёзды',
      'game.cashing': '⏳ Вывод...',
      'game.waitingForEnd': '⏳ Ожидаем конца раунда...',
      'game.bet': 'Ставка:',
      'game.crash': '💥 КРАШ!',
      'game.cashedOut': '✅ +{{amount}}⭐ x{{multiplier}}',
      
      // Profile (Profile.tsx)
      'profile.loadingProfile': 'Загрузка профиля...',
      'profile.statistics': '📊 Статистика',
      'profile.gamesPlayed': 'Выиграно игр',
      'profile.totalWin': 'Общий выигрыш',
      'profile.bestMultiplier': 'Лучший множитель',
      'profile.avgMultiplier': 'Средний множитель',
      'profile.gifts': '🎁 Подарки',
      'profile.testing': '🧪 Тестирование (только для разработки)',
      'profile.refundStars': 'Возврат звёзд для тестирования:',
      'profile.refunding': '⏳ Возврат...',
      'profile.refund': '🔄 Вернуть {{amount}} ⭐',
      'profile.testingNote': '⚠️ Эта функция предназначена только для тестирования. В продакшене будет удалена.',
      
      // Store (Store.tsx)
      'store.loadingGifts': 'Загрузка подарков...',
      'store.regular': '🎁 Обычные',
      'store.unique': '⭐ Уникальные',
      'store.wageredBalance': '💰 Отыгранный баланс: {{balance}} ⭐',
      'store.need50percent': '(нужно 50% от цены подарка)',
      'store.insufficientFunds': '💰 Недостаточно средств',
      'store.needToWager': '🎯 Нужно отыграть {{amount}} ⭐',
      'store.buy': '{{price}} ⭐',
      'store.sending': '⏳ Отправка...',
      'store.giftsSentToTelegram': '💡 Подарки отправляются в ваш Telegram',
      'store.purchaseError': 'Ошибка покупки',
      'store.dailyLimitExceeded': 'Превышен дневной лимит покупки подарков ({{limit}} шт.)',
      'store.requestTimeout': 'Запрос превысил время ожидания',
      
      // Leaderboard (Leaderboard.tsx)
      'leaderboard.loadingLeaderboard': 'Загрузка рейтинга...',
      'leaderboard.yourPlace': 'Ваше место:',
      'leaderboard.notInLeaderboard': 'Не в рейтинге',
      'leaderboard.emptyLeaderboard': 'Рейтинг пока пуст',
      'leaderboard.you': 'Вы',
      'leaderboard.player': 'Игрок',
      'leaderboard.gamesPlayed': 'Выиграно игр',
      'leaderboard.totalWin': 'Общий выигрыш',
      'leaderboard.bestMultiplier': 'Лучший множитель',
      'leaderboard.avgMultiplier': 'Средний множитель',
      
      // Payment Modal (PaymentModal.tsx)
      'payment.topUpBalance': '💰 Пополнение баланса',
      'payment.amountOfStars': 'Количество звёзд:',
      'payment.topUpWith': '💳 Пополнить на {{amount}} ⭐',
      'payment.toppingUp': '⏳ Пополняем...',
      'payment.starsRange': 'Количество звёзд должно быть от 10 до 1000000',
      'payment.paymentsUnavailable': 'Платежи недоступны в вашей версии Telegram',
      'payment.authDataError': 'Не удалось получить данные аутентификации',
      'payment.paymentError': 'Произошла ошибка при создании платежа',
      
      // Gift Requests (GiftRequests.tsx)
      'gifts.noRequests': 'Запросов на вывод подарков нет',
      'gifts.buyUniqueGifts': 'Покупайте уникальные подарки в магазине',
      'gifts.processing': 'В обработке\n(до 24 часов)',
      'gifts.sending': 'Производится отправка\n(15-45 мин)',
      'gifts.sent': 'Подарок отправлен',
      'gifts.rejected': 'Отклонено',
      'gifts.created': 'Создан:',
      'gifts.sentAt': 'Отправлен:',
      'gifts.contactSupport': '💬 Свяжитесь с поддержкой для уточнения причины',
      'gifts.cancelReasons.no_message': 'Вы не отправили сообщение боту, пожалуйста ещё раз ознакомьтесь с инструкцией.',
      'gifts.cancelReasons.price_changed': 'Во время обработки запроса цена на подарок изменилась.',
      'gifts.cancelReasons.suspect_act': 'Мы заметили странную активность на вашем аккаунте, нам нужно время чтобы разобраться в ситуации.',
      
      // Footer Navigation
      'nav.home': 'Игра',
      'nav.profile': 'Профиль',
      'nav.leaderboard': 'Рейтинг',
      'nav.store': 'Магазин',
      
      // Error Boundary
      'errors.occurred': 'Произошла ошибка',
      'errors.networkOrApi': 'Проблема с сетью или API.',
      'errors.tryAgain': 'Попробовать снова',
      
      // Maintenance Screen
      'maintenance.title': 'Технические работы',
      'maintenance.message': 'В настоящее время проводятся технические работы.\nПожалуйста, попробуйте зайти позже.',
      'maintenance.retry': '🔄 Попробовать снова',
      'maintenance.footer': 'Обычно это занимает несколько минут',
      
      // Common loading and alerts
      'common.loading': 'Загрузка...',
      'common.you': 'Вы',
      'common.player': 'Игрок',
      'alerts.linkCopied': 'Реферальная ссылка скопирована!',
      'alerts.paymentCreated': '🎉 Платёж на {{amount}} звёзд успешно создан! Проверьте ваш Telegram для завершения оплаты.',
      'alerts.invalidAmount': 'Некорректная сумма для возврата',
      'alerts.refundSuccess': '✅ Возвращено {{amount}} звёзд. Новый баланс: {{balance}}',
      'alerts.refundError': 'Ошибка при возврате звёзд: {{error}}',
      'alerts.channelBonusSuccess': 'Бонус за подписку получен! Вы получили {{amount}} ⭐',
      'alerts.channelBonusError': 'Ошибка получения бонуса: {{error}}',
      'alerts.userNotFound': 'Пользователь не найден в Telegram канале. Убедитесь, что вы запустили бота.',
      'alerts.notSubscribed': 'Вы не подписаны на канал. Пожалуйста, подпишитесь сначала.',
      'alerts.bonusAlreadyClaimed': 'Вы уже получили бонус за этот канал.',
      'profile.bonusesTitle': '⚡️ Бонусы',
      'profile.bonusDescription': 'Подпишитесь на наш <a href="https://t.me/crasherapp" target="_blank" rel="noopener noreferrer">канал</a> и получите {{amount}} ⭐ бонус!',
      'profile.getBonusButton': '💎 Получить бонус',
      'profile.checkingBonus': '⏳ Проверяем...',
      
      // GiftRequests specific (additional to existing ones)
      'gifts.historyTitle': 'История запросов на вывод',
      
      // Payment alerts
      'alerts.paymentInstructions': '💬 Счёт для оплаты отправлен в чат с ботом.\n\n1️⃣ Перейдите в чат с @crash_app_offical_bot\n2️⃣ Нажмите кнопку "Заплатить ⭐️{{amount}}"\n3️⃣ Подтвердите оплату\n\n✅ После оплаты баланс обновится автоматически!',
      
      // Additional translations for hardcoded strings
      'game.coefficient': 'Коэффициент',
      'common.seconds': 'сек',
      'common.seconds_short': 'сек.',
      'profile.statisticsTitle': '📊 Статистика',
      'profile.gamesPlayedLabel': 'Выиграно игр',
      'profile.totalWinLabel': 'Общий выигрыш',
      'profile.bestMultiplierLabel': 'Лучший множитель',
      'profile.avgMultiplierLabel': 'Средний множитель',
      'profile.giftsTitle': '🎁 Подарки',
      'profile.testingTitle': '🧪 Тестирование (только для разработки)',
      'profile.refundStarsLabel': 'Возврат звёзд для тестирования:',
      'profile.testingNoteText': '⚠️ Эта функция предназначена только для тестирования. В продакшене будет удалена.',
      'store.loadingGiftsText': 'Загрузка подарков...',
      'store.regularTitle': '🎁 Обычные',
      'store.uniqueTitle': '⭐ Уникальные',
      'store.regularWarning': '⚠️ ВНИМАНИЕ! Обычные подарки нельзя обменять на звёзды или передавать!',
      'store.wageredBalanceText': '💰 Отыгранный баланс: {{balance}} ⭐',
      'store.need50percentText': '(нужно 50% от цены подарка)',
      'store.giftsSentText': '💡 Подарки отправляются в ваш Telegram',
      'store.importantWarning': '⚠️ ВАЖНО: После покупки обязательно отправьте любое сообщение боту @{{giftBot}}, иначе подарок не будет доставлен!\n\nБаланс будет списан сразу. Продолжить?',
      'store.regularGiftConfirm': 'Подарок будет отправлен в ваш Telegram сразу же.\n\nДАННЫЕ ПОДАРКИ НЕЛЬЗЯ ОБМЕНИВАТЬ НА ЗВЁЗДЫ И ПЕРЕДАВАТЬ!\n\nПродолжить?',
      'store.authDataFailed': 'Не удалось получить данные аутентификации',
      'store.giftPurchaseSuccess': '🎉 {{message}}\n\n📬 Бот открыт в новой вкладке. Отправьте ему любое сообщение для активации доставки!',
      'store.dailyLimitMessage': 'Превышен дневной лимит покупки подарков ({{limit}} шт.)',
      'console.telegramDataError': 'Не удалось получить данные Telegram:',
      'console.statisticsError': 'Ошибка получения статистики:',
      'console.refundError': 'Ошибка возврата:',
      'console.invoiceSentToChat': 'Invoice была отправлена в чат, можете оплатить вручную',
      'console.leaderboardLoadError': 'Ошибка загрузки рейтинга:',
      'alerts.referralLinkAlert': 'Реферальная ссылка: {{link}}',
      'errors.unknown': 'Неизвестная ошибка',
      'payment.invoiceTitle': 'Пополнение баланса CRASHER',
      'payment.invoiceDescription': 'Покупка {{amount}} звёзд для игры',
      'store.giftSentFallback': 'Подарок отправлен: {{name}}!',
      
      // Promo code restrictions
      'store.promoBalanceLocked': 'Недостаточно доступного баланса. Пополните баланс на {{required}} звёзд, чтобы разблокировать средства от промокодов.',
      'game.promoBalanceLocked': 'Недостаточно доступного баланса для ставки. Пополните баланс, чтобы разблокировать средства от промокодов.',
      'store.promoBalanceTitle': 'Ограничение по промокоду',
      
      // Promo code section
      'profile.promoCodeTitle': '🎫 Введите промокод',
      'profile.promoCodePlaceholder': 'Введите промокод',
      'profile.promoCodeActivate': 'Активировать',
      'profile.promoCodeActivating': 'Активация...',
      'profile.promoCodeSuccess': 'Промокод активирован!\nПолучено: {{amount}} ⭐{{withdrawal}}',
      'profile.promoCodeWithdrawal': '\n⚠️ Для вывода этих звёзд нужно пополнить баланс на {{amount}} звёзд',
      'profile.promoCodeNotFound': 'Промокод не найден или неактивен',
      'profile.promoCodeAlreadyUsed': 'Промокод уже использован',
      'profile.promoCodeExpired': 'Промокод истёк',
      'profile.promoCodeExhausted': 'Промокод исчерпан',
      'profile.promoCodeInvalidFormat': 'Неверный формат промокода',
      'profile.promoCodeError': 'Ошибка активации промокода: {{error}}'
    },
  },
}

i18n.use(initReactI18next).init({
  resources,
  lng: 'en', // Временный язык до инициализации в App.tsx
  fallbackLng: 'en',
  interpolation: {
    escapeValue: false,
  },
})

// Добавляем обработчик для автоматического сохранения языка в localStorage
i18n.on('languageChanged', (lng) => {
  localStorage.setItem('i18nextLng', lng)
})

export default i18n
