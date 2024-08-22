from config import API_KEY
import aiohttp
import discord
from discord.ext import commands, tasks
import aiosqlite
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
        self.daily_json_reset.start()
        self.bot.loop.create_task(self.init_db())

    async def init_db(self):
        self.conn = await aiosqlite.connect('database/indirim.db')
        self.c = await self.conn.cursor()
        await self.c.execute('''
            CREATE TABLE IF NOT EXISTS GameNotifyChannels (
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
        ''')
        await self.c.execute('''
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
        await self.conn.commit()

    def cog_unload(self):
        self.check_deals.cancel()
        self.clear_old_deals.cancel()
        self.daily_json_reset.cancel()
        self.conn.close()

    async def cog_check(self, ctx):
        return ctx.author.guild_permissions.administrator

    @discord.app_commands.command(name="oyunbildirimac", description="Belirtilen kanalda oyun bildirimlerini açar")
    @commands.has_permissions(administrator=True)
    async def oyunbildirimac(self, interaction: discord.Interaction, kanal: discord.TextChannel):
        await self.c.execute('INSERT OR REPLACE INTO GameNotifyChannels (guild_id, channel_id) VALUES (?, ?)',
                             (interaction.guild.id, kanal.id))
        await self.conn.commit()
        await interaction.response.send_message(f"İndirimdeki oyunlar, saatte bir {kanal.mention} kanalında paylaşılacak.", ephemeral=True)

    @discord.app_commands.command(name="oyunbildirimkapat", description="Belirtilen kanalda oyun bildirimlerini kapatır")
    @commands.has_permissions(administrator=True)
    async def oyunbildirimkapat(self, interaction: discord.Interaction):
        await self.c.execute('DELETE FROM GameNotifyChannels WHERE guild_id = ?', (interaction.guild.id,))
        await self.conn.commit()
        await interaction.response.send_message(f"{interaction.channel.mention} kanalında oyun bildirimleri kapatıldı.", ephemeral=True)

    async def load_deals_from_api(self):
        params = {
            'key': API_KEY,
            'country': 'TR',
            'limit': 500,
            'sort': 'rank',
            'mature': 'false',
            'filter': 'N4IgxgrgLiBcoFsCWA7OBWADAGhAghgB5wCMmmAvrgCYBOCcA2iQGzYskC6uADgDb4oAMwD29JiWwAmbAGZuIKAE8eAUwlyFytQDkRMWIwDs2ABwKU+gAq1VAeVrVVtOFFoRVuAM5RV+BFbOYHCIqBg4eESk5FR4qlD4AMK0SFBIwfB4YbAsEQTEsGSUuAjx+ACqXs4hWWiwWCVRhTHevv6JIhAoBqF1WOSNBSgQfHyxXgAWIjxeTBzYrHLo7DIALOa4tnx+VQCafi6ZyHVSmGSDcKdSLBQUQA=='
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    deals = data.get('list', [])
                    if not deals:
                        print("API'den oyun verisi alınamadı.")
                        return
                    async with aiofiles.open(JSON_FILE, 'w') as f:
                        await f.write(json.dumps(deals))
                    print(f"{len(deals)} indirimli oyun JSON dosyasına kaydedildi.")
        except aiohttp.ClientError as e:
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
        await self.c.execute('SELECT guild_id, channel_id FROM GameNotifyChannels')
        channels = await self.c.fetchall()

        for guild_id, channel_id in channels:
            try:
                for deal in deals:
                    title = deal.get('title')
                    if not title:
                        print(f"Title yok, atlanıyor. Channel ID: {channel_id}")
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

                    if not await self.check_if_deal_exists_for_guild(title, guild_id):
                        now = datetime.now()
                        await self.notify_channel(guild_id, channel_id, title, new_price, old_price, discount, store, url, now)
                        break  # Move to the next guild after posting a deal
            except Exception as e:
                print(f"Error processing guild_id: {guild_id}, channel_id: {channel_id}, error: {e}")
        
        # Update JSON file with remaining deals
        async with aiofiles.open(JSON_FILE, 'w') as f:
            await f.write(json.dumps(deals))

    @tasks.loop(hours=24)  # Günlük olarak JSON dosyasını yenileme
    async def daily_json_reset(self):
        print("Günlük JSON sıfırlanıyor...")
        if os.path.exists(JSON_FILE):
            os.remove(JSON_FILE)
        await self.load_deals_from_api()
        print("JSON dosyası sıfırlandı ve yeniden dolduruldu.")

    @daily_json_reset.before_loop
    async def before_daily_json_reset(self):
        await self.bot.wait_until_ready()
        # Günlük sıfırlamanın zamanını ayarlamak için
        now = datetime.now()
        next_run = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await discord.utils.sleep_until(next_run)

    async def check_if_deal_exists_for_guild(self, title, guild_id):
        await self.c.execute("SELECT 1 FROM PostedDeals WHERE title = ? AND guild_id = ?", (title, guild_id))
        result = await self.c.fetchone()
        return result is not None

    async def save_deal(self, title, guild_id, channel_id, new_price, old_price, discount, store, url, now):
        try:
            await self.c.execute('''
                INSERT INTO PostedDeals (title, guild_id, channel_id, new_price, old_price, discount, store, url, last_shared)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, guild_id, channel_id, new_price, old_price, discount, store, url, now))
            await self.conn.commit()
            print(f"Saved deal {title} to DB for guild {guild_id}, channel {channel_id}")
        except aiosqlite.IntegrityError:
            print(f"Deal {title} already exists in DB for guild {guild_id}, channel {channel_id}")

    async def notify_channel(self, guild_id, channel_id, title, new_price, old_price, discount, store, url, now):
        try:
            channel = self.bot.get_channel(int(channel_id))

            profit = old_price - new_price
            profit = round(profit, 2)
            title_length = len(title)
            title_line = "━" * title_length

            if channel:
                message = (
                    f"**━━━━━━━━━━━━━{title_line}**\n"
                    f"## 🎮 **İndirim: {title}!**\n"
                    f"**━━━━━━━━━━━━━{title_line}**\n"
                    f"💰 **Yeni Fiyat:** `🔻 {new_price} ₺`\n"
                    f"🔖 **Eski Fiyat:** `🔺 {old_price} ₺`\n"
                    f"📉 **İndirim:** `%{discount}`\n"
                    f"💸 **Kâr** `{profit} ₺`\n"
                    f"🏪 **Mağaza:** `{store}`\n"
                    f"👉 [{title} Oyun Linki]({url})\n"

                )

                await channel.send(message)
                await self.save_deal(title, guild_id, channel_id, new_price, old_price, discount, store, url, now)

            else:
                print(f"Kanal bulunamadı: {channel_id} for guild: {guild_id}")
        except Exception as e:
            print(f"Error notifying channel: {channel_id} for guild: {guild_id}, error: {e}")

    @tasks.loop(hours=360)  # 15 günde bir
    async def clear_old_deals(self):
        await self.c.execute("DELETE FROM PostedDeals WHERE last_shared < DATETIME('now', '-15 days')")
        await self.conn.commit()
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
