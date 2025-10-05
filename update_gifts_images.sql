-- Обновление image_url для существующих подарков на относительные пути
-- и добавление уникальных подарков с изображениями из frontend/assets/gifts/

-- Сначала обновим обычные подарки, оставив emoji в качестве fallback
UPDATE gifts SET image_url = '/gifts/original/5170233102089322756.png', description='' WHERE id = 'bear';
UPDATE gifts SET image_url = '/gifts/original/5170145012310081615.png', description='' WHERE id = 'heart';
UPDATE gifts SET image_url = '/gifts/original/5170250947678437525.png', description='' WHERE id = 'gift';
UPDATE gifts SET image_url = '/gifts/original/5170144170496491616.png', description='' WHERE id = 'cake';
UPDATE gifts SET image_url = '/gifts/original/5170564780938756245.png', description='' WHERE id = 'rocket';
UPDATE gifts SET image_url = '/gifts/original/5170314324215857265.png', description='' WHERE id = 'roses';
UPDATE gifts SET image_url = '/gifts/original/5170521118301225164.png', description='' WHERE id = 'gem';
UPDATE gifts SET image_url = '/gifts/original/5170690322832818290.png', description='' WHERE id = 'ring';
UPDATE gifts SET image_url = '/gifts/original/5168043875654172773.png', description='' WHERE id = 'trophy';

-- Добавим уникальные подарки с изображениями из папки unique
-- Цены в USD взяты примерно ($1-10 range для уникальных подарков)

INSERT INTO gifts (id, name, description, price, ton_price, telegram_gift_id, emoji, image_url, sort_order, is_unique) VALUES
('astralshard', 'Astral Shard', '', NULL, 270.50, 'astral_shard_unique', '💎', '/gifts/unique/Astral Shard.png', 1, TRUE),
('bdaycandle', 'B-Day Candle', '', NULL, 4.55, 'bday_candle_unique', '🕯️', '/gifts/unique/B-Day Candle.png', 67, TRUE),
('berrybox', 'Berry Box', '', NULL, 12.36, 'berry_box_unique', '🍓', '/gifts/unique/Berry Box.png', 31, TRUE),
('bigyear', 'Big Year', '', NULL, 5.30, 'big_year_unique', '🎊', '/gifts/unique/Big Year.png', 61, TRUE),
('bondedring', 'Bonded Ring', '', NULL, 187.10, 'bonded_ring_unique', '💍', '/gifts/unique/Bonded Ring.png', 4, TRUE),
('bowtie', 'Bow Tie', '', NULL, 10.60, 'bow_tie_unique', '🎀', '/gifts/unique/Bow Tie.png', 34, TRUE),
('bunnymuffin', 'Bunny Muffin', '', NULL, 10.50, 'bunny_muffin_unique', '🧁', '/gifts/unique/Bunny Muffin.png', 36, TRUE),
('candycane', 'Candy Cane', '', NULL, 4.52, 'candy_cane_unique', '🍭', '/gifts/unique/Candy Cane.png', 68, TRUE),
('cookieheart', 'Cookie Heart', '', NULL, 5.44, 'cookie_heart_unique', '🍪', '/gifts/unique/Cookie Heart.png', 59, TRUE),
('crystalball', 'Crystal Ball', '', NULL, 22.14, 'crystal_ball_unique', '🔮', '/gifts/unique/Crystal Ball.png', 27, TRUE),
('cupidcharm', 'Cupid Charm', '', NULL, 31.03, 'cupid_charm_unique', '💘', '/gifts/unique/Cupid Charm.png', 18, TRUE),
('easteregg', 'Easter Egg', '', NULL, 8.09, 'easter_egg_unique', '🥚', '/gifts/unique/Easter Egg.png', 44, TRUE),
('electricskull', 'Electric Skull', '', NULL, 90.20, 'electric_skull_unique', '💀', '/gifts/unique/Electric Skull.png', 11, TRUE),
('eternalcandle', 'Eternal Candle', '', NULL, 10.55, 'eternal_candle_unique', '🕯️', '/gifts/unique/Eternal Candle.png', 35, TRUE),
('eternalrose', 'Eternal Rose', '', NULL, 41.94, 'eternal_rose_unique', '🌹', '/gifts/unique/Eternal Rose.png', 17, TRUE),
('evileye', 'Evil Eye', '', NULL, 11.97, 'evil_eye_unique', '🧿', '/gifts/unique/Evil Eye.png', 33, TRUE),
('flyingbroom', 'Flying Broom', '', NULL, 27.25, 'flying_broom_unique', '🧹', '/gifts/unique/Flying Broom.png', 21, TRUE),
('gemsignet', 'Gem Signet', '', NULL, 232.99, 'gem_signet_unique', '💎', '/gifts/unique/Gem Signet.png', 2, TRUE),
('genielamp', 'Genie Lamp', '', NULL, 142.50, 'genie_lamp_unique', '🪔', '/gifts/unique/Genie Lamp.png', 6, TRUE),
('gingercookie', 'Ginger Cookie', '', NULL, 5.59, 'ginger_cookie_unique', '🍪', '/gifts/unique/Ginger Cookie.png', 57, TRUE),
('hangingstar', 'Hanging Star', '', NULL, 14.12, 'hanging_star_unique', '⭐', '/gifts/unique/Hanging Star.png', 29, TRUE),
('hexpot', 'Hex Pot', '', NULL, 8.30, 'hex_pot_unique', '🫖', '/gifts/unique/Hex Pot.png', 43, TRUE),
('holidaydrink', 'Holiday Drink', '', NULL, 5.48, 'holiday_drink_unique', '🍹', '/gifts/unique/Holiday Drink.png', 58, TRUE),
('homemadecake', 'Homemade Cake', '', NULL, 5.26, 'homemade_cake_unique', '🎂', '/gifts/unique/Homemade Cake.png', 62, TRUE),
('hypnolollipop', 'Hypno Lollipop', '', NULL, 6.35, 'hypno_lollipop_unique', '🍭', '/gifts/unique/Hypno Lollipop.png', 52, TRUE),
('jackinthebox', 'Jack-in-the-Box', '', NULL, 6.71, 'jack_in_box_unique', '🎁', '/gifts/unique/Jack-in-the-Box.png', 49, TRUE),
('jellybunny', 'Jelly Bunny', '', NULL, 10.42, 'jelly_bunny_unique', '🐰', '/gifts/unique/Jelly Bunny.png', 37, TRUE),
('jesterhat', 'Jester Hat', '', NULL, 5.83, 'jester_hat_unique', '🎭', '/gifts/unique/Jester Hat.png', 56, TRUE),
('jinglebells', 'Jingle Bells', '', NULL, 5.90, 'jingle_bells_unique', '🔔', '/gifts/unique/Jingle Bells.png', 55, TRUE),
('joyfulbundle', 'Joyful Bundle', '', NULL, 7.42, 'joyful_bundle_unique', '💐', '/gifts/unique/Joyful Bundle.png', 46, TRUE),
('kissedfrog', 'Kissed Frog', '', NULL, 116.50, 'kissed_frog_unique', '🐸', '/gifts/unique/Kissed Frog.png', 7, TRUE),
('lightsword', 'Light Sword', '', NULL, 9.71, 'light_sword_unique', '⚔️', '/gifts/unique/Light Sword.png', 39, TRUE),
('lovecandle', 'Love Candle', '', NULL, 27.22, 'love_candle_unique', '🕯️', '/gifts/unique/Love Candle.png', 22, TRUE),
('lovepotion', 'Love Potion', '', NULL, 28.07, 'love_potion_unique', '🧪', '/gifts/unique/Love Potion.png', 20, TRUE),
('lunarsnake', 'Lunar Snake', '', NULL, 4.59, 'lunar_snake_unique', '🐍', '/gifts/unique/Lunar Snake.png', 66, TRUE),
('lushbouquet', 'Lush Bouquet', '', NULL, 7.59, 'lush_bouquet_unique', '💐', '/gifts/unique/Lush Bouquet.png', 45, TRUE),
('madpumpkin', 'Mad Pumpkin', '', NULL, 50.90, 'mad_pumpkin_unique', '🎃', '/gifts/unique/Mad Pumpkin.png', 15, TRUE),
('magicpotion', 'Magic Potion', '', NULL, 194.15, 'magic_potion_unique', '🧪', '/gifts/unique/Magic Potion.png', 3, TRUE),
('nekohelmet', 'Neko Helmet', '', NULL, 91.75, 'neko_helmet_unique', '😺', '/gifts/unique/Neko Helmet.png', 10, TRUE),
('partysparkler', 'Party Sparkler', '', NULL, 5.41, 'party_sparkler_unique', '🎇', '/gifts/unique/Party Sparkler.png', 60, TRUE),
('petsnake', 'Pet Snake', '', NULL, 4.70, 'pet_snake_unique', '🐍', '/gifts/unique/Pet Snake.png', 65, TRUE),
('recordplayer', 'Record Player', '', NULL, 24.72, 'record_player_unique', '🎵', '/gifts/unique/Record Player.png', 23, TRUE),
('restlessjar', 'Restless Jar', '', NULL, 7.42, 'restless_jar_unique', '🫙', '/gifts/unique/Restless Jar.png', 47, TRUE),
('sakuraflower', 'Sakura Flower', '', NULL, 13.56, 'sakura_flower_unique', '🌸', '/gifts/unique/Sakura Flower.png', 30, TRUE),
('santahat', 'Santa Hat', '', NULL, 6.71, 'santa_hat_unique', '🎅', '/gifts/unique/Santa Hat.png', 50, TRUE),
('scaredcat', 'Scared Cat', '', NULL, 151.72, 'scared_cat_unique', '🙀', '/gifts/unique/Scared Cat.png', 5, TRUE),
('sharptongue', 'Sharp Tongue', '', NULL, 113.10, 'sharp_tongue_unique', '👅', '/gifts/unique/Sharp Tongue.png', 8, TRUE),
('signetring', 'Signet Ring', '', NULL, 81.20, 'signet_ring_unique', '💍', '/gifts/unique/Signet Ring.png', 13, TRUE),
('skullflower', 'Skull Flower', '', NULL, 22.95, 'skull_flower_unique', '💀', '/gifts/unique/Skull Flower.png', 25, TRUE),
('sleighbell', 'Sleigh Bell', '', NULL, 23.30, 'sleigh_bell_unique', '🔔', '/gifts/unique/Sleigh Bell.png', 24, TRUE),
('snakebox', 'Snake Box', '', NULL, 4.52, 'snake_box_unique', '🐍', '/gifts/unique/Snake Box.png', 69, TRUE),
('snoopcigar', 'Snoop Cigar', '', NULL, 14.72, 'snoop_cigar_unique', '🚬', '/gifts/unique/Snoop Cigar.png', 28, TRUE),
('snoopdogg', 'Snoop Dogg', '', NULL, 5.22, 'snoop_dogg_unique', '🎤', '/gifts/unique/Snoop Dogg.png', 63, TRUE),
('snowglobe', 'Snow Globe', '', NULL, 9.11, 'snow_globe_unique', '❄️', '/gifts/unique/Snow Globe.png', 40, TRUE),
('snowmittens', 'Snow Mittens', '', NULL, 10.21, 'snow_mittens_unique', '🧤', '/gifts/unique/Snow Mittens.png', 38, TRUE),
('spicedwine', 'Spiced Wine', '', NULL, 7.42, 'spiced_wine_unique', '🍷', '/gifts/unique/Spiced Wine.png', 48, TRUE),
('spyagaric', 'Spy Agaric', '', NULL, 8.41, 'spy_agaric_unique', '🍄', '/gifts/unique/Spy Agaric.png', 42, TRUE),
('starnotepad', 'Star Notepad', '', NULL, 6.57, 'star_notepad_unique', '📝', '/gifts/unique/Star Notepad.png', 51, TRUE),
('swisswatch', 'Swiss Watch', '', NULL, 98.90, 'swiss_watch_unique', '⌚', '/gifts/unique/Swiss Watch.png', 9, TRUE),
('tamagadget', 'Tama Gadget', '', NULL, 6.00, 'tama_gadget_unique', '🎮', '/gifts/unique/Tama Gadget.png', 54, TRUE),
('tophat', 'Top Hat', '', NULL, 29.30, 'top_hat_unique', '🎩', '/gifts/unique/Top Hat.png', 19, TRUE),
('toybear', 'Toy Bear', '', NULL, 53.00, 'toy_bear_unique', '🧸', '/gifts/unique/Toy Bear.png', 14, TRUE),
('trappedheart', 'Trapped Heart', '', NULL, 22.21, 'trapped_heart_unique', '💔', '/gifts/unique/Trapped Heart.png', 26, TRUE),
('valentinebox', 'Valentine Box', '', NULL, 12.36, 'valentine_box_unique', '💝', '/gifts/unique/Valentine Box.png', 32, TRUE),
('vintagecigar', 'Vintage Cigar', '', NULL, 82.47, 'vintage_cigar_unique', '🚬', '/gifts/unique/Vintage Cigar.png', 12, TRUE),
('voodoodoll', 'Voodoo Doll', '', NULL, 47.06, 'voodoo_doll_unique', '🪆', '/gifts/unique/Voodoo Doll.png', 16, TRUE),
('whipcupcake', 'Whip Cupcake', '', NULL, 4.73, 'whip_cupcake_unique', '🧁', '/gifts/unique/Whip Cupcake.png', 64, TRUE),
('winterwreath', 'Winter Wreath', '', NULL, 6.14, 'winter_wreath_unique', '🎄', '/gifts/unique/Winter Wreath.png', 53, TRUE),
('witchhat', 'Witch Hat', '', NULL, 8.65, 'witch_hat_unique', '🧙', '/gifts/unique/Witch Hat.png', 41, TRUE),
('xmasstocking', 'Xmas Stocking', '', NULL, 4.28, 'xmas_stocking_unique', '🧦', '/gifts/unique/Xmas Stocking.png', 70, TRUE);

ON CONFLICT (id) DO UPDATE SET
    name = EXCLUDED.name,
    description = EXCLUDED.description,
    price = EXCLUDED.price,
    ton_price = EXCLUDED.ton_price,
    telegram_gift_id = EXCLUDED.telegram_gift_id,
    emoji = EXCLUDED.emoji,
    image_url = EXCLUDED.image_url,
    sort_order = EXCLUDED.sort_order,
    is_unique = EXCLUDED.is_unique;