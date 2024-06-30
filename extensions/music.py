import discord
from discord.ext import commands
import yt_dlp as youtube_dl
import asyncio
from asyncio import Lock
from discord.ui import Button, View

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.queue = []
        self.current_player = None
        self.is_playing = False
        self.queue_lock = Lock()
        self.caller = None
        self.current_message = None


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
                entries = [entry for entry in entries if entry and entry.get('url')]
                return entries
            else:
                return [data]

        @classmethod
        async def create_source(cls, entry, *, loop=None):
            loop = loop or asyncio.get_event_loop()
            try:
                data = await loop.run_in_executor(None, lambda: Music.ytdl.extract_info(entry['url'], download=False))
                if 'url' in data:
                    return cls(discord.FFmpegPCMAudio(data['url'], **Music.ffmpeg_options), data=data)
                else:
                    raise YTDLError(f"Unable to extract info for URL: {entry['url']}")
            except youtube_dl.utils.DownloadError as e:
                print(f"Hata yakalandı: {e}")  # Hatanın nedenini yazdır
                if "MESAM / MSG CS" in str(e) or "unavailable" in str(e):
                    print(f"Skipping blocked video: {entry['url']}")
                    if self.queue:
                        self.queue.pop(0)  # Atla ve sıradaki videoya geç
                    else:
                        self.is_playing = False
                        await ctx.send("Sırada şarkı yok.")
                        await ctx.voice_client.disconnect()
                    return None  
                else:
                    raise 

    async def play_next(self, ctx):
        if self.queue:
            self.current_player = self.queue.pop(0)
            self.is_playing = True
            async with ctx.typing():
                source = await self.YTDLSource.create_source(self.current_player, loop=self.bot.loop)
                if source:
                    view = self.get_control_buttons(ctx)
                    ctx.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next_after_callback(ctx), self.bot.loop))
                    embed = discord.Embed(title="Şu anda Çalan Şarkı", description=self.current_player['title'], color=discord.Color.green())
                    if self.current_message:
                        await self.current_message.edit(embed=embed, view=view)
                    else:
                        self.current_message = await ctx.send(embed=embed, view=view)
                    

                else:
                    await self.play_next(ctx)  # Skip to the next song if source is None
        else:
            self.is_playing = False
            await ctx.send("Sırada şarkı yok.")
            await ctx.voice_client.disconnect()

    async def play_next_after_callback(self, ctx):
        if self.queue:
            await self.play_next(ctx)

    async def prepare_next_song(self, ctx):
        async with self.queue_lock:
            while self.queue:
                next_song = self.queue.pop(0)
                source = await self.YTDLSource.create_source(next_song, loop=self.bot.loop)
                if source:
                    self.queue.insert(0, next_song)  # Re-add the valid song to the queue
                    if not self.is_playing:
                        await self.play_next(ctx)
                    break
            else:
                self.is_playing = False


    @commands.command()
    async def cal(self, ctx, *, url_or_query):
        try:
            channel = ctx.author.voice.channel
            if ctx.voice_client is None:
                await channel.connect()
                self.caller = ctx.author
            elif ctx.voice_client.channel != channel:
                await ctx.send(f"Şu anda başka bir kanalda bulunuyorum ({ctx.voice_client.channel.name}). Müsait olunca tekrar çağırın.")
                return
        except AttributeError:
            await ctx.send("Bir ses kanalında değilsiniz.")
            return

        embed = discord.Embed(title="Şarkı Yükleniyor", description="Lütfen bekleyin...", color=discord.Color.blue())
        loading_message = await ctx.send(embed=embed)

        try:
            entries = await self.YTDLSource.from_url(url_or_query, loop=self.bot.loop, stream=True)
            if entries:
                async with self.queue_lock:
                    self.queue.extend(entries)
                if not self.is_playing:
                    await self.prepare_next_song(ctx)
                embed.title = "Şarkılar Kuyruğa Eklendi"
                embed.description = f'{len(entries)} şarkı kuyruğa eklendi.'
                await loading_message.edit(embed=embed)
            else:
                await ctx.send("Playlistte geçerli şarkı bulunamadı.")
        except YTDLError as e:
            if "MESAM / MSG CS" in e.message or "telif hakkı" in e.message:
                await ctx.send(f"Video telif hakkı nedeniyle engellenmiş: {entry['url']}")
            else:
                await ctx.send(f"Şarkı bilgisi çıkarılırken hata oluştu: {e}")
            return
    def get_control_buttons(self, ctx):
        async def stop_callback(interaction):
            await interaction.response.defer()
            if ctx.voice_client.is_playing():
                ctx.voice_client.pause()
                await interaction.followup.send("Şarkı durduruldu.", ephemeral=True)
                view = self.get_control_buttons(ctx)
                await self.current_message.edit(view=view)

        async def resume_callback(interaction):
            await interaction.response.defer()
            if ctx.voice_client.is_paused():
                ctx.voice_client.resume()
                await interaction.followup.send("Şarkı devam ediyor.", ephemeral=True)
                view = self.get_control_buttons(ctx)
                await self.current_message.edit(view=view)

        async def skip_callback(interaction):
            await interaction.response.defer()
            if ctx.voice_client.is_playing():
                ctx.voice_client.stop()
                embed = self.current_message.embeds[0]
                embed.title = "Sıradaki şarkıya geçildi."
                await self.current_message.edit(embed=embed)
                await self.play_next(ctx)  # Directly call play_next

        async def exit_callback(interaction):
            await interaction.response.defer()
            if ctx.voice_client and ctx.voice_client.is_connected():
                if ctx.author != self.caller:
                    await interaction.followup.send("Botu sadece çağıran kişi çıkartabilir.", ephemeral=True)
                    return
                await ctx.voice_client.disconnect()
                self.queue.clear()
                self.is_playing = False
                embed = discord.Embed(title="Çaycı artık özgür!", color=discord.Color.red())
                await self.current_message.edit(embed=embed)
            else:
                await ctx.send("Bot bir ses kanalında değil.")

        async def siradakiler_callback(interaction):
            await interaction.response.defer()
            if ctx.voice_client and ctx.voice_client.is_connected():
                valid_queue = [entry for entry in self.queue if entry.get('title') and entry.get('url')]
                if valid_queue:
                    pages = []
                    max_chars = 1024  # Discord embed field character limit
                    current_message = ""
                    for idx, entry in enumerate(valid_queue):
                        next_entry = f"{idx + 1}. {entry['title']}\n"
                        if len(current_message) + len(next_entry) > max_chars:
                            pages.append(current_message)
                            current_message = next_entry
                        else:
                            current_message += next_entry
                    if current_message:
                        pages.append(current_message)

                    # Pagination with buttons
                    current_page = 0
                    embed = discord.Embed(title="Sıradaki Şarkılar", description=pages[current_page], color=discord.Color.blue())

                    async def next_callback(interaction):
                        nonlocal current_page
                        if current_page < len(pages) - 1:
                            current_page += 1
                            embed.description = pages[current_page]
                            await interaction.response.edit_message(embed=embed, view=view)

                    async def previous_callback(interaction):
                        nonlocal current_page
                        if current_page > 0:
                            current_page -= 1
                            embed.description = pages[current_page]
                            await interaction.response.edit_message(embed=embed, view=view)

                    next_button = Button(label="İleri", style=discord.ButtonStyle.primary)
                    previous_button = Button(label="Geri", style=discord.ButtonStyle.primary)

                    next_button.callback = next_callback
                    previous_button.callback = previous_callback

                    view = View()
                    view.add_item(previous_button)
                    view.add_item(next_button)
                    message = await ctx.send(embed=embed, view=view)
                    await message.delete(delay=30)  # 30 saniye sonra mesajı sil
                else:
                    message = await ctx.send("Sırada şarkı yok.")
                    await message.delete(delay=30)  # 30 saniye sonra mesajı sil
            else:
                message = await ctx.send("Bot bir ses kanalında değil.")
                await message.delete(delay=30)  # 30 saniye sonra mesajı sil



        exit_button = Button(label="⏹️", style=discord.ButtonStyle.primary)
        stop_button = Button(label="⏸️", style=discord.ButtonStyle.primary)
        resume_button = Button(label="▶️", style=discord.ButtonStyle.primary)
        skip_button = Button(label="⏭️", style=discord.ButtonStyle.primary)
        siradakiler_button = Button(label="📜", style=discord.ButtonStyle.primary)

        exit_button.callback = exit_callback
        stop_button.callback = stop_callback
        resume_button.callback = resume_callback
        skip_button.callback = skip_callback
        siradakiler_button.callback = siradakiler_callback

        view = View()
        view.add_item(exit_button)
        view.add_item(stop_button)
        view.add_item(resume_button)
        view.add_item(skip_button)
        view.add_item(siradakiler_button)

        return view


    @commands.command()
    async def siradakiler(self, ctx):
        if ctx.voice_client and ctx.voice_client.is_connected():
            valid_queue = [entry for entry in self.queue if entry.get('title') and entry.get('url')]
            if valid_queue:
                pages = []
                max_chars = 1024  # Discord embed field character limit
                current_message = ""
                for idx, entry in enumerate(valid_queue):
                    next_entry = f"{idx + 1}. {entry['title']}\n"
                    if len(current_message) + len(next_entry) > max_chars:
                        pages.append(current_message)
                        current_message = next_entry
                    else:
                        current_message += next_entry
                if current_message:
                    pages.append(current_message)

                # Pagination with buttons
                current_page = 0
                embed = discord.Embed(title="Sıradaki Şarkılar", description=pages[current_page], color=discord.Color.blue())

                async def next_callback(interaction):
                    nonlocal current_page
                    if current_page < len(pages) - 1:
                        current_page += 1
                        embed.description = pages[current_page]
                        await interaction.response.edit_message(embed=embed, view=view)

                async def previous_callback(interaction):
                    nonlocal current_page
                    if current_page > 0:
                        current_page -= 1
                        embed.description = pages[current_page]
                        await interaction.response.edit_message(embed=embed, view=view)

                next_button = Button(label="➡️", style=discord.ButtonStyle.primary)
                previous_button = Button(label="⬅️", style=discord.ButtonStyle.primary)


                next_button.callback = next_callback
                previous_button.callback = previous_callback

                view = View()
                view.add_item(previous_button)
                view.add_item(next_button)
                message = await ctx.send(embed=embed, view=view)
                await message.delete(delay=30)  # 30 saniye sonra mesajı sil
            else:
                message = await ctx.send("Sırada şarkı yok.")
                await message.delete(delay=30)  # 30 saniye sonra mesajı sil
        else:
            message = await ctx.send("Bot bir ses kanalında değil.")
            await message.delete(delay=30)  # 30 saniye sonra mesajı sil

async def setup(bot):
    await bot.add_cog(Music(bot))
