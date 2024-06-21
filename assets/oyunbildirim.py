from config import API_KEY
import requests
import discord
from discord.ext import commands, tasks
import sqlite3
from datetime import datetime, timedelta
import json
import os
import aiofiles

API_URL = 'https://api.isthereanydeal.com/deals/v2'
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

    @commands.command(name='oyunbildirimac')
    async def oyunbilayar(self, ctx, channel: discord.TextChannel):
        self.c.execute('INSERT OR REPLACE INTO GameNotifyChannels (guild_id, channel_id) VALUES (?, ?)',
                       (ctx.guild.id, channel.id))
        self.conn.commit()
        await ctx.send(f"İndirimdeki oyunlar, saatte bir {channel.mention} kanalında paylaşılacak.")
    
    @commands.command(name='oyunbildirimkapat')
    async def oyunbildirimkapat(self, ctx):
        self.c.execute('DELETE FROM GameNotifyChannels WHERE guild_id = ?', (ctx.guild.id,))
        self.conn.commit()
        await ctx.send(f"{ctx.channel.mention} kanalında oyun bildirimleri kapatıldı.")

    async def load_deals_from_api(self):
        params = {
            'key': API_KEY,
            'country': 'TR',
            'limit': 500,
            'sort': 'rank',
            'mature': 'false',
            'filter': 'N4IgxgrgLiBcoFsCWA7OBWADAGhAghgB5wCMmmAvrgCYBOCcA2iQGzYskC6uADgDb4oAMwD29JiWwAmbAGZuIKAE8eAUwlyFytQDkRMWIwDs2ABwKU+gAq1VAeVrVVtOFFoRVuAM5RV+BFbOYHCIqBg4eESk5FR4qlD4AMK0SFBIwfB4YbCyEQTEsGSUuAjx+ACqXs4hWWiwACx5UYUx3r7+iSIQKAahdSSN5CXNKBB8fLFeABYiPF5MHNiscujsMvXmuLZ8flUAmn4umch1UphkwwVnUiwUFEA='
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

    @tasks.loop(minutes=60.0)
    async def check_deals(self):
        deals = await self.load_deals_from_file()
        if not deals:
            print("No deals available to check.")
            return
        
        # Get the list of channels to notify
        self.c.execute('SELECT guild_id, channel_id FROM GameNotifyChannels')
        channels = self.c.fetchall()

        for guild_id, channel_id in channels:
            # Iterate over deals until we find one that hasn't been posted in this guild
            for deal in deals:
                title = deal.get('title')
                if not title:
                    print("Title yok, atlanıyor.")
                    continue

                new_price = deal.get('deal', {}).get('price', {}).get('amount')
                old_price = deal.get('deal', {}).get('regular', {}).get('amount')
                discount = deal.get('deal', {}).get('cut', {})
                store = deal.get('deal', {}).get('shop', {}).get('name')
                url = deal.get('deal', {}).get('url')

                if new_price is None or old_price is None or discount is None or store is None or url is None:
                    continue

                if discount < 50:
                    continue

                if not self.check_if_deal_exists_for_guild(title, guild_id):
                    now = datetime.now()
                    await self.notify_channel(guild_id, channel_id, title, new_price, old_price, discount, store, url, now)
                    break  # Move to the next guild after posting a deal
        
        # Update JSON file with remaining deals
        async with aiofiles.open(JSON_FILE, 'w') as f:
            await f.write(json.dumps(deals))

    def check_if_deal_exists_for_guild(self, title, guild_id):
        self.c.execute("SELECT 1 FROM PostedDeals WHERE title = ? AND guild_id = ?", (title, guild_id))
        result = self.c.fetchone()
        print(f"Check if deal exists: {title} for guild {guild_id}, result: {result}")
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

    async def notify_channel(self, guild_id, channel_id, title, new_price, old_price, discount, store, url, now):
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

    @tasks.loop(hours=360)  # 15 günde bir
    async def clear_old_deals(self):
        self.c.execute("DELETE FROM PostedDeals WHERE last_shared < DATETIME('now', '-15 days')")
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
