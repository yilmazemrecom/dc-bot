import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.current_player = None

    youtube_dl.utils.bug_reports_message = lambda: ''

    ytdl_format_options = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0'
    }

    ffmpeg_options = {
        'options': '-vn'
    }

    ytdl = youtube_dl.YoutubeDL(ytdl_format_options)

    class YTDLSource(discord.PCMVolumeTransformer):
        def __init__(self, source, *, data, volume=0.5):
            super().__init__(source, volume)
            self.data = data
            self.title = data.get('title')
            self.url = data.get('url')

        @classmethod
        async def from_url(cls, url, *, loop=None, stream=False):
            loop = loop or asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: Music.ytdl.extract_info(url, download=not stream))

            if 'entries' in data:
                data = data['entries'][0]

            filename = data['url'] if stream else Music.ytdl.prepare_filename(data)
            return cls(discord.FFmpegPCMAudio(filename, **Music.ffmpeg_options), data=data)

    async def play_next(self, ctx):
        if self.queue:
            self.current_player = self.queue.pop(0)
            async with ctx.typing():
                ctx.voice_client.play(self.current_player, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx), ctx.bot.loop))
            await ctx.send(f'Çalınan: {self.current_player.title}')
        else:
            await ctx.send("Sırada şarkı yok.")
            await ctx.voice_client.disconnect()

    async def prepare_next_song(self, url):
        player = await self.YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
        self.queue.append(player)

    @commands.command()
    async def cal(self, ctx, *, url_or_query):
        try:
            channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await channel.connect()
            elif ctx.voice_client.channel != channel:
                await ctx.voice_client.move_to(channel)
        except:
            await ctx.send("Bir ses kanalında değilsiniz.")
            return

        # İlk şarkıyı yüklerken yerel bir ses dosyası çalın
        if not ctx.voice_client.is_playing() and not self.queue:
            ctx.voice_client.play(discord.FFmpegPCMAudio('caylar.mp3'), after=lambda e: None)
            await asyncio.sleep(5)

        await self.prepare_next_song(url_or_query)
        await ctx.send(f'Kuyruğa eklendi: {url_or_query}')

        if not ctx.voice_client.is_playing():
            await self.play_next(ctx)

    @commands.command()
    async def cik(self, ctx):
        if ctx.voice_client.is_connected():
            await ctx.voice_client.disconnect()

    @commands.command()
    async def gec(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        else:
            await ctx.send("Sırada şarkı yok.")

    @commands.command()
    async def durdur(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("Şarkı durduruldu.")
        else:
            await ctx.send("Çalan bir şarkı yok.")

    @commands.command()
    async def devam(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("Şarkı kaldığı yerden devam ediyor.")
        else:
            await ctx.send("Devam ettirilecek bir şarkı yok.")

    @commands.command()
    async def siradakiler(self, ctx):
        if self.queue:
            queue_list = "\n".join([f"{idx + 1}. {player.title}" for idx, player in enumerate(self.queue)])
            await ctx.send(f"Sıradaki şarkılar:\n{queue_list}")
        else:
            await ctx.send("Sırada şarkı yok.")

    @cal.error
    async def cal_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Lütfen bir şarkı URL'si veya ismi belirtin. Örneğin: `!cal <URL veya şarkı ismi>`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Geçerli bir URL veya şarkı ismi belirtmelisiniz.")
        else:
            await ctx.send(f"Bir hata oluştu: {error}")

async def setup(bot):
    await bot.add_cog(Music(bot))
