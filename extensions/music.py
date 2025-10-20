import discord
from discord.ext import commands, tasks
from discord.ui import Button, View
import asyncio
from asyncio import Lock
import aiosqlite
from typing import Optional
from discord import app_commands
import wavelink
import datetime
from config import LAVALINK_URI, LAVALINK_PASSWORD

class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild_states = {}
        self.check_voice_channel.start()
        self.bot.loop.create_task(self.connect_nodes())

    def get_guild_state(self, guild_id):
        if guild_id not in self.guild_states:
            self.guild_states[guild_id] = {
                "queue": [],
                "current_player": None,
                "is_playing": False,
                "queue_lock": Lock(),
                "caller": None,
                "current_message": None,
                "last_user_activity": datetime.datetime.now()
            }
        return self.guild_states[guild_id]

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        nodes = [wavelink.Node(uri=f"http://127.0.0.1:2333", password=LAVALINK_PASSWORD)]
        await wavelink.Pool.connect(nodes=nodes, client=self.bot)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        print(f'Wavelink Node Ready: {payload.node}')

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEndEventPayload):
        player = payload.player
        if player is None:
            return
        
        if not player.connected: 
            return

        state = self.get_guild_state(player.guild.id)
        
        # Kullanıcı aktivitesini güncelle
        state["last_user_activity"] = datetime.datetime.now()
        
        # Sırada şarkı varsa
        if state["queue"]:
            try:
                track = state["queue"].pop(0)
                await player.play(track)
                state["current_player"] = player.current  # player.current kullan, track değil
                state["is_playing"] = True
                
                if state["current_message"]:
                    try:
                        embed = discord.Embed(
                            title="Şu anda Çalan Şarkı",
                            description=track.title,
                            color=discord.Color.green()
                        )
                        if track.artwork:
                            embed.set_thumbnail(url=track.artwork)
                        elif track.thumbnail:
                            embed.set_thumbnail(url=track.thumbnail)
                            
                        view = self.get_control_buttons(state["current_message"])
                        await state["current_message"].edit(embed=embed, view=view)
                    except discord.errors.NotFound:
                        # Mesaj silinmişse yeni mesaj oluştur
                        try:
                            channel = player.channel if hasattr(player, 'channel') else player.guild.text_channels[0]
                            state["current_message"] = await channel.send(embed=embed, view=view)
                        except:
                            state["current_message"] = None
                    except Exception as e:
                        print(f"Mesaj güncelleme hatası: {e}")
                        
            except wavelink.LavalinkException as e:
                print(f"Wavelink hatası - şarkı çalınamadı: {e}")
                # Bu şarkı çalınamazsa bir sonrakini dene
                if state["queue"]:
                    # Kuyruktaki sonraki şarkıyı dene
                    await self.on_wavelink_track_end(payload)
                else:
                    # Kuyruk boşsa bağlantıyı kes
                    await player.disconnect()
                    state["is_playing"] = False
                    state["current_player"] = None
                    if state["current_message"]:
                        try:
                            await state["current_message"].delete()
                        except discord.errors.NotFound:
                            pass
                        finally:
                            state["current_message"] = None
            except Exception as e:
                print(f"Track end hatası: {e}")
                # Genel hata durumunda da sonraki şarkıyı dene
                if state["queue"]:
                    await self.on_wavelink_track_end(payload)
                else:
                    await player.disconnect()
                    state["is_playing"] = False
                    state["current_player"] = None
                    if state["current_message"]:
                        try:
                            await state["current_message"].delete()
                        except discord.errors.NotFound:
                            pass
                        finally:
                            state["current_message"] = None
        else:
            # Kuyruk boşsa
            try:
                await player.disconnect()
            except Exception as e:
                print(f"Disconnect hatası: {e}")
            finally:
                state["is_playing"] = False
                state["current_player"] = None
                if state["current_message"]:
                    try:
                        await state["current_message"].delete()
                    except discord.errors.NotFound:
                        pass
                    finally:
                        state["current_message"] = None

    async def _delete_message_after(self, message: discord.Message, delay: int):
        await asyncio.sleep(delay)
        try:
            await message.delete()
        except discord.errors.NotFound:
            pass

    async def play_next(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        player = interaction.guild.voice_client
        
        if not player or not player.connected:
            state["is_playing"] = False
            return
        
        if state["queue"]:
            try:
                track = state["queue"].pop(0)
                await player.play(track)
                state["is_playing"] = True
                state["current_player"] = player.current
                
                view = self.get_control_buttons(interaction)
                
                embed = discord.Embed(
                    title="Şu anda Çalan Şarkı",
                    description=track.title,
                    color=discord.Color.green()
                )
                
                if hasattr(track, 'artwork') and track.artwork:
                    embed.set_thumbnail(url=track.artwork)
                elif hasattr(track, 'thumbnail') and track.thumbnail:
                    embed.set_thumbnail(url=track.thumbnail)
                
                if state["current_message"]:
                    try:
                        await state["current_message"].delete()
                    except discord.errors.NotFound:
                        pass
                    except Exception as e:
                        print(f"Mesaj silme hatası: {e}")
                
                try:
                    state["current_message"] = await interaction.channel.send(embed=embed, view=view)
                except Exception as e:
                    print(f"Mesaj gönderme hatası: {e}")
                    state["current_message"] = None
                    
            except wavelink.LavalinkException as e:
                print(f"Wavelink play hatası: {e}")
                # Bu şarkı oynatılamazsa bir sonrakini dene
                if state["queue"]:
                    await self.play_next(interaction)
                else:
                    state["is_playing"] = False
                    if player and player.connected:
                        await player.disconnect()
            except Exception as e:
                print(f"Play next genel hatası: {e}")
                if state["queue"]:
                    await self.play_next(interaction)
                else:
                    state["is_playing"] = False
                    if player and player.connected:
                        await player.disconnect()
        else:
            state["is_playing"] = False
            if player and player.connected:
                try:
                    await player.disconnect()
                except Exception as e:
                    print(f"Disconnect hatası: {e}")
            if state["current_message"]:
                try:
                    await state["current_message"].delete()
                except discord.errors.NotFound:
                    pass
                except Exception as e:
                    print(f"Mesaj silme hatası: {e}")
                finally:
                    state["current_message"] = None

    async def button_queue_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild.id)
        if not interaction.guild.voice_client:
            await interaction.followup.send("Bot bir ses kanalında değil!", ephemeral=True)
            return
        if not state["queue"]:
            await interaction.followup.send("Sırada şarkı yok!", ephemeral=True)
            return
        embed = discord.Embed(title="🎵 Çalma Listesi", color=discord.Color.blue())
        if state["current_player"]:
            embed.add_field(name="Şimdi Çalıyor", value=f"▶️ {state['current_player'].title}", inline=False)
        queue_text = ""
        for idx, song in enumerate(state["queue"], 1):
            queue_text += f"{idx}. {song.title}\n"
            if idx % 10 == 0:
                embed.add_field(name=f"Sıradaki Şarkılar ({idx-9}-{idx})", value=queue_text, inline=False)
                queue_text = ""
        if queue_text:
            embed.add_field(name="Sıradaki Şarkılar", value=queue_text, inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)

    async def button_pause_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        msg_content = ""
        if interaction.guild.voice_client and interaction.guild.voice_client.playing:
            await interaction.guild.voice_client.pause()
            msg_content = "⏸️ Şarkı duraklatıldı"
        elif interaction.guild.voice_client and interaction.guild.voice_client.paused:
            await interaction.guild.voice_client.resume()
            msg_content = "▶️ Şarkı devam ediyor"
        
        if msg_content:
            msg = await interaction.followup.send(msg_content, ephemeral=True)
            self.bot.loop.create_task(self._delete_message_after(msg, 10))

    async def button_skip_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.stop()
            msg = await interaction.followup.send("⏭️ Şarkı geçildi", ephemeral=True)
            self.bot.loop.create_task(self._delete_message_after(msg, 10))

    async def button_stop_callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        state = self.get_guild_state(interaction.guild.id)
        if interaction.guild.voice_client:
            state["queue"].clear()
            await interaction.guild.voice_client.disconnect()
            state["is_playing"] = False
            
            msg = await interaction.followup.send("⏹️ Müzik durduruldu", ephemeral=True)
            self.bot.loop.create_task(self._delete_message_after(msg, 10))

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
            if await self.is_favorite(user_id, current_song.uri, guild_id):
                await self.remove_favorite(user_id, current_song.uri, guild_id)
                await interaction.followup.send("💔 Şarkı favorilerden çıkarıldı!", ephemeral=True)
            else:
                await self.add_favorite(user_id, guild_id, current_song.title, current_song.uri)
                await interaction.followup.send("❤️ Şarkı favorilere eklendi!", ephemeral=True)
        except Exception as e:
            print(f"Favori işlemi hatası: {e}")
            try:
                await interaction.followup.send("Bir hata oluştu.", ephemeral=True)
            except:
                pass

    @discord.app_commands.command(name="cal", description="Şarkı çalar")
    @discord.app_commands.describe(sarki="Şarkı adı veya URL")
    async def slash_cal(self, interaction: discord.Interaction, sarki: str):
        state = self.get_guild_state(interaction.guild.id)
        
        await interaction.response.defer()
        
        try:
            channel = interaction.user.voice.channel
            if not interaction.guild.voice_client:
                player: wavelink.Player = await channel.connect(cls=wavelink.Player)
                state["caller"] = interaction.user
            elif interaction.guild.voice_client.channel != channel:
                await interaction.followup.send(
                    f"Şu anda başka bir kanalda bulunuyorum ({interaction.guild.voice_client.channel.name}). Müsait olunca tekrar çağırın.", 
                    ephemeral=True
                )
                return
            else:
                player = interaction.guild.voice_client
        except AttributeError:
            await interaction.followup.send("Bir ses kanalında değilsiniz.", ephemeral=True)
            return

        # Defer ettikten sonra followup kullan
        loading_message = await interaction.followup.send(f"🎶 **{sarki}** aranıyor...")

        async def delete_message(message, delay):
            await asyncio.sleep(delay)
            try:
                await message.delete()
            except discord.errors.NotFound:
                pass

        try:
            tracks: wavelink.Search = await wavelink.Playable.search(sarki)
            if not tracks:
                await loading_message.edit(content="❌ Şarkı bulunamadı.")
                self.bot.loop.create_task(delete_message(loading_message, 30))
                return

            # Playlist kontrolü
            if isinstance(tracks, wavelink.Playlist):
                async with state["queue_lock"]:
                    state["queue"].extend(tracks.tracks)
                
                await loading_message.edit(content=f"✅ Playlist sıraya eklendi. **{len(tracks.tracks)}** şarkı.")
            else:
                track = tracks[0]
                async with state["queue_lock"]:
                    state["queue"].append(track)

                await loading_message.edit(content=f"✅ **{track.title}** sıraya eklendi.")

            self.bot.loop.create_task(delete_message(loading_message, 30))

            if not player.playing and not player.paused:
                await self.play_next(interaction)
                
        except Exception as e:
            await loading_message.edit(content=f"❌ Şarkı bilgisi alınırken bir hata oluştu.")
            self.bot.loop.create_task(delete_message(loading_message, 30))
            print(f"Error in slash_cal: {e}")
            return
            
    def get_control_buttons(self, interaction):
        view = discord.ui.View(timeout=None) 
        
        stop_button = Button(emoji="⏹️", style=discord.ButtonStyle.danger, custom_id="music_stop")
        stop_button.callback = self.button_stop_callback

        pause_button = Button(emoji="⏯️", style=discord.ButtonStyle.primary, custom_id="music_pause")
        pause_button.callback = self.button_pause_callback

        skip_button = Button(emoji="⏭️", style=discord.ButtonStyle.primary, custom_id="music_skip") 
        skip_button.callback = self.button_skip_callback

        queue_button = Button(emoji="📋", style=discord.ButtonStyle.secondary, custom_id="music_queue")
        queue_button.callback = self.button_queue_callback

        favorite_button = Button(emoji="❤️", style=discord.ButtonStyle.success, custom_id="music_favorite")
        favorite_button.callback = self.button_favorite_callback

        view.add_item(stop_button)
        view.add_item(pause_button)
        view.add_item(skip_button)
        view.add_item(queue_button)
        view.add_item(favorite_button)

        return view

    @discord.app_commands.command(name="siradakiler", description="Sıradaki şarkıları gösterir")
    async def slash_siradakiler(self, interaction: discord.Interaction):
        state = self.get_guild_state(interaction.guild.id)
        if interaction.guild.voice_client and interaction.guild.voice_client.connected:
            if state["queue"]:
                pages = []
                max_chars = 1024
                current_message = ""
                for idx, track in enumerate(state["queue"]):
                    next_entry = f"{idx + 1}. {track.title}\n"
                    if len(current_message) + len(next_entry) > max_chars:
                        pages.append(current_message)
                        current_message = next_entry
                    else:
                        current_message += next_entry
                if current_message:
                    pages.append(current_message)

                current_page = 0
                embed = discord.Embed(title="Sıradaki Şarkılar", description=pages[current_page], color=discord.Color.blue())

                await interaction.response.send_message(embed=embed, view=QueueView(pages), ephemeral=True)
            else:
                await interaction.response.send_message("Sırada şarkı yok.", ephemeral=True, delete_after=30)
        else:
            await interaction.response.send_message("Bot bir ses kanalında değil.", ephemeral=True, delete_after=30)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.id != self.bot.user.id:
            return

        state = self.get_guild_state(member.guild.id)
        if before.channel is not None and after.channel is None:
            state["queue"].clear()
            state["is_playing"] = False
            if state["current_message"]:
                try:
                    await state["current_message"].delete()
                except discord.errors.NotFound:
                    pass
                finally:
                    state["current_message"] = None
            
            if member.guild.voice_client:
                try:
                    await member.guild.voice_client.disconnect()
                except Exception as e:
                    print(f"Error disconnecting in on_voice_state_update: {e}")

    def get_voice_state(self, guild):
        if guild.voice_client:
            return guild.voice_client.channel
        return None

    @tasks.loop(minutes=5)
    async def check_voice_channel(self):
        for guild_id, state in self.guild_states.items():
            guild = self.bot.get_guild(guild_id)
            if guild and guild.voice_client and guild.voice_client.connected:
                voice_channel = guild.voice_client.channel
                if voice_channel:
                    # Bot dışında kanaldaki kullanıcıları bul
                    human_members = [m for m in voice_channel.members if not m.bot]
                    
                    player = guild.voice_client
                    
                    if human_members:
                        # Kullanıcı varsa zaman damgasını güncelle
                        state["last_user_activity"] = datetime.datetime.now()
                    else:
                        # Kullanıcı yoksa ve 10 dakikadan uzun süredir yalnızsa ayrıl
                        if (datetime.datetime.now() - state["last_user_activity"]).total_seconds() > 600:
                            # Botun hala müzik çalıp çalmadığını kontrol et
                            if not player.playing and not state["queue"]:
                                # Kanalı terk ettiğini belirten bir mesaj gönder
                                try:
                                    channel_to_send = self.get_guild_state(guild_id)["current_message"].channel
                                    message = await channel_to_send.send("Kanalda kimse kalmadı. Ayrılıyorum...")
                                    
                                    # 1 dakika sonra mesajı sil
                                    await asyncio.sleep(60)
                                    await message.delete()
                                except (AttributeError, discord.errors.NotFound):
                                    # Mesaj gönderilemezse hata vermeden devam et
                                    pass

                                await player.disconnect()
                                
                                # Durumu ve kuyruğu temizle
                                state["queue"].clear()
                                state["is_playing"] = False
                                state["current_player"] = None
                                if state["current_message"]:
                                    try:
                                        await state["current_message"].delete()
                                    except discord.errors.NotFound:
                                        pass
                                    finally:
                                        state["current_message"] = None

    @check_voice_channel.before_loop
    async def before_check_voice_channel(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        pass

    def cog_unload(self):
        for vc in self.bot.voice_clients:
            self.bot.loop.create_task(vc.disconnect(force=True))
        
        if hasattr(self, 'queue'):
            self.queue.clear()

    async def add_favorite(self, user_id: str, guild_id: str, song_title: str, song_url: str):
        async with aiosqlite.connect('database/economy.db') as db:
            await db.execute ('''INSERT OR REPLACE INTO favorite_songs 
                (user_id, guild_id, song_title, song_url) 
                VALUES (?, ?, ?, ?)''', (user_id, guild_id, song_title, song_url))
            await db.commit()

    async def remove_favorite(self, user_id: str, song_url: str, guild_id: str):
        async with aiosqlite.connect('database/economy.db') as db:
            await db.execute ('''DELETE FROM favorite_songs 
                WHERE user_id = ? AND song_url = ? AND guild_id = ?''', (user_id, song_url, guild_id))
            await db.commit()

    async def get_favorites(self, user_id: str, guild_id: str):
        try:
            async with aiosqlite.connect('database/economy.db') as db:
                async with db.execute ('''SELECT song_title, song_url 
                    FROM favorite_songs 
                    WHERE user_id = ? AND guild_id = ?
                    ORDER BY added_at DESC''', (user_id, guild_id)) as cursor:
                    return await cursor.fetchall()
        except Exception as e:
            print(f"Veritabanı hatası (get_favorites): {e}")
            return []

    async def is_favorite(self, user_id: str, song_url: str, guild_id: str):
        async with aiosqlite.connect('database/economy.db') as db:
            async with db.execute ('''SELECT 1 FROM favorite_songs 
                WHERE user_id = ? AND song_url = ? AND guild_id = ?''', (user_id, song_url, guild_id)) as cursor:
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
        if await self.is_favorite(user_id, current_song.uri, guild_id):
            await self.remove_favorite(user_id, current_song.uri, guild_id)
            await interaction.response.send_message("💔 Şarkı favorilerden çıkarıldı!", ephemeral=True)
        else:
            await self.add_favorite(user_id, guild_id, current_song.title, current_song.uri)
            await interaction.response.send_message("❤️ Şarkı favorilere eklendi!", ephemeral=True)

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
            
            # Sayfa oluşturma mantığı
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
                # Mesajı ephemeral olarak gönderdikten sonra nesnesini al
                message = await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)
                view.message = message  # Bu, view nesnesinin mesajı takip etmesini sağlar
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
            if not interaction.guild.voice_client:
                player = await channel.connect(cls=wavelink.Player)
                state = self.get_guild_state(interaction.guild.id)
                state["caller"] = interaction.user
            elif interaction.guild.voice_client.channel != channel:
                await interaction.response.send_message(
                    f"🔒 Bot şu anda başka bir ses kanalında: **{interaction.guild.voice_client.channel.name}**",
                    ephemeral=True
                )
                return
            else:
                player = interaction.guild.voice_client
        except AttributeError:
            await interaction.response.send_message("📢 Lütfen önce bir ses kanalına katılın.", ephemeral=True)
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
                tracks = await wavelink.Playable.search(url)
                if not tracks:
                    tracks = await wavelink.Playable.search(f"ytsearch:{title}")
                if not tracks:
                    tracks = await wavelink.Playable.search(f"ytmsearch:{title}")
                
                if tracks:
                    track = tracks[0] if not isinstance(tracks, wavelink.Playlist) else tracks.tracks[0]
                    async with state["queue_lock"]:
                        state["queue"].append(track)
                    songs_added += 1
                else:
                    failed_songs.append(title)
            except Exception as e:
                print(f"Yüklenemeyen favori: {title} ({url}) -> {e}")
                failed_songs.append(title)

        if songs_added > 0:
            if not player.playing and not player.paused:
                await self.play_next(interaction)
                
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

            # Mesajı gönder ve 60 saniye sonra sil
            sent_message = await interaction.followup.send(embed=embed)
            self.bot.loop.create_task(self._delete_message_after(sent_message, 60))

        else:
            message = await interaction.followup.send(
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
            await self.remove_favorite(user_id, selected_song[1], guild_id)
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
                await db.execute ('''
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
    def __init__(self, pages, timeout=120):
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
        try:
            if self.message:
                await self.message.edit(view=self)
        except discord.errors.NotFound:
            pass

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