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
                "favorites": [],  # Sadece favori şarkılar kalsın
                "loop": "off"  # "off", "single", "queue" olarak 3 mod ekleyelim
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
        state = self.get_guild_state(interaction.guild.id)
        
        try:
            # Şu anki şarkıyı önceki şarkı olarak kaydet
            if state["current_player"]:
                state["previous_song"] = state["current_player"].copy()
            
            # Döngü moduna göre işlem yap
            if state["current_player"]:
                if state["loop"] == "single":
                    # Aynı şarkıyı tekrar çal
                    async with state["queue_lock"]:
                        current_song = state["current_player"].copy()
                        state["queue"].insert(0, current_song)
                elif state["loop"] == "queue":
                    # Şarkıyı kuyruğun sonuna ekle
                    async with state["queue_lock"]:
                        current_song = state["current_player"].copy()
                        state["queue"].append(current_song)
            
            # Eğer kuyruk boşsa ve döngü modu queue ise tüm şarkıları tekrar ekle
            if not state["queue"] and state["loop"] == "queue" and state["previous_song"]:
                async with state["queue_lock"]:
                    state["queue"].append(state["previous_song"].copy())
            
            # Eğer kuyruk boşsa ve ses kanalındaysa
            if not state["queue"] and interaction.guild.voice_client:
                state["is_playing"] = False
                await interaction.guild.voice_client.disconnect()
                
                # Son mesajı güncelle
                if state["current_message"]:
                    try:
                        end_embed = discord.Embed(
                            title="Müzik Bitti",
                            description="Çalma listesi sona erdi.",
                            color=discord.Color.blue()
                        )
                        await state["current_message"].edit(embed=end_embed, view=None)
                    except:
                        pass
                return
            
            # Yeni şarkıyı hazırla
            await self.prepare_next_song(interaction)

        except Exception as e:
            print(f"Play next callback hatası: {e}")
            if interaction.guild.voice_client:
                await interaction.guild.voice_client.disconnect()

    async def prepare_next_song(self, interaction):
        state = self.get_guild_state(interaction.guild.id)
        async with state["queue_lock"]:
            try:
                # Önce ses kanalı bağlantısını kontrol et
                if not interaction.guild.voice_client:
                    try:
                        channel = interaction.user.voice.channel
                        await channel.connect()
                    except:
                        print("Ses kanalına bağlanılamadı")
                        state["is_playing"] = False
                        return

                while state["queue"]:
                    next_song = state["queue"].pop(0)
                    if not next_song:
                        continue
                        
                    source = await self.YTDLSource.create_source(next_song, loop=self.bot.loop)
                    if source and interaction.guild.voice_client:  # Voice client'ı tekrar kontrol et
                        state["current_player"] = next_song
                        interaction.guild.voice_client.play(
                            source,
                            after=lambda e: self.bot.loop.create_task(
                                self.play_next_after_callback(interaction)
                            )
                        )
                        state["is_playing"] = True
                        
                        # Embed ve butonları oluştur
                        embed = discord.Embed(
                            title="🎵 Şimdi Çalıyor",
                            description=f"[{next_song['title']}]({next_song['url']})",
                            color=discord.Color.blue()
                        )
                        
                        if 'thumbnail' in next_song:
                            embed.set_thumbnail(url=next_song['thumbnail'])
                        
                        # Butonları oluştur
                        view = View(timeout=None)
                        buttons = [
                            ("⏮️", "previous", discord.ButtonStyle.primary, self.button_previous_callback),
                            ("⏯️", "pause", discord.ButtonStyle.primary, self.button_pause_callback),
                            ("⏭️", "skip", discord.ButtonStyle.primary, self.button_skip_callback),
                            ("⏹️", "stop", discord.ButtonStyle.danger, self.button_stop_callback),
                            ("📜", "queue", discord.ButtonStyle.secondary, self.button_queue_callback),
                            ("🔀", "shuffle", discord.ButtonStyle.secondary, self.button_shuffle_callback),
                            ("🔁", "loop", discord.ButtonStyle.secondary, self.button_loop_callback),
                            ("❤️", "favorite", discord.ButtonStyle.success, self.button_favorite_callback)
                        ]
                        
                        for emoji, custom_id, style, callback in buttons:
                            button = Button(style=style, emoji=emoji, custom_id=custom_id)
                            button.callback = lambda i, cb=callback: cb(i)
                            view.add_item(button)
                        
                        # Mesajı güncelle
                        try:
                            if state["current_message"]:
                                await state["current_message"].edit(embed=embed, view=view)
                            else:
                                state["current_message"] = await interaction.followup.send(embed=embed, view=view)
                        except discord.NotFound:
                            state["current_message"] = await interaction.followup.send(embed=embed, view=view)
                        
                        break
                else:
                    state["is_playing"] = False
                    if interaction.guild.voice_client:
                        await interaction.guild.voice_client.disconnect()
                    
            except Exception as e:
                print(f"Şarkı hazırlama hatası: {e}")
                state["is_playing"] = False
                if interaction.guild.voice_client:
                    await interaction.guild.voice_client.disconnect()
                try:
                    await interaction.followup.send("Şarkı çalınırken bir hata oluştu.", ephemeral=True)
                except:
                    pass

    # Yeni buton callback'leri
    async def button_previous_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        
        try:
            await interaction.response.defer(ephemeral=True)
            
            if state.get("previous_song"):
                # Şu anki şarkıyı kuyruğun başına ekle
                if state["current_player"]:
                    async with state["queue_lock"]:
                        current = state["current_player"].copy()
                        state["queue"].insert(0, current)
                
                # Önceki şarkıyı çal
                async with state["queue_lock"]:
                    state["queue"].insert(0, state["previous_song"].copy())
                
                if interaction.guild.voice_client:
                    interaction.guild.voice_client.stop()  # Mevcut şarkıyı durdur
                
                await interaction.followup.send("⏮️ Önceki şarkıya dönülüyor", ephemeral=True)
            else:
                await interaction.followup.send("Önceki şarkı yok!", ephemeral=True)
                
            await self.update_player_message(interaction, state)
            
        except Exception as e:
            print(f"Önceki şarkı hatası: {e}")
            await interaction.followup.send("Bir hata oluştu.", ephemeral=True)

    async def button_queue_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if not state["queue"]:
            await interaction.response.send_message("Sırada şarkı yok!", ephemeral=True)
            return
            
        embed = discord.Embed(title="🎵 Çalma Listesi", color=discord.Color.blue())
        
        # Şu an çalan
        if state["current_player"]:
            embed.add_field(
                name="Şimdi Çalıyor",
                value=f"▶️ {state['current_player']['title']}",
                inline=False
            )
        
        # Sıradaki şarkılar
        queue_text = ""
        for idx, song in enumerate(state["queue"], 1):
            queue_text += f"{idx}. {song['title']}\n"
            if idx % 10 == 0:
                embed.add_field(name=f"Sıradaki Şarkılar ({idx-9}-{idx})", value=queue_text, inline=False)
                queue_text = ""
        
        if queue_text:
            embed.add_field(name="Sıradaki Şarkılar", value=queue_text, inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await self.update_player_message(interaction, state)

    async def button_shuffle_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if state["queue"]:
            random.shuffle(state["queue"])
            await interaction.response.send_message("🔀 Çalma listesi karıştırıldı", ephemeral=True)
        else:
            await interaction.response.send_message("Sırada şarkı yok!", ephemeral=True)
        await self.update_player_message(interaction, state)

    async def button_loop_callback(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        
        # Döngü modları arasında geçiş yap
        if state["loop"] == "off":
            state["loop"] = "single"
            status = "🔂 Tek şarkı döngüsü açık"
        elif state["loop"] == "single":
            state["loop"] = "queue"
            status = "🔁 Çalma listesi döngüsü açık"
        else:
            state["loop"] = "off"
            status = "➡️ Döngü kapalı"
            
        await interaction.response.send_message(status, ephemeral=True)
        await self.update_player_message(interaction, state)

    # Buton callback fonksiyonları
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
        
        # Ses kanalı kontrolü
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
            # Önce defer edelim
            await interaction.response.defer(ephemeral=True)
            
            if await self.is_favorite(user_id, current_song['url']):
                await self.remove_favorite(user_id, current_song['url'])
                await interaction.followup.send("💔 Şarkı favorilerden çıkarıldı!", ephemeral=True)
            else:
                await self.add_favorite(user_id, guild_id, current_song['title'], current_song['url'])
                await interaction.followup.send("❤️ Şarkı favorilere eklendi!", ephemeral=True)
            
            # Mesajı güncelle
            embed = discord.Embed(
                title="🎵 Şimdi Çalıyor",
                description=f"[{current_song['title']}]({current_song['url']})",
                color=discord.Color.blue()
            )
            
            # Thumbnail ve ek bilgiler
            if 'thumbnail' in current_song:
                embed.set_thumbnail(url=current_song['thumbnail'])
            
            # Butonları yeniden oluştur
            view = View(timeout=None)
            
            # İlk sıra butonları
            previous_button = Button(style=discord.ButtonStyle.primary, emoji="⏮️", custom_id="previous")
            previous_button.callback = lambda i: self.button_previous_callback(i)
            view.add_item(previous_button)
            
            pause_button = Button(style=discord.ButtonStyle.primary, emoji="⏯️", custom_id="pause")
            pause_button.callback = lambda i: self.button_pause_callback(i)
            view.add_item(pause_button)
            
            skip_button = Button(style=discord.ButtonStyle.primary, emoji="⏭️", custom_id="skip")
            skip_button.callback = lambda i: self.button_skip_callback(i)
            view.add_item(skip_button)
            
            stop_button = Button(style=discord.ButtonStyle.danger, emoji="⏹️", custom_id="stop")
            stop_button.callback = lambda i: self.button_stop_callback(i)
            view.add_item(stop_button)

            # İkinci sıra butonları
            queue_button = Button(style=discord.ButtonStyle.secondary, emoji="📜", custom_id="queue")
            queue_button.callback = lambda i: self.button_queue_callback(i)
            view.add_item(queue_button)
            
            shuffle_button = Button(style=discord.ButtonStyle.secondary, emoji="🔀", custom_id="shuffle")
            shuffle_button.callback = lambda i: self.button_shuffle_callback(i)
            view.add_item(shuffle_button)
            
            loop_button = Button(style=discord.ButtonStyle.secondary, emoji="🔁", custom_id="loop")
            loop_button.callback = lambda i: self.button_loop_callback(i)
            view.add_item(loop_button)
            
            favorite_button = Button(style=discord.ButtonStyle.success, emoji="❤️", custom_id="favorite")
            favorite_button.callback = lambda i: self.button_favorite_callback(i)
            view.add_item(favorite_button)

            # Mevcut mesajı güncelle
            if state["current_message"]:
                await state["current_message"].edit(embed=embed, view=view)

        except Exception as e:
            print(f"Favori işlemi hatası: {e}")
            try:
                await interaction.followup.send("Bir hata oluştu.", ephemeral=True)
            except:
                pass

    @discord.app_commands.command(name="cal")
    @discord.app_commands.describe(
        sarki="Şarkı adı veya URL (Sadece YouTube linki giriniz)"
    )
    async def slash_cal(self, interaction: discord.Interaction,
        sarki: str,
    ):
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
            self.current_page = current_page
            self.total_pages = len(pages)
            
            # Butonları güncelle
            self.update_buttons()
        
        def update_buttons(self):
            # Önceki sayfa butonu
            self.previous_page.disabled = self.current_page <= 0
            # Sonraki sayfa butonu
            self.next_page.disabled = self.current_page >= self.total_pages - 1
            # Sayfa numarası
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
            # Timeout olduğunda butonları devre dışı bırak
            for item in self.children:
                item.disabled = True

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

            # Her sayfada 5 şarkı olacak şekilde böl
            pages = []
            for i in range(0, len(favorites), 5):
                embed = discord.Embed(
                    title="🎵 Favori Şarkılarınız", 
                    color=discord.Color.blue()
                )
                
                # Şarkıları tek bir alanda göster
                song_list = ""
                for idx, (title, _) in enumerate(favorites[i:i+5], i+1):
                    # Başlığı 40 karakterle sınırla
                    shortened_title = title[:40] + "..." if len(title) > 40 else title
                    song_list += f"`{idx}.` {shortened_title}\n"
                
                embed.description = song_list
                embed.set_footer(text="Bir şarkıyı çalmak için /favorical <numara> komutunu kullanın")
                pages.append(embed)

            # Sayfa görünümünü oluştur ve gönder
            if pages:
                view = self.FavoritesView(pages)
                await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)
            else:
                await interaction.followup.send("Favori şarkı listeniz boş!", ephemeral=True)

        except Exception as e:
            print(f"Favoriler listesi hatası: {e}")
            await interaction.followup.send(
                "Favori şarkılar listelenirken bir hata oluştu.", 
                ephemeral=True
            )

    @discord.app_commands.command(name="favorical")
    @discord.app_commands.describe(
        sira_no="Çalmak istediğiniz şarkının sıra numarası"
    )
    async def slash_favorical(self, interaction: discord.Interaction, 
        sira_no: app_commands.Range[int, 1, 100]
    ):
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        
        # Ses kanalı kontrolü
        try:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                await channel.connect()
            elif interaction.guild.voice_client.channel != channel:
                await interaction.response.send_message(
                    f"Şu anda başka bir kanalda bulunuyorum ({interaction.guild.voice_client.channel.name}). "
                    "Müsait olunca tekrar çağırın.", 
                    ephemeral=True
                )
                return
        except AttributeError:
            await interaction.response.send_message("Bir ses kanalında değilsiniz.", ephemeral=True)
            return

        # Favorileri kontrol et
        favorites = await self.get_favorites(user_id, guild_id)
        
        if not favorites:
            await interaction.response.send_message("Favori şarkı listeniz boş!", ephemeral=True)
            return
            
        if sira_no < 1 or sira_no > len(favorites):
            await interaction.response.send_message(
                f"Geçersiz şarkı numarası! 1 ile {len(favorites)} arasında bir sayı girin.", 
                ephemeral=True
            )
            return

        # Yükleniyor mesajı
        await interaction.response.defer()

        try:
            selected_song = favorites[sira_no - 1]
            state = self.get_guild_state(interaction.guild.id)

            # Şarkıyı YouTube'dan yükle
            entries = await self.YTDLSource.from_url(selected_song[1], loop=self.bot.loop, stream=True)
            if entries and len(entries) > 0:
                async with state["queue_lock"]:
                    state["queue"].append(entries[0])
                if not state["is_playing"]:
                    await self.prepare_next_song(interaction)
                else:
                    await interaction.followup.send(
                        f"**{selected_song[0]}** sıraya eklendi.", 
                        ephemeral=True
                    )
            else:
                await interaction.followup.send(
                    "Şarkı yüklenemedi veya bulunamadı.", 
                    ephemeral=True
                )

        except Exception as e:
            print(f"Favori şarkı çalma hatası: {e}")
            await interaction.followup.send(
                "Şarkı çalınırken bir hata oluştu.", 
                ephemeral=True
            )

    @discord.app_commands.command(name="favorisil")
    @discord.app_commands.describe(
        sira_no="Silmek istediğiniz şarkının sıra numarası"
    )
    async def slash_favorisil(self, interaction: discord.Interaction, 
        sira_no: app_commands.Range[int, 1, 100]  # 1-100 arası
    ):
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        
        # Favorileri kontrol et
        favorites = await self.get_favorites(user_id, guild_id)
        
        if not favorites:
            await interaction.response.send_message("Favori şarkı listeniz zaten boş!", ephemeral=True)
            return
            
        if sira_no < 1 or sira_no > len(favorites):
            await interaction.response.send_message(
                f"Geçersiz şarkı numarası! 1 ile {len(favorites)} arasında bir sayı girin.", 
                ephemeral=True
            )
            return

        try:
            selected_song = favorites[sira_no - 1]
            await self.remove_favorite(user_id, selected_song[1])  # URL'i kullanarak sil
            
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
    @discord.app_commands.describe(
        onay="Tüm favori şarkılarınızı silmek istediğinize emin misiniz?"
    )
    @discord.app_commands.choices(
        onay=[
            discord.app_commands.Choice(name="Evet", value="evet"),
            discord.app_commands.Choice(name="Hayır", value="hayır")
        ]
    )
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

    async def update_player_message(self, interaction: discord.Interaction, state):
        # Eğer bot ses kanalında değilse veya şarkı çalmıyorsa güncelleme yapma
        if not interaction.guild.voice_client or not state["is_playing"]:
            return

        try:
            # Embed oluştur
            current_song = state["current_player"]
            embed = discord.Embed(
                title="🎵 Şimdi Çalıyor",
                description=f"[{current_song['title']}]({current_song['url']})",
                color=discord.Color.blue()
            )
            
            if 'thumbnail' in current_song:
                embed.set_thumbnail(url=current_song['thumbnail'])

            # View oluştur
            view = View(timeout=None)
            
            # Butonları ekle
            buttons = [
                ("⏮️", "previous", discord.ButtonStyle.primary, self.button_previous_callback),
                ("⏯️", "pause", discord.ButtonStyle.primary, self.button_pause_callback),
                ("⏭️", "skip", discord.ButtonStyle.primary, self.button_skip_callback),
                ("⏹️", "stop", discord.ButtonStyle.danger, self.button_stop_callback),
                ("📜", "queue", discord.ButtonStyle.secondary, self.button_queue_callback),
                ("🔀", "shuffle", discord.ButtonStyle.secondary, self.button_shuffle_callback),
                ("🔁", "loop", discord.ButtonStyle.secondary, self.button_loop_callback),
                ("❤️", "favorite", discord.ButtonStyle.success, self.button_favorite_callback)
            ]
            
            for emoji, custom_id, style, callback in buttons:
                button = Button(style=style, emoji=emoji, custom_id=custom_id)
                button.callback = lambda i, cb=callback: cb(i)
                view.add_item(button)

            # Mesajı güncelle veya yeni mesaj gönder
            if not state["current_message"]:
                state["current_message"] = await interaction.followup.send(embed=embed, view=view)
            else:
                try:
                    await state["current_message"].edit(embed=embed, view=view)
                except discord.NotFound:
                    state["current_message"] = await interaction.followup.send(embed=embed, view=view)

        except Exception as e:
            print(f"Mesaj güncelleme hatası: {e}")

    @discord.app_commands.command(name="favoricallist", description="Tüm favori şarkılarınızı sıraya ekler")
    async def slash_favoricallist(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        guild_id = str(interaction.guild.id)
        
        # Ses kanalı kontrolü
        try:
            channel = interaction.user.voice.channel
            if interaction.guild.voice_client is None:
                await channel.connect()
            elif interaction.guild.voice_client.channel != channel:
                await interaction.response.send_message(
                    f"Şu anda başka bir kanalda bulunuyorum ({interaction.guild.voice_client.channel.name}). "
                    "Müsait olunca tekrar çağırın.", 
                    ephemeral=True
                )
                return
        except AttributeError:
            await interaction.response.send_message("Bir ses kanalında değilsiniz.", ephemeral=True)
            return

        # Favorileri kontrol et
        favorites = await self.get_favorites(user_id, guild_id)
        
        if not favorites:
            await interaction.response.send_message("Favori şarkı listeniz boş!", ephemeral=True)
            return
            
        # Yükleniyor mesajı
        await interaction.response.defer()
        
        try:
            state = self.get_guild_state(interaction.guild.id)
            songs_added = 0

            for song_title, song_url in favorites:
                # Her şarkıyı YouTube'dan yükle
                entries = await self.YTDLSource.from_url(song_url, loop=self.bot.loop, stream=True)
                if entries and len(entries) > 0:
                    async with state["queue_lock"]:
                        state["queue"].append(entries[0])
                        songs_added += 1

            if songs_added > 0:
                if not state["is_playing"]:
                    await self.prepare_next_song(interaction)
                
                embed = discord.Embed(
                    title="Favoriler Eklendi",
                    description=f"✅ {songs_added} favori şarkı sıraya eklendi!",
                    color=discord.Color.green()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(
                    "Şarkılar eklenirken bir sorun oluştu.", 
                    ephemeral=True
                )

        except Exception as e:
            print(f"Favori şarkı listesi çalma hatası: {e}")
            await interaction.followup.send(
                "Şarkılar eklenirken bir hata oluştu.", 
                ephemeral=True
            )

async def setup(bot):
    await bot.add_cog(Music(bot))
