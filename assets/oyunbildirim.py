from config import API_KEY
import requests
import discord
from discord.ext import commands,tasks
import sqlite3
from datetime import datetime, timedelta
import json
import os
import aiofiles


# IsThereAnyDeal API ayarları

API_URL = 'https://api.isthereanydeal.com/v01/deals/list/'

JSON_FILE = 'json/indirim.json'


class Oyunbildirim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_deals.start()
        self.clear_old_deals.start()

        # SQLite veritabanı bağlantısı
        self.conn = sqlite3.connect('database/indirim.db')
        self.c = self.conn.cursor()
        self.c.execute('''
            CREATE TABLE IF NOT EXISTS GameNotifyChannels (
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
        ''')
        self.c.execute('''
            CREATE TABLE IF NOT EXISTS PostedDeals (
                title TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                new_price REAL,
                old_price REAL,
                discount INTEGER,
                store TEXT,
                url TEXT,
                last_shared TIMESTAMP NOT NULL,
                PRIMARY KEY (title, guild_id, channel_id)
            )
        ''')
        self.conn.commit()

    def cog_unload(self):
        self.check_deals.cancel()
        self.clear_old_deals.cancel()
        self.conn.close()

    @commands.command(name='oyunbilayar')
    async def oyunbilayar(self, ctx, channel: discord.TextChannel):
        self.c.execute('INSERT OR REPLACE INTO GameNotifyChannels (guild_id, channel_id) VALUES (?, ?)',
                       (ctx.guild.id, channel.id))
        self.conn.commit()
        await ctx.send(f"İndirimdeki oyunlar, 5 dakikada bir {channel.mention} kanalında paylaşılacak. Bence herkes o kanalı sessize alsın xd")

    async def load_deals_from_api(self):
        last_checked = datetime.utcnow() - timedelta(minutes=5)
        params = {
            'key': API_KEY,
            'country': 'TR',
            'limit': 500,
            'price': '-price_cut',
            'cut': 0,
            'timestamp': last_checked.strftime('%Y-%m-%dT%H:%M:%SZ')
        }
        try:
            response = requests.get(API_URL, params=params, verify=False)
            response.raise_for_status()
            data = response.json()
            deals = data.get('list', [])
            if not deals:
                print("API'den oyun verisi alınamadı.")
                return
            async with aiofiles.open(JSON_FILE, 'w') as f:
                await f.write(json.dumps(deals))
            print(f"{len(deals)} indirimli oyun JSON dosyasına kaydedildi.")
        except requests.exceptions.RequestException as e:
            print(f"API isteğinde hata oluştu: {e}")

    async def load_deals_from_file(self):
        if not os.path.exists(JSON_FILE):
            await self.load_deals_from_api()
        async with aiofiles.open(JSON_FILE, 'r') as f:
            return json.loads(await f.read())

    @tasks.loop(minutes=5.0)
    async def check_deals(self):
        deals = await self.load_deals_from_file()
        while deals:
            deal = deals.pop(0)  # İlk anlaşmayı al ve listeden çıkar
            title = deal.get('title')
            if not title:
                print("Title yok, atlanıyor.")
                continue

            new_price = deal.get('price_new')
            old_price = deal.get('price_old')
            discount = deal.get('price_cut')
            store = deal.get('shop', {}).get('name')
            store_id = deal.get('shop', {}).get('id')
            url = deal.get('urls', {}).get('buy')

            if new_price is None or old_price is None or discount is None or store is None or url is None:
                print(f"Eksik bilgiler var, atlanıyor. Title: {title}")
                continue

            if store_id not in ['steam', 'epic']:
                print(f"{store} mağazasından gelen anlaşma atlanıyor. Title: {title}")
                continue

            now = datetime.now()

            if self.check_if_deal_exists(title):
                print(f"Deal {title} already shared today.")
                continue  # Veritabanında mevcutsa sonraki anlaşmaya geç

            await self.notify_channels(title, new_price, old_price, discount, store, url, now)
            async with aiofiles.open(JSON_FILE, 'w') as f:
                await f.write(json.dumps(deals))  # JSON dosyasını güncelle
            break

    def check_if_deal_exists(self, title):
        self.c.execute("SELECT 1 FROM PostedDeals WHERE title = ?", (title,))
        result = self.c.fetchone()
        print(f"Check if deal exists: {title}, result: {result}")
        return result is not None

    def save_deal(self, title, guild_id, channel_id, new_price, old_price, discount, store, url, now):
        try:
            self.c.execute('''
                INSERT INTO PostedDeals (title, guild_id, channel_id, new_price, old_price, discount, store, url, last_shared)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, guild_id, channel_id, new_price, old_price, discount, store, url, now))
            self.conn.commit()
            print(f"Saved deal {title} to DB for guild {guild_id}, channel {channel_id}")
        except sqlite3.IntegrityError:
            print(f"Deal {title} already exists in DB for guild {guild_id}, channel {channel_id}")

    async def notify_channels(self, title, new_price, old_price, discount, store, url, now):
        self.c.execute('SELECT guild_id, channel_id FROM GameNotifyChannels')
        channels = self.c.fetchall()
        for guild_id, channel_id in channels:
            if not self.check_if_deal_exists_for_guild(title, guild_id):
                channel = self.bot.get_channel(int(channel_id))
                if channel:
                    message = (
                        f"Yeni Oyun İndirimi: **{title}**!\n"
                        f"Yeni Fiyat: {new_price} TL\n"
                        f"Eski Fiyat: {old_price} TL\n"
                        f"İndirim: %{discount}\n"
                        f"Mağaza: {store}\n"
                        f"[Oyun Linki]({url})"
                    )
                    await channel.send(message)
                    self.save_deal(title, guild_id, channel_id, new_price, old_price, discount, store, url, now)


    def check_if_deal_exists_for_guild(self, title, guild_id):
        self.c.execute("SELECT 1 FROM PostedDeals WHERE title = ? AND guild_id = ? AND DATE(last_shared) = DATE('now')", (title, guild_id))
        return self.c.fetchone() is not None

    @tasks.loop(hours=360)  # 15 günde bir
    async def clear_old_deals(self):
        self.c.execute("DELETE FROM PostedDeals WHERE last_shared < DATE('now', '-15 days')")
        self.conn.commit()
        print("Eski indirimler silindi.")

    @clear_old_deals.before_loop
    async def before_clear_old_deals(self):
        await self.bot.wait_until_ready()

    @check_deals.before_loop
    async def before_check_deals(self):
        await self.bot.wait_until_ready()
        await self.load_deals_from_api()

async def setup(bot):
    await bot.add_cog(Oyunbildirim(bot))