from config import OMDB_API_KEY
import aiohttp
import discord
from discord.ext import commands, tasks
import aiosqlite
import random

OMDB_API_URL = 'http://www.omdbapi.com/'

class FilmBildirim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.daily_movie_recommendation.start()
        self.bot.loop.create_task(self.init_db())

    async def init_db(self):
        self.conn = await aiosqlite.connect('database/film.db')
        self.c = await self.conn.cursor()
        await self.c.execute('''
            CREATE TABLE IF NOT EXISTS FilmNotifyChannels (
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
        ''')
        await self.conn.commit()

    def cog_unload(self):
        self.daily_movie_recommendation.cancel()
        self.conn.close()

    @discord.app_commands.command(name="filmbildirimac", description="Belirtilen kanalda film bildirimlerini açar")
    async def slash_filmbildirimac(self, interaction: discord.Interaction, kanal: discord.TextChannel):
        await self.c.execute('INSERT OR REPLACE INTO FilmNotifyChannels (guild_id, channel_id) VALUES (?, ?)',
                             (interaction.guild.id, kanal.id))
        await self.conn.commit()
        await interaction.response.send_message(f"Film önerileri, günde bir defa {kanal.mention} kanalında paylaşılacak.", ephemeral=True)

    @discord.app_commands.command(name="filmbildirimkapat", description="Belirtilen kanalda film bildirimlerini kapatır")
    async def slash_filmbildirimkapat(self, interaction: discord.Interaction):
        await self.c.execute('DELETE FROM FilmNotifyChannels WHERE guild_id = ?', (interaction.guild.id,))
        await self.conn.commit()
        await interaction.response.send_message(f"{interaction.channel.mention} kanalında film bildirimleri kapatıldı.", ephemeral=True)



    async def fetch_movie_details(self, imdb_id):
        params = {
            'apikey': OMDB_API_KEY,
            'i': imdb_id,
            'r': 'json'
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(OMDB_API_URL, params=params) as response:
                    response.raise_for_status()
                    return await response.json()
        except aiohttp.ClientError as e:
            print(f"API isteğinde hata oluştu: {e}")
            return None

    async def get_top_rated_movie(self):
        params = {
            'apikey': OMDB_API_KEY,
            's': 'movie',  # Geniş bir arama terimi kullanarak genel bir arama yapıyoruz
            'type': 'movie',
            'r': 'json',
            'page': random.randint(1, 100)  # Rastgele bir sayfa seçiyoruz ki her seferinde farklı sonuçlar elde edelim
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(OMDB_API_URL, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    print(f"OMDb API Yanıtı: {data}")  # API yanıtını yazdır
                    if 'Search' not in data:
                        print("API yanıtında 'Search' anahtarı yok.")
                        return None
                    
                    for movie in data['Search']:
                        details = await self.fetch_movie_details(movie['imdbID'])
                        if details:
                            print(f"Film Detayları: {details}")  # Film detaylarını yazdır
                        if details and 'imdbRating' in details and float(details['imdbRating']) >= 8.0 and float(details['Year'])>=2010:
                            return details
                        
                    
                    print("IMDb puanı 7 ve üzeri film bulunamadı.")
                    return None
        except aiohttp.ClientError as e:
            print(f"API isteğinde hata oluştu: {e}")
            return None

    @tasks.loop(hours=24)
    async def daily_movie_recommendation(self):
        await self.c.execute('SELECT guild_id, channel_id FROM FilmNotifyChannels')
        channels = await self.c.fetchall()

        for guild_id, channel_id in channels:
            try:
                movie = await self.get_top_rated_movie()
                if movie:
                    print(f"Önerilen Film: {movie}")  # Önerilen filmi yazdır
                    channel = self.bot.get_channel(int(channel_id))
                    if channel:
                        try:
                            embed = discord.Embed(
                                title=movie['Title'],
                                description=f"Yıl: {movie['Year']}\nIMDb: {movie['imdbRating']}\nTür: {movie['Genre']}",
                                color=discord.Color.blue()
                            )
                            embed.set_image(url=movie['Poster'])
                            embed.set_footer(text="Bugün için film önerisi")
                            await channel.send(embed=embed)
                            print(f"Mesaj gönderildi: {movie['Title']}")  # Mesajın gönderildiğini yazdır
                        except discord.DiscordException as e:
                            print(f"Mesaj gönderiminde hata oluştu: {e}")
                    else:
                        print(f"Kanal bulunamadı: {channel_id} for guild: {guild_id}")
            except Exception as e:
                print(f"Error processing guild_id: {guild_id}, channel_id: {channel_id}, error: {e}")

    @daily_movie_recommendation.before_loop
    async def before_daily_movie_recommendation(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(FilmBildirim(bot))
