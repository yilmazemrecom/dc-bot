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
                "current_message": None,
                "voice_client": None
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
        'extract_flat': 'in_playlist',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'referer': 'https://www.youtube.com/',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }

    ffmpeg_options = {
        'before_options': (
            '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 '
            '-reconnect_at_eof 1 -reconnect_on_network_error 1 '
            '-reconnect_on_http_error 4xx,5xx'
        ),
        'options': '-vn -filter:a "volume=0.25"'
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
            try:
                def extract_info():
                    return Music.ytdl.extract_info(url, download=not stream)
                
                data = await loop.run_in_executor(None, extract_info)
            except Exception as e:
                print(f"URL çıkarma hatası: {e}")
                return None

            if not data:
                return None

            if 'entries' in data:
                entries = data['entries']
                entries = [entry for entry in entries if entry and entry.get('url')]
                return entries
            else:
                return [data]

        @classmethod
        async def create_source(cls, entry, *, loop=None, retries=3):
            loop = loop or asyncio.get_event_loop()
            
            for attempt in range(retries):
                try:
                    def extract_info():
                        return Music.ytdl.extract_info(entry['url'], download=False)
                    
                    data = await loop.run_in_executor(None, extract_info)
                    
                    if not data or 'url' not in data:
                        if attempt < retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        return None
                    
                    return cls(discord.FFmpegPCMAudio(data['url'], **Music.ffmpeg_options), data=data)
                    
                except youtube_dl.utils.DownloadError as e:
                    print(f"Download hatası (deneme {attempt + 1}/{retries}): {e}")
                    if "MESAM / MSG CS" in str(e) or "unavailable" in str(e):
                        print(f"Engellenen video atlanıyor: {entry['url']}")
                        return None
                    elif "HTTP Error 403" in str(e) and attempt < retries - 1:
                        await asyncio.sleep(3 + attempt * 2)
                        continue
                    elif attempt == retries - 1:
                        return None
                except Exception as e:
                    print(f"Genel hata (deneme {attempt + 1}/{retries}): {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(1 + attempt)
                        continue
                    return None
            
            return None

    async def play_next(self, interaction):
        guild_id = interaction.guild.id
        state = self.get_guild_state(guild_id)
        
        if not interaction.guild.voice_client or not interaction.guild.voice_client.is_connected():
            state["is_playing"] = False
            await self.cleanup_guild_state(guild_id)
            return
            
        if state["queue"]:
            state["current_player"] = state["queue"].pop(0)
            state["is_playing"] = True
            
            async with interaction.channel.typing():
                source = await self.YTDLSource.create_source(state["current_player"], loop=self.bot.loop, retries=3)
                
                if source:
                    view = self.get_control_buttons(interaction)
                    
                    try:
                        interaction.guild.voice_client.play(
                            source, 
                            after=lambda e: asyncio.run_coroutine_threadsafe(
                                self.play_next_after_callback(interaction), 
                                self.bot.loop
                            )
                        )
                        
                        embed = discord.Embed(
                            title="🎵 Şu anda Çalan Şarkı", 
                            description=state["current_player"]['title'], 
                            color=discord.Color.green()
                        )
                        embed.set_thumbnail(url=source.thumbnail)
                        
                        if state["current_message"]:
                            try:
                                await state["current_message"].edit(embed=embed, view=view)
                            except discord.NotFound:
                                state["current_message"] = await interaction.channel.send(embed=embed, view=view)
                        else:
                            state["current_message"] = await interaction.channel.send(embed=embed, view=view)
                            
                    except Exception as e:
                        print(f"Oynatma hatası: {e}")
                        await self.prepare_next_song(interaction)
                else:
                    await self.prepare_next_song(interaction)
        else:
            state["is_playing"] = False
            await self.cleanup_guild_state(guild_id)

    async def cleanup_guild_state(self, guild_id):
        """Sunucu durumunu temizle"""
        state = self.get_guild_state(guild_id)
        
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client:
            try:
                await guild.voice_client.disconnect(force=True)
            except Exception as e:
                print(f"Voice client bağlantısı kesilirken hata: {e}")
        
        if state["current_message"]:
            try:
                await state["current_message"].delete()
            except Exception as e:
                print(f"Mesaj silinirken hata: {e}")
            state["current_message"] = None
        
        state["queue"].clear()
        state["current_player"] = None
        state["is_playing"] = False

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
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.pause()
            await interaction.response.send_message("⏸️ Şarkı duraklatıldı", ephemeral=True)
        elif interaction.guild.voice_client and interaction.guild.voice_client.is_paused():
            interaction.guild.voice_client.resume()
            await interaction.response.send_message("▶️ Şarkı devam ediyor", ephemeral=True)
        else:
            await interaction.response.send_message("Çalan şarkı yok", ephemeral=True)

    async def button_skip_callback(self, interaction: discord.Interaction):
        if interaction.guild.voice_client and interaction.guild.voice_client.is_playing():
            interaction.guild.voice_client.stop()
            await interaction.response.send_message("⭐ Şarkı geçildi", ephemeral=True)
        else:
            await interaction.response.send_message("Çalan şarkı yok", ephemeral=True)

    async def button_stop_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if interaction.guild.voice_client:
            state["queue"].clear()
            interaction.guild.voice_client.stop()
            await interaction.guild.voice_client.disconnect()
            await interaction.response.send_message("⏹️ Müzik durduruldu", ephemeral=True)
        else:
            await interaction.response.send_message("Bot zaten bağlı değil", ephemeral=True)

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
                source = await self.YTDLSource.create_source(next_song, loop=self.bot.loop, retries=2)
                if source:
                    state["queue"].insert(0, next_song)
                    state["is_playing"] = True
                    await self.play_next(interaction)
                    break
            else:
                state["is_playing"] = False
                await self.cleanup_guild_state(interaction.guild.id)

    @discord.app_commands.command(name="cal", description="Şarkı çalar")
    @discord.app_commands.describe(sarki="Şarkı adı veya URL (Sadece YouTube linki giriniz)")
    async def slash_cal(self, interaction: discord.Interaction, sarki: str):
        state = self.get_guild_state(interaction.guild.id)
        
        try:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                await channel.connect()
                state["caller"] = interaction.user
            elif interaction.guild.voice_client.channel != channel:
                await interaction.response.send_message(
                    f"Şu anda başka bir kanalda bulunuyorum ({interaction.guild.voice_client.channel.name}). "
                    f"Müsait olunca tekrar çağırın.", 
                    ephemeral=True
                )
                return
        except AttributeError:
            await interaction.response.send_message("Bir ses kanalında değilsiniz.", ephemeral=True)
            return

        embed = discord.Embed(title="Şarkı Yükleniyor", description="Lütfen bekleyin...", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)
        loading_message = await interaction.original_response()

        try:
            # Lambda fonksiyonu yerine doğrudan fonksiyon çağrısı
            loop = asyncio.get_event_loop()
            def extract_info():
                return self.ytdl.extract_info(sarki, download=False)
            
            data = await loop.run_in_executor(None, extract_info)
            
            if not data:
                await loading_message.edit(
                    content="Şarkı bilgisi alınamadı.", 
                    embed=None, 
                    delete_after=10
                )
                return
                
            # Entries oluştur
            if 'entries' in data:
                entries = [entry for entry in data['entries'] if entry and entry.get('url')]
            else:
                entries = [data]
                
            if entries:
                async with state["queue_lock"]:
                    state["queue"].extend(entries)
                    
                if not state["is_playing"]:
                    await self.prepare_next_song(interaction)
                    
                embed = discord.Embed(
                    title="Şarkılar Kuyruğa Eklendi", 
                    description=f"{len(entries)} şarkı kuyruğa eklendi.", 
                    color=discord.Color.blue()
                )
                await loading_message.edit(embed=embed, delete_after=10)
            else:
                await loading_message.edit(
                    content="Playlistte geçerli şarkı bulunamadı.", 
                    embed=None, 
                    delete_after=10
                )
                await self.cleanup_guild_state(interaction.guild.id)

        except Exception as e:
            print(f"Şarkı bilgisi çıkarılırken hata oluştu: {e}")
            await loading_message.edit(
                content="Şarkı yüklenirken bir hata oluştu.", 
                embed=None, 
                delete_after=10
            )

    def get_control_buttons(self, interaction):
        view = discord.ui.View(timeout=600)
        
        stop_button = Button(emoji="⏹️", style=discord.ButtonStyle.danger)
        pause_button = Button(emoji="⏯️", style=discord.ButtonStyle.primary)
        skip_button = Button(emoji="⭐", style=discord.ButtonStyle.primary) 
        queue_button = Button(emoji="📋", style=discord.ButtonStyle.secondary)
        favorite_button = Button(emoji="❤️", style=discord.ButtonStyle.success)
        
        stop_button.callback = lambda i: self.button_stop_callback(i)
        pause_button.callback = lambda i: self.button_pause_callback(i)
        skip_button.callback = lambda i: self.button_skip_callback(i)
        queue_button.callback = lambda i: self.button_queue_callback(i)
        favorite_button.callback = lambda i: self.button_favorite_callback(i)

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
                max_chars = 1024
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
                await interaction.response.send_message(embed=embed, view=view, delete_after=30)
            else:
                await interaction.response.send_message("Sırada şarkı yok.", delete_after=30)
        else:
            await interaction.response.send_message("Bot bir ses kanalında değil.", delete_after=30)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id != self.bot.user.id:
            return

        # Bot voice state değişikliği - kanaldan ayrıldı
        if before.channel is not None and after.channel is None:
            await self.cleanup_guild_state(member.guild.id)

    @tasks.loop(minutes=1.0)
    async def check_voice_channel(self):
        for guild in self.bot.guilds:
            if guild.voice_client and guild.voice_client.is_connected():
                voice_channel = guild.voice_client.channel
                if voice_channel and len(voice_channel.members) == 1:
                    await asyncio.sleep(300)  # 5 dakika bekle
                    if (guild.voice_client and guild.voice_client.is_connected() and 
                        len(guild.voice_client.channel.members) == 1):
                        print(f"Bot {guild.name} sunucusunda yalnız kaldı, ayrılıyor...")
                        await self.cleanup_guild_state(guild.id)

    @check_voice_channel.before_loop
    async def before_check_voice_channel(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.component:
            state = self.get_guild_state(interaction.guild.id)
            if state["current_message"] and interaction.message.id == state["current_message"].id:
                await interaction.response.defer()
                embed = state["current_message"].embeds[0]
                view = self.get_control_buttons(interaction)
                await state["current_message"].edit(embed=embed, view=view)

    def cog_unload(self):
        self.check_voice_channel.cancel()
        for guild_id in list(self.guild_states.keys()):
            asyncio.create_task(self.cleanup_guild_state(guild_id))

    # Favori sistem metodları
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

        try:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                await channel.connect()
                state = self.get_guild_state(interaction.guild.id)
                state["caller"] = interaction.user
            elif interaction.guild.voice_client.channel != channel:
                await interaction.response.send_message(
                    f"🔒 Bot şu anda başka bir ses kanalında: **{interaction.guild.voice_client.channel.name}**",
                    ephemeral=True
                )
                return
        except AttributeError:
            await interaction.response.send_message("🔢 Lütfen önce bir ses kanalına katılın.", ephemeral=True)
            return

        favorites = await self.get_favorites(user_id, guild_id)
        if not favorites:
            await interaction.response.send_message("🔭 Favori listeniz boş!", ephemeral=True)
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