import discord
from discord.ext import commands, tasks
import yt_dlp as youtube_dl
import asyncio
from asyncio import Lock
from discord.ui import Button, View
import datetime

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.guild_states = {}
        self.check_voice_channel.start()


    def get_guild_state(self, guild_id):
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = {
                "queue": [],
                "current_player": None,
                "is_playing": False,
                "queue_lock": Lock(),
                "caller": None,
                "current_message": None
            }
        return self.guild_states[guild_id]

    youtube_dl.utils.bug_reports_message = lambda: ''

    ytdl_format_options = {
        'format': 'bestaudio/best',
        'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
        'restrictfilenames': True,
        'nocertificate': True,
        'ignoreerrors': True,
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
            self.thumbnail = data.get('thumbnail')

        @classmethod
        async def from_url(cls, url, *, loop=None, stream=False):
            loop = loop or asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: Music.ytdl.extract_info(url, download=not stream))

            if not data:
                return None

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
                if not data:
                    return None
                if 'url' in data:
                    return cls(discord.FFmpegPCMAudio(data['url'], **Music.ffmpeg_options), data=data)
                else:
                    raise Exception(f"Unable to extract info for URL: {entry['url']}")
            except youtube_dl.utils.DownloadError as e:
                print(f"Hata yakalandı: {e}")
                if "MESAM / MSG CS" in str(e) or "unavailable" in str(e):
                    print(f"Skipping blocked video: {entry['url']}")
                    return None  
                else:
                    raise 

    async def play_next(self, interaction):
        state = self.get_guild_state(interaction.guild.id)
        if state["queue"]:
            state["current_player"] = state["queue"].pop(0)
            state["is_playing"] = True
            async with interaction.channel.typing():
                source = await self.YTDLSource.create_source(state["current_player"], loop=self.bot.loop)
                if source:
                    view = self.get_control_buttons(interaction)
                    interaction.guild.voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(self.play_next_after_callback(interaction), self.bot.loop))
                    embed = discord.Embed(title="Şu anda Çalan Şarkı", description=state["current_player"]['title'], color=discord.Color.green())
                    embed.set_thumbnail(url=source.thumbnail)
                    if state["current_message"]:
                        await state["current_message"].edit(embed=embed, view=view)
                    else:
                        state["current_message"] = await interaction.channel.send(embed=embed, view=view)
                else:
                    await self.play_next(interaction)  # Skip to the next song if source is None
        else:
            state["is_playing"] = False
            await interaction.guild.voice_client.disconnect()
            if state["current_message"]:
                await state["current_message"].delete()
                state["current_message"] = None

    async def play_next_after_callback(self, interaction):
        await self.play_next(interaction)


    async def prepare_next_song(self, interaction):
        state = self.get_guild_state(interaction.guild.id)
        async with state["queue_lock"]:
            while state["queue"]:
                next_song = state["queue"].pop(0)
                source = await self.YTDLSource.create_source(next_song, loop=self.bot.loop)
                if source:
                    state["queue"].insert(0, next_song)  # Re-add the valid song to the queue
                    if not state["is_playing"]:
                        await self.play_next(interaction)
                    break
            else:
                state["is_playing"] = False

    @discord.app_commands.command(name="cal", description="Şarkı çalar")
    async def slash_cal(self, interaction: discord.Interaction, sarki: str):
        state = self.get_guild_state(interaction.guild.id)
        try:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                await channel.connect()
                state["caller"] = interaction.user
            elif interaction.guild.voice_client.channel != channel:
                await interaction.response.send_message(f"Şu anda başka bir kanalda bulunuyorum ({interaction.guild.voice_client.channel.name}). Müsait olunca tekrar çağırın.", ephemeral=True)
                return
        except AttributeError:
            await interaction.response.send_message("Bir ses kanalında değilsiniz.", ephemeral=True)
            return

        embed = discord.Embed(title="Şarkı Yükleniyor", description="Lütfen bekleyin...", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
        loading_message = await interaction.original_response()
        await loading_message.delete(delay=10)

        try:
            entries = await self.YTDLSource.from_url(sarki, loop=self.bot.loop, stream=True)
            if entries:
                async with state["queue_lock"]:
                    state["queue"].extend(entries)
                if not state["is_playing"]:
                    await self.prepare_next_song(interaction)
                embed = discord.Embed(title="Şarkılar Kuyruğa Eklendi", description=f"{len(entries)} şarkı kuyruğa eklendi.", color=discord.Color.blue())
                loadingmess= await loading_message.edit(embed=embed)
                await loadingmess.delete(delay=10)
            else:
                await interaction.followup.send("Playlistte geçerli şarkı bulunamadı.", ephemeral=True)
                state["queue"].clear()
                state["is_playing"] = False
                await state["current_message"].delete()
                state["current_message"] = None
                await interaction.guild.voice_client.disconnect()

        except Exception as e:
            print(f"Şarkı bilgisi çıkarılırken hata oluştu: {e}")
            return

    def get_control_buttons(self, interaction):
        view = discord.ui.View(timeout=600)
        state = self.get_guild_state(interaction.guild.id)
        async def stop_callback(interaction):
            await interaction.response.defer()
            if interaction.guild.voice_client.is_playing():
                interaction.guild.voice_client.pause()
                await interaction.followup.send("Şarkı durduruldu.", ephemeral=True)
                view = self.get_control_buttons(interaction)
                await state["current_message"].edit(view=view)
            elif interaction.guild.voice_client.is_paused():
                interaction.guild.voice_client.resume()
                await interaction.followup.send("Şarkı devam ediyor.", ephemeral=True)
                view = self.get_control_buttons(interaction)
                await state["current_message"].edit(view=view)


        async def resume_callback(interaction):
            await interaction.response.defer()
            if interaction.guild.voice_client.is_paused():
                interaction.guild.voice_client.resume()
                await interaction.followup.send("Şarkı devam ediyor.", ephemeral=True)
                view = self.get_control_buttons(interaction)
                await state["current_message"].edit(view=view)

        async def skip_callback(interaction):
            await interaction.response.defer()
            if interaction.guild.voice_client.is_playing():
                interaction.guild.voice_client.stop()
                embed = state["current_message"].embeds[0]
                embed.title = "Sıradaki şarkıya geçildi."
                await state["current_message"].edit(embed=embed)

        async def exit_callback(interaction):
            await interaction.response.defer()
            if interaction.guild.voice_client and interaction.guild.voice_client.is_connected():
                if interaction.user != state["caller"]:
                    await interaction.followup.send("Botu sadece çağıran kişi çıkartabilir.", ephemeral=True)
                    return
                await interaction.guild.voice_client.disconnect()
                state["queue"].clear()
                state["is_playing"] = False
                await state["current_message"].delete()
                state["current_message"] = None
                embed = discord.Embed(title="Çaycı Artık Özgür!", description="Bot ses kanalından çıkartıldı.", color=discord.Color.red())
                message = await interaction.channel.send(embed=embed)
            else:
                await interaction.channel.send("Bot bir ses kanalında değil.")

        async def siradakiler_callback(interaction):
            await interaction.response.defer()
            if interaction.guild.voice_client and interaction.guild.voice_client.is_connected():
                valid_queue = [entry for entry in state["queue"] if entry.get('title') and entry.get('url')]
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
                    message = await interaction.channel.send(embed=embed, view=view)
                    await message.delete(delay=30)  # 30 saniye sonra mesajı sil
                else:
                    message = await interaction.channel.send("Sırada şarkı yok.")
                    await message.delete(delay=30)  # 30 saniye sonra mesajı sil
            else:
                message = await interaction.channel.send("Bot bir ses kanalında değil.")
                await message.delete(delay=30)  # 30 saniye sonra mesajı sil

        exit_button = Button(label="", emoji="⏹️", style=discord.ButtonStyle.primary)
        stop_button = Button(label="", emoji="⏯️", style=discord.ButtonStyle.primary)
        skip_button = Button(label="", emoji="⏭️", style=discord.ButtonStyle.primary)
        siradakiler_button = Button(label="", emoji="📋", style=discord.ButtonStyle.primary)

        exit_button.callback = exit_callback
        stop_button.callback = stop_callback

        skip_button.callback = skip_callback
        siradakiler_button.callback = siradakiler_callback

        view = View()
        view.add_item(exit_button)
        view.add_item(stop_button)

        view.add_item(skip_button)
        view.add_item(siradakiler_button)

        return view

    @discord.app_commands.command(name="siradakiler", description="Sıradaki şarkıları gösterir")
    async def slash_siradakiler(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if interaction.guild.voice_client and interaction.guild.voice_client.is_connected():
            valid_queue = [entry for entry in state["queue"] if entry.get('title') and entry.get('url')]
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
                    message = await interaction.response.send_message(embed=embed, view=view)
                    await message.delete(delay=30)  
            else:
                message = await interaction.response.send_message("Sırada şarkı yok.")
                await message.delete(delay=30) 
        else:
            message = await interaction.response.send_message("Bot bir ses kanalında değil.")
            await message.delete(delay=30) 


    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if not member.bot:
            return

        state = self.get_guild_state(member.guild.id)
        if before.channel is not None and after.channel is None:
            state["queue"].clear()
            state["is_playing"] = False
            if state["current_message"]:
                await state["current_message"].delete()
                state["current_message"] = None
            if member.guild.voice_client:
                await member.guild.voice_client.disconnect()

    def get_voice_state(self, guild):
        if guild.voice_client:
            return guild.voice_client.channel
        return None

    @tasks.loop(minutes=1.0)
    async def check_voice_channel(self):
        for guild in self.bot.guilds:
            voice_state = self.get_voice_state(guild)
            if voice_state and len(voice_state.members) == 1:
                await asyncio.sleep(600)  # 10 dakika bekle
                if len(voice_state.members) == 1:  # Tekrar kontrol et
                    await guild.voice_client.disconnect()
                    state = self.get_guild_state(guild.id)
                    state["queue"].clear()
                    state["is_playing"] = False
                    if state["current_message"]:
                        await state["current_message"].delete()
                        state["current_message"] = None

    @check_voice_channel.before_loop
    async def before_check_voice_channel(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            state = self.get_guild_state(interaction.guild.id)
            if state["current_message"] and interaction.message.id == state["current_message"].id:
                await interaction.response.defer()
                # Refresh the message to keep buttons active
                embed = state["current_message"].embeds[0]
                view = self.get_control_buttons(interaction)
                await state["current_message"].edit(embed=embed, view=view)



async def setup(bot):
    await bot.add_cog(Music(bot))
