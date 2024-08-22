import discord
from discord.ext import commands, tasks
import feedparser
import aiosqlite
from datetime import datetime
from html import unescape
import re

RSS_FEEDS = {
    'genel hurriyet': 'https://www.hurriyet.com.tr/rss/anasayfa',
    'genel haberturk': 'https://www.haberturk.com/rss',
    'genel ntv': 'https://www.ntv.com.tr/gundem.rss',
    'genel anadolu_ajansi': 'https://www.aa.com.tr/tr/rss/default?cat=gundem',
    'genel bbc_world': 'http://feeds.bbci.co.uk/news/world/rss.xml',
    'genel cnn_world': 'http://rss.cnn.com/rss/edition_world.rss',
    'teknoloji webtekno': 'https://www.webtekno.com/rss.xml',
    'teknoloji shiftdelete': 'https://shiftdelete.net/feed',
    'teknoloji donanimhaber': 'https://www.donanimhaber.com/rss/tum/',
    'oyun shiftdelete': 'https://shiftdelete.net/oyun/feed',
}

def clean_html(raw_html):
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', raw_html)
    return unescape(cleantext)

class Haberbildirim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_news.start()
        self.bot.loop.create_task(self.init_db())

    async def init_db(self):
        self.conn = await aiosqlite.connect('database/haber.db')
        self.c = await self.conn.cursor()
        await self.c.execute('''
            CREATE TABLE IF NOT EXISTS NewsNotifyChannels (
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                source TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id, source)
            )
        ''')
        await self.c.execute('''
            CREATE TABLE IF NOT EXISTS PostedNews (
                title TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                source TEXT NOT NULL,
                last_shared TIMESTAMP NOT NULL,
                PRIMARY KEY (title, guild_id, channel_id)
            )
        ''')
        await self.conn.commit()

    def cog_unload(self):
        self.check_news.cancel()
        self.conn.close()

    async def cog_check(self, ctx):
        return ctx.author.guild_permissions.administrator

    @discord.app_commands.command(name="haberbildirimac", description="Belirtilen kanalda haber bildirimlerini açar")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def haberbildirimac(self, interaction: discord.Interaction, kanal: discord.TextChannel, kaynak: str):
        await self.c.execute('INSERT OR REPLACE INTO NewsNotifyChannels (guild_id, channel_id, source) VALUES (?, ?, ?)',
                             (interaction.guild.id, kanal.id, kaynak))
        await self.conn.commit()
        await interaction.response.send_message(f"{kaynak} haberleri, saatte bir {kanal.mention} kanalında paylaşılacak.", ephemeral=True)

    @discord.app_commands.command(name="haberbildirimkapat", description="Belirtilen kanalda haber bildirimlerini kapatır")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def haberbildirimkapat(self, interaction: discord.Interaction, kanal: discord.TextChannel, kaynak: str):
        await self.c.execute('DELETE FROM NewsNotifyChannels WHERE guild_id = ? AND channel_id = ? AND source = ?',
                             (interaction.guild.id, kanal.id, kaynak))
        await self.conn.commit()
        await interaction.response.send_message(f"{kaynak} haber kaynağı, {kanal.mention} kanalında kapatıldı.", ephemeral=True)

    @haberbildirimac.autocomplete("kaynak")
    async def kaynak_autocomplete(self, interaction: discord.Interaction, current: str):
        return [
            discord.app_commands.Choice(name=key, value=key)
            for key in RSS_FEEDS.keys() if current.lower() in key.lower()
        ]

    async def get_latest_news(self, source):
        url = RSS_FEEDS.get(source)
        if not url:
            return None
        feed = feedparser.parse(url)
        if feed.entries:
            entry = feed.entries[0]  # Sadece ilk haberi alıyoruz
            summary = clean_html(entry.summary) if 'summary' in entry else "Detaylar için tıklayın."
            image = entry.get('media_thumbnail', [{'url': None}])[0]['url'] if 'media_thumbnail' in entry else None
            return {
                'title': entry.title,
                'link': entry.link,
                'summary': summary,
                'image': image,
                'source': source,
            }
        return None

    @tasks.loop(minutes=60.0)
    async def check_news(self):
        await self.c.execute('SELECT guild_id, channel_id, source FROM NewsNotifyChannels')
        channels = await self.c.fetchall()

        for guild_id, channel_id, source in channels:
            news_item = await self.get_latest_news(source)
            if news_item:
                if not await self.check_if_news_posted(news_item['title'], guild_id, channel_id):
                    await self.notify_channel(guild_id, channel_id, news_item['title'], news_item['link'], news_item['summary'], news_item['image'], news_item['source'])
                    await self.mark_news_as_posted(news_item['title'], guild_id, channel_id, source)

    async def check_if_news_posted(self, title, guild_id, channel_id):
        await self.c.execute("SELECT 1 FROM PostedNews WHERE title = ? AND guild_id = ? AND channel_id = ?", (title, guild_id, channel_id))
        result = await self.c.fetchone()
        return result is not None

    async def mark_news_as_posted(self, title, guild_id, channel_id, source):
        now = datetime.now()
        await self.c.execute('INSERT INTO PostedNews (title, guild_id, channel_id, source, last_shared) VALUES (?, ?, ?, ?, ?)',
                             (title, guild_id, channel_id, source, now))
        await self.conn.commit()

    async def notify_channel(self, guild_id, channel_id, title, link, summary, image, source):
        try:
            channel = self.bot.get_channel(int(channel_id))
            if channel:
                # Renkli Embed Mesajı
                embed = discord.Embed(
                    title=title,
                    description=summary,
                    color=discord.Color.from_rgb(0, 153, 255),  # Mavi tonunda bir renk
                    url=link
                )
                embed.set_author(name=source.capitalize())
                if image:
                    embed.set_image(url=image)
                embed.add_field(name="Detaylar için tıkla", value=f"[Haberin Devamı]({link})", inline=False)
                
                await channel.send(embed=embed)
        except Exception as e:
            print(f"Error notifying channel: {channel_id} for guild: {guild_id}, error: {e}")

    @check_news.before_loop
    async def before_check_news(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(Haberbildirim(bot))
