from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, Integer, String, Text, DECIMAL, Index, PrimaryKeyConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username = Column(String(255), nullable=True)
    first_name = Column(String(255), nullable=True)
    last_name = Column(String(255), nullable=True)
    balance = Column(DECIMAL(12, 2), default=0.0, nullable=False)  # в звёздах с десятичными
    withdrawal_locked_balance = Column(DECIMAL(12, 2), default=0.0, nullable=False)  # заблокированный баланс от промокодов
    total_deposited = Column(DECIMAL(12, 2), default=0.0)
    total_withdrawn = Column(DECIMAL(12, 2), default=0.0)
    referral_code = Column(String(20), unique=True, nullable=True, index=True)
    referred_by_id = Column(BigInteger, ForeignKey('users.id'), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)
    language_code = Column(String(10), default='en')
    
    # Relationships
    stats = relationship("UserStats", back_populates="user", uselist=False)
    transactions = relationship("Transaction", back_populates="user")
    gift_purchases = relationship("GiftPurchase", back_populates="user")
    channel_bonuses = relationship("ChannelSubscriptionBonus", back_populates="user")
    promo_code_uses = relationship("PromoCodeUse", back_populates="user")
    referred_users = relationship("User", remote_side=[id])
    referrals_given = relationship("Referral", foreign_keys="Referral.referrer_id", back_populates="referrer")
    referrals_received = relationship("Referral", foreign_keys="Referral.referred_id", back_populates="referred")

class UserStats(Base):
    __tablename__ = 'user_stats'
    
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    total_games = Column(Integer, default=0)
    games_won = Column(Integer, default=0)
    games_lost = Column(Integer, default=0)
    total_wagered = Column(DECIMAL(12, 2), default=0.0)
    total_won = Column(DECIMAL(12, 2), default=0.0)
    wagered_balance = Column(DECIMAL(12, 2), default=0.0)  # Net winnings available for gift purchases
    best_multiplier = Column(DECIMAL(10, 2), default=0)
    avg_multiplier = Column(DECIMAL(10, 2), default=1.0)  # Average multiplier of winning games only
    # real_avg_multiplier = Column(DECIMAL(10, 2), default=0)  # Secret: average of ALL games (wins + losses) - DISABLED until migration
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="stats")

class GameHistory(Base):
    __tablename__ = 'game_history'
    
    id = Column(BigInteger, autoincrement=True)
    crash_point = Column(DECIMAL(10, 2), nullable=False)
    total_bet = Column(DECIMAL(12, 2), default=0.0)  # Общая ставка всех игроков
    total_payout = Column(DECIMAL(12, 2), default=0.0)  # Общие выплаты всем игрокам
    house_profit = Column(DECIMAL(12, 2), default=0.0)  # Прибыль дома (total_bet - total_payout)
    player_count = Column(Integer, default=0)  # Количество игроков в раунде
    is_completed = Column(Boolean, default=False)  # Раунд завершен (следующий раунд начался)
    played_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Партиционированная таблица: составной первичный ключ
    __table_args__ = (
        PrimaryKeyConstraint('id', 'played_at'),
    )
    
    # Relationships НЕ БУДУТ РАБОТАТЬ с партиционированными таблицами
    # transactions = relationship("Transaction", back_populates="game")

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(BigInteger, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False)
    game_id = Column(BigInteger, nullable=True)  # Убираем ForeignKey из-за партиционирования
    type = Column(String(20), nullable=False)  # deposit, withdrawal, game_win, game_loss, gift_purchase
    amount = Column(DECIMAL(12, 2), nullable=False)
    balance_after = Column(DECIMAL(12, 2), nullable=False)
    multiplier = Column(DECIMAL(10, 2), nullable=True)  # Для игровых транзакций - множитель кешаута
    payment_payload = Column(String(255), nullable=True)
    telegram_payment_id = Column(String(255), nullable=True)
    telegram_payment_charge_id = Column(String(255), nullable=True)  # For Telegram Stars refunds
    provider_payment_charge_id = Column(String(255), nullable=True)  # For payment provider refunds
    status = Column(String(20), default='pending')  # pending, completed, failed, refunded
    extra_data = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Партиционированная таблица: составной первичный ключ
    __table_args__ = (
        PrimaryKeyConstraint('id', 'created_at'),
    )
    
    # Relationships - только с users, НЕ с game_history (партиционирована)
    user = relationship("User", back_populates="transactions")

class Gift(Base):
    __tablename__ = 'gifts'
    
    id = Column(String(50), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(DECIMAL(12, 2), nullable=True)  # Цена в звёздах (NULL для уникальных подарков)
    ton_price = Column(DECIMAL(10, 4), nullable=True)  # Цена в USD для уникальных подарков (поле называется ton_price для совместимости)
    telegram_gift_id = Column(String(100), nullable=False)
    business_gift_id = Column(String(100), nullable=True)
    emoji = Column(String(10), nullable=True)
    image_url = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    is_unique = Column(Boolean, default=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    purchases = relationship("GiftPurchase", back_populates="gift")

class GiftPurchase(Base):
    __tablename__ = 'gift_purchases'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    gift_id = Column(String(50), ForeignKey('gifts.id'), nullable=False)
    price = Column(DECIMAL(12, 2), nullable=False)
    telegram_gift_id = Column(String(100), nullable=False)
    status = Column(String(20), default='pending', index=True)  # pending, sent, failed
    error_message = Column(Text, nullable=True)
    purchased_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User", back_populates="gift_purchases")
    gift = relationship("Gift", back_populates="purchases")

class Referral(Base):
    __tablename__ = 'referrals'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    referrer_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    referred_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    bonus_amount = Column(DECIMAL(12, 2), default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    referrer = relationship("User", foreign_keys=[referrer_id], back_populates="referrals_given")
    referred = relationship("User", foreign_keys=[referred_id], back_populates="referrals_received")
    
    # Unique constraint
    __table_args__ = (
        Index('idx_referrals_unique', 'referrer_id', 'referred_id', unique=True),
    )

class PaymentRequest(Base):
    __tablename__ = 'payment_requests'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    gift_id = Column(String(50), ForeignKey('gifts.id'), nullable=False)
    gift_name = Column(String(255), nullable=False)
    price = Column(DECIMAL(12, 2), nullable=False)  # цена в TON (для совместимости)
    price_stars = Column(DECIMAL(12, 2), nullable=False)  # цена в звездах (списанная с баланса)
    status = Column(String(20), default='pending', index=True)  # pending, approved, completed, canceled
    cancel_reason = Column(String(50), nullable=True)  # no_message, price_changed, suspect_act
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    user = relationship("User")
    gift = relationship("Gift")

class ChannelSubscriptionBonus(Base):
    __tablename__ = 'channel_subscription_bonuses'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    channel_id = Column(String(255), nullable=False, index=True)
    bonus_amount = Column(DECIMAL(12, 2), nullable=False)
    subscription_verified_at = Column(DateTime(timezone=True), nullable=True)
    bonus_claimed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    attempts_count = Column(Integer, default=1, nullable=False)
    last_attempt_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    
    # Relationships
    user = relationship("User", back_populates="channel_bonuses")
    
    # Constraints and indexes
    __table_args__ = (
        Index('idx_channel_bonuses_user_channel', 'user_id', 'channel_id', unique=True),
        Index('idx_channel_bonuses_claimed_at', 'bonus_claimed_at'),
    )

class SystemSettings(Base):
    __tablename__ = 'system_settings'
    
    key = Column(String(100), primary_key=True)
    value = Column(JSONB, nullable=False)
    description = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class PromoCode(Base):
    __tablename__ = 'promo_codes'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    code = Column(String(50), unique=True, nullable=False, index=True)
    balance_reward = Column(DECIMAL(12, 2), nullable=False)
    withdrawal_requirement = Column(DECIMAL(12, 2), nullable=True)
    max_uses = Column(Integer, nullable=False)
    current_uses = Column(Integer, default=0, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    uses = relationship("PromoCodeUse", back_populates="promo_code")

class PromoCodeUse(Base):
    __tablename__ = 'promo_code_uses'
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    promo_code_id = Column(BigInteger, ForeignKey('promo_codes.id'), nullable=False, index=True)
    user_id = Column(BigInteger, ForeignKey('users.id'), nullable=False, index=True)
    balance_granted = Column(DECIMAL(12, 2), nullable=False)
    withdrawal_requirement = Column(DECIMAL(12, 2), nullable=True)
    used_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    promo_code = relationship("PromoCode", back_populates="uses")
    user = relationship("User", back_populates="promo_code_uses")
    
    # Unique constraint - один промокод на пользователя
    __table_args__ = (
        Index('idx_promo_code_uses_unique', 'promo_code_id', 'user_id', unique=True),
    )