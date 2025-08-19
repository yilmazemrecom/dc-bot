import discord
from discord.ext import commands, tasks
import yt_dlp as youtube_dl
import asyncio
from asyncio import Lock
from discord.ui import Button, View
import datetime
import aiosqlite
from typing import Optional
from discord import app_commands
import random

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
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -probesize 32 -analyzeduration 0',
        'options': '-vn -bufsize 512k -maxrate 128k'
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
                    await self.prepare_next_song(interaction)
        else:
            state["is_playing"] = False
            await interaction.guild.voice_client.disconnect()
            if state["current_message"]:
                await state["current_message"].delete()
                state["current_message"] = None

    async def play_next_after_callback(self, interaction):
        await self.play_next(interaction)

    async def button_queue_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if not interaction.guild.voice_client:
            await interaction.response.send_message("Bot bir ses kanalında değil!", ephemeral=True)
            return
        if not state["queue"]:
            await interaction.response.send_message("Sırada şarkı yok!", ephemeral=True)
            return
        embed = discord.Embed(title="🎵 Çalma Listesi", color=discord.Color.blue())
        if state["current_player"]:
            embed.add_field(name="Şimdi Çalıyor", value=f"▶️ {state['current_player']['title']}", inline=False)
        queue_text = ""
        for idx, song in enumerate(state["queue"], 1):
            queue_text += f"{idx}. {song['title']}\n"
            if idx % 10 == 0:
                embed.add_field(name=f"Sıradaki Şarkılar ({idx-9}-{idx})", value=queue_text, inline=False)
                queue_text = ""
        if queue_text:
            embed.add_field(name="Sıradaki Şarkılar", value=queue_text, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def button_pause_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("⏸️ Şarkı duraklatıldı", ephemeral=True)
        elif interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("▶️ Şarkı devam ediyor", ephemeral=True)
        await self.update_player_message(interaction, state)

    async def button_skip_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if interaction.guild.voice_client:
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⏭️ Şarkı geçildi", ephemeral=True)
        await self.update_player_message(interaction, state)

    async def button_stop_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if interaction.guild.voice_client:
            state["queue"].clear()
            interaction.guild.voice_client.stop()
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("⏹️ Müzik durduruldu", ephemeral=True)
        await self.update_player_message(interaction, state)

    async def button_favorite_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if not interaction.guild.voice_client or not state["is_playing"]:
            await interaction.response.send_message("Şu anda çalan şarkı yok!", ephemeral=True)
            return
        if not state["current_player"]:
            await interaction.response.send_message("Şu anda çalan şarkı yok!", ephemeral=True)
            return
        current_song = state["current_player"]
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        try:
            await interaction.response.defer(ephemeral=True)
            if await self.is_favorite(user_id, current_song['url']):
                await self.remove_favorite(user_id, current_song['url'])
                await interaction.followup.send("💔 Şarkı favorilerden çıkarıldı!", ephemeral=True)
            else:
                await self.add_favorite(user_id, guild_id, current_song['title'], current_song['url'])
                await interaction.followup.send("❤️ Şarkı favorilere eklendi!", ephemeral=True)
            embed = discord.Embed(
                title="🎵 Şimdi Çalıyor",
                description=f"[{current_song['title']}]({current_song['url']})",
                color=discord.Color.blue()
            )
            if 'thumbnail' in current_song:
                embed.set_thumbnail(url=current_song['thumbnail'])
            view = View(timeout=None)

            pause_button = Button(style=discord.ButtonStyle.primary, emoji="⏯️", custom_id="pause")
            pause_button.callback = lambda i: self.button_pause_callback(i)
            view.add_item(pause_button)
            skip_button = Button(style=discord.ButtonStyle.primary, emoji="⏭️", custom_id="skip")
            skip_button.callback = lambda i: self.button_skip_callback(i)
            view.add_item(skip_button)
            stop_button = Button(style=discord.ButtonStyle.danger, emoji="⏹️", custom_id="stop")
            stop_button.callback = lambda i: self.button_stop_callback(i)
            view.add_item(stop_button)
            queue_button = Button(style=discord.ButtonStyle.secondary, emoji="📜", custom_id="queue")
            queue_button.callback = lambda i: self.button_queue_callback(i)
            view.add_item(queue_button)
            favorite_button = Button(style=discord.ButtonStyle.success, emoji="❤️", custom_id="favorite")
            favorite_button.callback = lambda i: self.button_favorite_callback(i)
            view.add_item(favorite_button)
            if state["current_message"]:
                await state["current_message"].edit(embed=embed, view=view)
        except Exception as e:
            print(f"Favori işlemi hatası: {e}")
            try:
                await interaction.followup.send("Bir hata oluştu.", ephemeral=True)
            except:
                pass



    async def prepare_next_song(self, interaction):
        state = self.get_guild_state(interaction.guild.id)
        async with state["queue_lock"]:
            while state["queue"]:
                next_song = state["queue"].pop(0)
                source = await self.YTDLSource.create_source(next_song, loop=self.bot.loop)
                if source:
                    state["queue"].insert(0, next_song)  # Re-add the valid song to the queue
                    state["is_playing"] = True
                    await self.play_next(interaction)
                    break
            else:
                state["is_playing"] = False

    @discord.app_commands.command(name="cal", description="Şarkı çalar")
    @discord.app_commands.describe(sarki="Şarkı adı veya URL (Sadece YouTube linki giriniz)")
    async def slash_cal(self, interaction: discord.Interaction, sarki: str):
        state = self.get_guild_state(interaction.guild.id)
        try:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                # Voice connection with user-friendly retry
                connection_embed = discord.Embed(
                    title="🎵 Ses Kanalına Bağlanıyor...", 
                    description="Lütfen bekleyin, bağlantı kuruluyor...", 
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=connection_embed)
                
                for attempt in range(3):
                    try:
                        await asyncio.wait_for(channel.connect(timeout=30.0), timeout=45.0)
                        state["caller"] = interaction.user
                        break
                    except (asyncio.TimeoutError, discord.errors.ConnectionClosed) as e:
                        if attempt == 2:
                            # Final failure message
                            error_embed = discord.Embed(
                                title="⚠️ Müzik Sistemi Hakkında",
                                description="Sunucumuz uygun fiyatlı olduğundan dolayı Türkiye'de bulunuyor ve Discord yasaklarından ötürü ping sorunu yaşıyoruz.\n\n"
                                           "Sunucu kiralamak pahalı olduğundan müzik için sorunlar çıkabiliyor. 😅\n\n"
                                           "**Çözüm önerileri:**\n"
                                           "• Biraz bekleyip tekrar deneyin\n"
                                           "• Bazen 2-3 deneme gerekebilir\n"
                                           "• Anlayışınız için teşekkürler! 🙏",
                                color=discord.Color.orange()
                            )
                            error_embed.set_footer(text="Daha iyi hizmet verebilmek için çalışıyoruz ❤️")
                            await interaction.edit_original_response(embed=error_embed)
                            return
                        
                        # Show retry attempt
                        retry_embed = discord.Embed(
                            title="🔄 Yeniden Deneniyor...",
                            description=f"Bağlantı kurulamadı, deneme {attempt + 2}/3...",
                            color=discord.Color.yellow()
                        )
                        await interaction.edit_original_response(embed=retry_embed)
                        await asyncio.sleep(3)
            elif interaction.guild.voice_client.channel != channel:
                await interaction.response.send_message(f"Şu anda başka bir kanalda bulunuyorum ({interaction.guild.voice_client.channel.name}). Müsait olunca tekrar çağırın.", ephemeral=True)
                return
        except AttributeError:
            await interaction.response.send_message("Bir ses kanalında değilsiniz.", ephemeral=True)
            return

        # Bağlantı başarılı ise loading mesajına geç
        if not hasattr(interaction, '_response_sent') or not interaction._response_sent:
            embed = discord.Embed(title="Şarkı Yükleniyor", description="Lütfen bekleyin...", color=discord.Color.blue())
            await interaction.response.send_message(embed=embed)
        else:
            # Bağlantı mesajını loading'e güncelle
            embed = discord.Embed(title="✅ Bağlandı! Şarkı Yükleniyor...", description="Lütfen bekleyin...", color=discord.Color.green())
            await interaction.edit_original_response(embed=embed)
        
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
        
        # Button tanımlamaları
        stop_button = Button(emoji="⏹️", style=discord.ButtonStyle.danger)
        pause_button = Button(emoji="⏯️", style=discord.ButtonStyle.primary)
        skip_button = Button(emoji="⏭️", style=discord.ButtonStyle.primary) 
        queue_button = Button(emoji="📋", style=discord.ButtonStyle.secondary)
        favorite_button = Button(emoji="❤️", style=discord.ButtonStyle.success)
        
        # Callback tanımlamaları
        stop_button.callback = lambda i: self.button_stop_callback(i)
        pause_button.callback = lambda i: self.button_pause_callback(i)
        skip_button.callback = lambda i: self.button_skip_callback(i)
        queue_button.callback = lambda i: self.button_queue_callback(i)
        favorite_button.callback = lambda i: self.button_favorite_callback(i)

        # Butonları view'e ekleme

        view.add_item(stop_button)
        view.add_item(pause_button)
        view.add_item(skip_button)
        view.add_item(queue_button)
        view.add_item(favorite_button)

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
                    nonlocal current_page, view
                    if current_page < len(pages) - 1:
                        current_page += 1
                        embed.description = pages[current_page]
                        await interaction.response.edit_message(embed=embed, view=view)

                async def previous_callback(interaction):
                    nonlocal current_page, view
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
        if member.id != self.bot.user.id:
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

    def cog_unload(self):
        # Müzik çalma işlemlerini durdur
        for vc in self.bot.voice_clients:
            self.bot.loop.create_task(vc.disconnect(force=True))
        
        # Varsa queue'ları temizle
        if hasattr(self, 'queue'):
            self.queue.clear()

    async def add_favorite(self, user_id: str, guild_id: str, song_title: str, song_url: str):
        async with aiosqlite.connect('database/economy.db') as db:
            await db.execute('''
                INSERT OR REPLACE INTO favorite_songs 
                (user_id, guild_id, song_title, song_url) 
                VALUES (?, ?, ?, ?)
            ''', (user_id, guild_id, song_title, song_url))
            await db.commit()

    async def remove_favorite(self, user_id: str, song_url: str):
        async with aiosqlite.connect('database/economy.db') as db:
            await db.execute('''
                DELETE FROM favorite_songs 
                WHERE user_id = ? AND song_url = ?
            ''', (user_id, song_url))
            await db.commit()

    async def get_favorites(self, user_id: str, guild_id: str):
        try:
            async with aiosqlite.connect('database/economy.db') as db:
                async with db.execute('''
                    SELECT song_title, song_url 
                    FROM favorite_songs 
                    WHERE user_id = ? AND guild_id = ?
                    ORDER BY added_at DESC
                ''', (user_id, guild_id)) as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            print(f"Veritabanı hatası (get_favorites): {e}")
            return []

    async def is_favorite(self, user_id: str, song_url: str):
        async with aiosqlite.connect('database/economy.db') as db:
            async with db.execute('''
                SELECT 1 FROM favorite_songs 
                WHERE user_id = ? AND song_url = ?
            ''', (user_id, song_url)) as cursor:
                return await cursor.fetchone() is not None

    @discord.app_commands.command(name="favori", description="Şarkıyı favorilere ekler")
    async def slash_favori(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if not state["current_player"]:
            await interaction.response.send_message("Şu anda çalan şarkı yok!", ephemeral=True)
            return
        current_song = state["current_player"]
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        if await self.is_favorite(user_id, current_song['url']):
            await self.remove_favorite(user_id, current_song['url'])
            await interaction.response.send_message("Şarkı favorilerden çıkarıldı!", ephemeral=True)
        else:
            await self.add_favorite(user_id, guild_id, current_song['title'], current_song['url'])
            await interaction.response.send_message("Şarkı favorilere eklendi!", ephemeral=True)

    class FavoritesView(discord.ui.View):
        def __init__(self, pages, current_page=0):
            super().__init__(timeout=None)
            self.pages = pages
            self.current_page = 0
            self.total_pages = len(pages)
            self.update_buttons()
        
        def update_buttons(self):
            self.previous_page.disabled = self.current_page <= 0
            self.next_page.disabled = self.current_page >= self.total_pages - 1
            self.page_counter.label = f"Sayfa {self.current_page + 1}/{self.total_pages}"
        
        @discord.ui.button(label="◀️ Önceki", style=discord.ButtonStyle.primary)
        async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.current_page > 0:
                self.current_page -= 1
                self.update_buttons()
                await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
        
        @discord.ui.button(label="Sayfa 1/1", style=discord.ButtonStyle.secondary, disabled=True)
        async def page_counter(self, interaction: discord.Interaction, button: discord.ui.Button):
            pass
        
        @discord.ui.button(label="Sonraki ▶️", style=discord.ButtonStyle.primary)
        async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
            if self.current_page < len(self.pages) - 1:
                self.current_page += 1
                self.update_buttons()
                await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

        async def on_timeout(self):
            for item in self.children:
                item.disabled = True
            await self.message.edit(view=self)

    @discord.app_commands.command(name="favoriler", description="Favori şarkıları listeler")
    async def slash_favoriler(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
            user_id = str(interaction.user.id)
            guild_id = str(interaction.guild.id)
            favorites = await self.get_favorites(user_id, guild_id)
            if not favorites:
                await interaction.followup.send("Favori şarkı listeniz boş!", ephemeral=True)
                return
            pages = []
            for i in range(0, len(favorites), 5):
                embed = discord.Embed(title="🎵 Favori Şarkılarınız", color=discord.Color.blue())
                song_list = ""
                for idx, (title, _) in enumerate(favorites[i:i+5], i+1):
                    shortened_title = title[:40] + "..." if len(title) > 40 else title
                    song_list += f"`{idx}.` {shortened_title}\n"
                embed.description = song_list
                embed.set_footer(text="Bir şarkıyı çalmak için /favorical <numara> komutunu kullanın")
                pages.append(embed)
            if pages:
                view = self.FavoritesView(pages)
                await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)
            else:
                await interaction.followup.send("Favori şarkı listeniz boş!", ephemeral=True)
        except Exception as e:
            print(f"Favoriler listesi hatası: {e}")
            await interaction.followup.send("Favori şarkılar listelenirken bir hata oluştu.", ephemeral=True)

    @discord.app_commands.command(name="favoricallist", description="Tüm favori şarkılarınızı sıraya ekler ve çalar")
    async def slash_favoricallist(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)

        # Ses kanalında mı?
        try:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                # Voice connection with user-friendly retry  
                connection_embed = discord.Embed(
                    title="🎵 Ses Kanalına Bağlanıyor...", 
                    description="Lütfen bekleyin, bağlantı kuruluyor...", 
                    color=discord.Color.blue()
                )
                await interaction.response.send_message(embed=connection_embed)
                
                for attempt in range(3):
                    try:
                        await asyncio.wait_for(channel.connect(timeout=30.0), timeout=45.0)
                        state = self.get_guild_state(interaction.guild.id)
                        state["caller"] = interaction.user
                        break
                    except (asyncio.TimeoutError, discord.errors.ConnectionClosed) as e:
                        if attempt == 2:
                            # Final failure message
                            error_embed = discord.Embed(
                                title="⚠️ Müzik Sistemi Hakkında",
                                description="Sunucumuz uygun fiyatlı olduğundan dolayı Türkiye'de bulunuyor ve Discord yasaklarından ötürü ping sorunu yaşıyoruz.\n\n"
                                           "Sunucu kiralamak pahalı olduğundan müzik için sorunlar çıkabiliyor. 😅\n\n"
                                           "**Çözüm önerileri:**\n"
                                           "• Biraz bekleyip tekrar deneyin\n" 
                                           "• Bazen 2-3 deneme gerekebilir\n"
                                           "• Anlayışınız için teşekkürler! 🙏",
                                color=discord.Color.orange()
                            )
                            error_embed.set_footer(text="Daha iyi hizmet verebilmek için çalışıyoruz ❤️")
                            await interaction.edit_original_response(embed=error_embed)
                            return
                        
                        # Show retry attempt
                        retry_embed = discord.Embed(
                            title="🔄 Yeniden Deneniyor...",
                            description=f"Bağlantı kurulamadı, deneme {attempt + 2}/3...",
                            color=discord.Color.yellow()
                        )
                        await interaction.edit_original_response(embed=retry_embed)
                        await asyncio.sleep(3)
            elif interaction.guild.voice_client.channel != channel:
                await interaction.response.send_message(
                    f"🔒 Bot şu anda başka bir ses kanalında: **{interaction.guild.voice_client.channel.name}**",
                    ephemeral=True
                )
                return
        except AttributeError:
            await interaction.response.send_message("📢 Lütfen önce bir ses kanalına katılın.", ephemeral=True)
            return

        # Favori verilerini al
        favorites = await self.get_favorites(user_id, guild_id)
        if not favorites:
            await interaction.response.send_message("📭 Favori listeniz boş!", ephemeral=True)
            return

        await interaction.response.defer()

        state = self.get_guild_state(interaction.guild.id)
        songs_added = 0
        failed_songs = []

        for title, url in favorites:
            if "googlevideo.com" in url:
                print(f"Geçersiz yönlendirme linki atlandı: {url}")
                failed_songs.append(title)
                continue
            try:
                entries = await self.YTDLSource.from_url(url, loop=self.bot.loop, stream=True)
                if entries and len(entries) > 0:
                    async with state["queue_lock"]:
                        state["queue"].append(entries[0])
                        songs_added += 1
                else:
                    failed_songs.append(title)
            except Exception as e:
                print(f"Yüklenemeyen favori: {title} ({url}) -> {e}")
                failed_songs.append(title)

        if songs_added > 0:
            if not state["is_playing"]:
                state["is_playing"] = True
                await self.prepare_next_song(interaction)

            embed = discord.Embed(
                title="🎶 Favoriler Eklendi",
                description=f"✅ {songs_added} şarkı sıraya başarıyla eklendi.",
                color=discord.Color.green()
            )

            if failed_songs:
                failed_text = '\n'.join(
                    [f"❌ {t[:40]}..." if len(t) > 40 else f"❌ {t}" for t in failed_songs]
                )
                embed.add_field(name="Eklenemeyen Şarkılar", value=failed_text[:1024], inline=False)

            await interaction.followup.send(embed=embed, ephemeral=True)
        else:
            await interaction.followup.send(
                "❌ Hiçbir şarkı yüklenemedi. Şarkılar silinmiş veya engellenmiş olabilir.",
                ephemeral=True
            )
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.disconnect()
            state["queue"].clear()
            state["is_playing"] = False



    @discord.app_commands.command(name="favorisil")
    @discord.app_commands.describe(sira_no="Silmek istediğiniz şarkının sıra numarası")
    async def slash_favorisil(self, interaction: discord.Interaction, sira_no: app_commands.Range[int, 1, 100]):
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        favorites = await self.get_favorites(user_id, guild_id)
        if not favorites:
            await interaction.response.send_message("Favori şarkı listeniz zaten boş!", ephemeral=True)
            return
        if sira_no < 1 or sira_no > len(favorites):
            await interaction.response.send_message(f"Geçersiz şarkı numarası! 1 ile {len(favorites)} arasında bir sayı girin.", ephemeral=True)
            return
        try:
            selected_song = favorites[sira_no - 1]
            await self.remove_favorite(user_id, selected_song[1])
            embed = discord.Embed(
                title="Favori Şarkı Silindi", 
                description=f"{selected_song[0]} favori listenizden kaldırıldı.", 
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Favori şarkı silme hatası: {e}")
            error_embed = discord.Embed(
                title="Hata", 
                description="Şarkı silinirken bir hata oluştu.", 
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

    @discord.app_commands.command(name="favoritümünüsil")
    @discord.app_commands.describe(onay="Tüm favori şarkılarınızı silmek istediğinize emin misiniz?")
    @discord.app_commands.choices(onay=[
        discord.app_commands.Choice(name="Evet", value="evet"),
        discord.app_commands.Choice(name="Hayır", value="hayır")
    ])
    async def slash_favoritümünüsil(self, interaction: discord.Interaction, onay: str):
        if onay != "evet":
            await interaction.response.send_message("İşlem iptal edildi.", ephemeral=True)
            return
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        try:
            async with aiosqlite.connect('database/economy.db') as db:
                await db.execute('''
                    DELETE FROM favorite_songs 
                    WHERE user_id = ? AND guild_id = ?
                ''', (user_id, guild_id))
                await db.commit()
            embed = discord.Embed(
                title="Favori Listesi Temizlendi", 
                description="Tüm favori şarkılarınız silindi.", 
                color=discord.Color.green()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            print(f"Tüm favorileri silme hatası: {e}")
            error_embed = discord.Embed(
                title="Hata", 
                description="Favori listesi silinirken bir hata oluştu.", 
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=error_embed, ephemeral=True)

class QueueView(discord.ui.View):
    def __init__(self, pages, timeout=30):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.primary)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            embed = discord.Embed(title="Sıradaki Şarkılar", description=self.pages[self.current_page], color=discord.Color.blue())
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.primary)  
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            embed = discord.Embed(title="Sıradaki Şarkılar", description=self.pages[self.current_page], color=discord.Color.blue())
            await interaction.response.edit_message(embed=embed, view=self)
            
    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        await self.message.edit(view=self)

class FavoritesView(discord.ui.View):
    def __init__(self, pages):
        super().__init__(timeout=None)
        self.pages = pages
        self.current_page = 0
        self.total_pages = len(pages)
        self.update_buttons()
    
    def update_buttons(self):
        self.previous_page.disabled = self.current_page <= 0
        self.next_page.disabled = self.current_page >= self.total_pages - 1
        self.page_counter.label = f"Sayfa {self.current_page + 1}/{self.total_pages}"
    
    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.primary)
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    @discord.ui.button(label="Sayfa 1/1", style=discord.ButtonStyle.secondary, disabled=True)
    async def page_counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass
    
    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

async def setup(bot):
    await bot.add_cog(Music(bot))