import discord
from discord.ext import commands
import yt_dlp as youtube_dl
from asyncio import Lock


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.current_player = None
        self.is_playing = False
        self.queue_lock = Lock()
        self.caller = None

    youtube_dl.utils.bug_reports_message = lambda: ''

    ytdl_format_options = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,  # ignoreerrors set to True to continue processing
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'auto',
        'source_address': '0.0.0.0',
        'extract_flat': 'in_playlist'
    }

    ffmpeg_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
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
                entries = data['entries']
                entries = [entry for entry in entries if entry and entry.get('url')]  # Filter out None entries and entries without url
                return entries
            else:
                return [data]

        @classmethod
        async def create_source(cls, entry, *, loop=None):
            loop = loop or asyncio.get_event_loop()
            try:
                data = await loop.run_in_executor(None, lambda: Music.ytdl.extract_info(entry['url'], download=False))
                return cls(discord.FFmpegPCMAudio(data['url'], **Music.ffmpeg_options), data=data)
            except Exception as e:
                print(f"Error creating source: {e}")
                return None

    async def play_next(self, ctx):
        if self.queue:
            self.current_player = self.queue.pop(0)
            self.is_playing = True
            async with ctx.typing():
                source = await self.YTDLSource.create_source(self.current_player, loop=self.bot.loop)
                if source:
                    ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next(ctx), ctx.bot.loop))
                    await ctx.send(f'Çalınan: {self.current_player["title"]}')
                else:
                    await self.play_next(ctx)  # Skip to the next song if source is None
        else:
            self.is_playing = False
            await ctx.send("Sırada şarkı yok.")
            await ctx.voice_client.disconnect()

    async def prepare_next_song(self, ctx):
        while self.queue:
            next_song = self.queue.pop(0)
            source = await self.YTDLSource.create_source(next_song, loop=self.bot.loop)
            if source:
                self.queue.insert(0, next_song)  # Re-add the valid song to the queue
                if not self.is_playing:
                    await self.play_next(ctx)
                break  # Exit loop when a valid song is found
            else:
                continue  # Continue to the next song if current is invalid
        else:
            self.is_playing = False

    @commands.command()
    async def cal(self, ctx, *, url_or_query):
        try:
            channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await channel.connect()
                self.caller = ctx.author  # Botu çağıran kişiyi kaydet
            elif ctx.voice_client.channel != channel:
                await ctx.send(f"Şu anda başka bir kanalda bulunuyorum ({ctx.voice_client.channel.name}). Müsait olunca tekrar çağırın.")
                return
        except:
            await ctx.send("Bir ses kanalında değilsiniz.")
            return

        await ctx.send("Şarkı yükleniyor, lütfen bekleyin...")

        try:
            entries = await self.YTDLSource.from_url(url_or_query, loop=self.bot.loop, stream=True)
            if entries:
                async with self.queue_lock:
                    self.queue.extend(entries)
                if not self.is_playing:
                    await self.prepare_next_song(ctx)
                await ctx.send(f'Kuyruğa eklendi: {url_or_query}')
            else:
                await ctx.send("Playlistte geçerli şarkı bulunamadı.")
        except Exception as e:
            await ctx.send(f"Şarkı bilgisi çıkarılırken hata oluştu. Baba üzgün...")

    @commands.command()
    async def cik(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_connected():
            if ctx.author != self.caller:
                await ctx.send("Botu sadece çağıran kişi çıkartabilir.")
                return
            await ctx.voice_client.disconnect()
            self.queue.clear()
            self.is_playing = False
            await ctx.send("Baba tahliye...")
        else:
            await ctx.send("Bot bir ses kanalında değil.")


    @commands.command()
    async def gec(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_connected():
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
                await self.play_next(ctx)
            else:
                await ctx.send("Sırada şarkı yok.")
        else:
            await ctx.send("Bot bir ses kanalında değil.")

    @commands.command()
    async def durdur(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_connected():
            if ctx.voice_client.is_playing():
                ctx.voice_client.pause()
                await ctx.send("Şarkı durduruldu.")
            else:
                await ctx.send("Çalan bir şarkı yok.")
        else:
            await ctx.send("Bot bir ses kanalında değil.")

    @commands.command()
    async def devam(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_connected():
            if ctx.voice_client.is_paused():
                ctx.voice_client.resume()
                await ctx.send("Şarkı kaldığı yerden devam ediyor.")
            else:
                await ctx.send("Devam ettirilecek bir şarkı yok.")
        else:
            await ctx.send("Bot bir ses kanalında değil.")

    @commands.command()
    async def siradakiler(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_connected():
            valid_queue = [entry for entry in self.queue if entry.get('title') and entry.get('url')]
            if valid_queue:
                queue_list = "\n".join([f"{idx + 1}. {entry['title']}" for idx, entry in enumerate(valid_queue)])
                await ctx.send(f"Sıradaki şarkılar:\n{queue_list}")
            else:
                await ctx.send("Sırada şarkı yok.")
        else:
            await ctx.send("Bot bir ses kanalında değil.")

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
