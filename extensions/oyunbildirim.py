from config import API_KEY
import aiohttp
import discord
from discord.ext import commands, tasks
import aiosqlite
from datetime import datetime, timedelta
import json
import os
import aiofiles
import asyncio
import logging

API_URL = 'https://api.isthereanydeal.com/deals/v2'
JSON_FILE = 'json/indirim.json'
logging.basicConfig(level=logging.ERROR)

class Oyunbildirim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_deals.start()
        self.clear_old_deals.start()
        self.daily_json_reset.start()
        self.bot.loop.create_task(self.init_db())
        

    async def init_db(self):
        try:
            self.conn = await aiosqlite.connect('database/indirim.db')
            self.c = await self.conn.cursor()
            
            # Önce mevcut tabloları kontrol et
            await self.c.execute("PRAGMA table_info(GameNotifyChannels)")
            columns = await self.c.fetchall()
            existing_columns = [column[1] for column in columns]
            
            # Eğer tablo yoksa oluştur
            if not existing_columns:
                await self.c.execute('''
                    CREATE TABLE IF NOT EXISTS GameNotifyChannels (
                        guild_id TEXT NOT NULL,
                        channel_id TEXT NOT NULL,
                        bildirim_sakligi INTEGER DEFAULT 60,
                        aktif BOOLEAN DEFAULT 1,
                        son_bildirim TIMESTAMP,
                        PRIMARY KEY (guild_id, channel_id)
                    )
                ''')
            else:
                # Yeni sütunları ekle
                if 'bildirim_sakligi' not in existing_columns:
                    await self.c.execute('ALTER TABLE GameNotifyChannels ADD COLUMN bildirim_sakligi INTEGER DEFAULT 60')
                    print("Sütun eklendi: bildirim_sakligi")
                
                if 'aktif' not in existing_columns:
                    await self.c.execute('ALTER TABLE GameNotifyChannels ADD COLUMN aktif BOOLEAN DEFAULT 1')
                    print("Sütun eklendi: aktif")
                
                if 'son_bildirim' not in existing_columns:
                    await self.c.execute('ALTER TABLE GameNotifyChannels ADD COLUMN son_bildirim TIMESTAMP')
                    print("Sütun eklendi: son_bildirim")
            
            # PostedDeals tablosu
            await self.c.execute('''
                CREATE TABLE IF NOT EXISTS PostedDeals (
                    title TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    new_price REAL,
                    old_price REAL,
                    discount INTEGER,
                    store TEXT,
                    url TEXT,
                    last_shared TIMESTAMP NOT NULL,
                    PRIMARY KEY (title, guild_id, channel_id)
                )
            ''')
            
            await self.conn.commit()
            print("Oyun bildirim database güncellendi.")
            
        except Exception as e:
            print(f"Database initialization error: {e}")
            logging.error(f"Oyun bildirim DB hatası: {e}")

    def cog_unload(self):
        try:
            self.check_deals.cancel()
            self.clear_old_deals.cancel()
            self.daily_json_reset.cancel()
            if hasattr(self, 'conn') and self.conn:
                asyncio.create_task(self.conn.close())
            print("Oyun bildirim cog unloaded.")
        except Exception as e:
            print(f"Cog unload error: {e}")
            logging.error(f"Oyun bildirim cog unload hatası: {e}")

    async def cog_check(self, ctx):
        # Interaction ve Context her ikisini de destekle
        if hasattr(ctx, 'user'):  # Interaction
            return ctx.user.guild_permissions.administrator
        else:  # Context
            return ctx.author.guild_permissions.administrator

    @discord.app_commands.command(name="oyunbildirimac", description="Belirtilen kanalda oyun bildirimlerini açar")
    @discord.app_commands.describe(
        kanal="Bildirimlerin gönderileceği kanal",
        siklik="Bildirim sıklığı (dakika): 30, 60, 120, 180, 360 (varsayılan: 60)"
    )
    @commands.has_permissions(administrator=True)
    async def oyunbildirimac(self, interaction: discord.Interaction, 
                            kanal: discord.TextChannel, 
                            siklik: int = 60):
        
        # Geçerli sıklık değerleri
        gecerli_sikliklar = [15, 30, 60, 120, 180, 360, 720, 1440]  # 15dk - 24 saat
        
        if siklik not in gecerli_sikliklar:
            await interaction.response.send_message(
                f"❌ Geçersiz sıklık! Geçerli değerler: {', '.join(map(str, gecerli_sikliklar))} dakika", 
                ephemeral=True
            )
            return

        await self.c.execute('''
            INSERT OR REPLACE INTO GameNotifyChannels 
            (guild_id, channel_id, bildirim_sakligi, aktif, son_bildirim) 
            VALUES (?, ?, ?, ?, ?)
        ''', (interaction.guild.id, kanal.id, siklik, True, datetime.now()))
        
        await self.conn.commit()
        
        # Sıklık açıklaması
        if siklik < 60:
            siklik_text = f"{siklik} dakika"
        elif siklik < 1440:
            siklik_text = f"{siklik // 60} saat"
        else:
            siklik_text = f"{siklik // 1440} gün"
            
        embed = discord.Embed(
            title="✅ Oyun Bildirimleri Açıldı!",
            description=f"📢 **Kanal:** {kanal.mention}\n⏰ **Sıklık:** {siklik_text}\n🎮 İndirimdeki oyunlar düzenli olarak paylaşılacak!",
            color=0x00ff00
        )
        embed.set_footer(text="Ayarları değiştirmek için /oyunbildirimayar komutunu kullanın")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.app_commands.command(name="oyunbildirimayar", description="Oyun bildirim ayarlarını değiştir")
    @discord.app_commands.describe(
        siklik="Yeni bildirim sıklığı (dakika): 15, 30, 60, 120, 180, 360, 720, 1440",
        durum="Bildirimleri aç/kapat (True/False)"
    )
    @commands.has_permissions(administrator=True)
    async def oyunbildirimayar(self, interaction: discord.Interaction, 
                              siklik: int = None, 
                              durum: bool = None):
        
        # Mevcut ayarları kontrol et
        await self.c.execute('''
            SELECT channel_id, bildirim_sakligi, aktif 
            FROM GameNotifyChannels 
            WHERE guild_id = ?
        ''', (interaction.guild.id,))
        
        result = await self.c.fetchone()
        if not result:
            await interaction.response.send_message("❌ Bu sunucuda aktif oyun bildirimi bulunamadı!", ephemeral=True)
            return

        channel_id, mevcut_siklik, mevcut_durum = result
        
        # Yeni değerleri belirle
        yeni_siklik = siklik if siklik is not None else mevcut_siklik
        yeni_durum = durum if durum is not None else bool(mevcut_durum)
        
        # Geçerli sıklık kontrolü
        if siklik is not None:
            gecerli_sikliklar = [15, 30, 60, 120, 180, 360, 720, 1440]
            if siklik not in gecerli_sikliklar:
                await interaction.response.send_message(
                    f"❌ Geçersiz sıklık! Geçerli değerler: {', '.join(map(str, gecerli_sikliklar))} dakika", 
                    ephemeral=True
                )
                return

        # Ayarları güncelle
        await self.c.execute('''
            UPDATE GameNotifyChannels 
            SET bildirim_sakligi = ?, aktif = ?
            WHERE guild_id = ?
        ''', (yeni_siklik, yeni_durum, interaction.guild.id))
        
        await self.conn.commit()
        
        # Sonuç mesajı
        kanal = self.bot.get_channel(channel_id)
        
        if yeni_siklik < 60:
            siklik_text = f"{yeni_siklik} dakika"
        elif yeni_siklik < 1440:
            siklik_text = f"{yeni_siklik // 60} saat"
        else:
            siklik_text = f"{yeni_siklik // 1440} gün"
            
        durum_text = "🟢 Aktif" if yeni_durum else "🔴 Kapalı"
        
        embed = discord.Embed(
            title="⚙️ Oyun Bildirim Ayarları Güncellendi!",
            color=0x0099ff
        )
        embed.add_field(name="📢 Kanal", value=kanal.mention if kanal else "Kanal bulunamadı", inline=True)
        embed.add_field(name="⏰ Sıklık", value=siklik_text, inline=True)
        embed.add_field(name="📊 Durum", value=durum_text, inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.app_commands.command(name="oyunbildirimdurum", description="Oyun bildirim ayarlarını görüntüle")
    @commands.has_permissions(administrator=True)
    async def oyunbildirimdurum(self, interaction: discord.Interaction):
        await self.c.execute('''
            SELECT channel_id, bildirim_sakligi, aktif, son_bildirim 
            FROM GameNotifyChannels 
            WHERE guild_id = ?
        ''', (interaction.guild.id,))
        
        result = await self.c.fetchone()
        if not result:
            await interaction.response.send_message("❌ Bu sunucuda aktif oyun bildirimi bulunamadı!", ephemeral=True)
            return

        channel_id, siklik, aktif, son_bildirim = result
        
        # GELİŞTİRİLMİŞ KANAL BULMA
        channel = None
        kanal_durumu = "❌ Bulunamadı"
        
        try:
            # Yöntem 1: Cache'den al
            channel = self.bot.get_channel(int(channel_id))
            
            # Yöntem 2: Guild'den al
            if not channel:
                channel = interaction.guild.get_channel(int(channel_id))
            
            # Yöntem 3: API'den çek
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(int(channel_id))
                except:
                    pass
            
            if channel:
                # Yetki kontrolü
                perms = channel.permissions_for(interaction.guild.me)
                if perms.send_messages:
                    kanal_durumu = f"✅ {channel.mention}"
                else:
                    kanal_durumu = f"⚠️ {channel.mention} (Yetki yok)"
            else:
                kanal_durumu = f"❌ Kanal silinmiş (ID: {channel_id})"
                
        except Exception as e:
            kanal_durumu = f"❌ Hata: {str(e)[:50]}"
        
        # Sıklık metni
        if siklik < 60:
            siklik_text = f"{siklik} dakika"
        elif siklik < 1440:
            siklik_text = f"{siklik // 60} saat"
        else:
            siklik_text = f"{siklik // 1440} gün"
            
        durum_text = "🟢 Aktif" if aktif else "🔴 Kapalı"
        
        # Son bildirim zamanı
        if son_bildirim:
            try:
                if isinstance(son_bildirim, str):
                    son_bildirim_dt = datetime.fromisoformat(son_bildirim)
                else:
                    son_bildirim_dt = son_bildirim
                son_bildirim_text = f"<t:{int(son_bildirim_dt.timestamp())}:R>"
            except:
                son_bildirim_text = "Bilinmiyor"
        else:
            son_bildirim_text = "Henüz bildirim gönderilmedi"
        
        # Sonraki bildirim tahmini
        if aktif and son_bildirim and channel:
            try:
                sonraki_bildirim = son_bildirim_dt + timedelta(minutes=siklik)
                if sonraki_bildirim > datetime.now():
                    sonraki_bildirim_text = f"<t:{int(sonraki_bildirim.timestamp())}:R>"
                else:
                    sonraki_bildirim_text = "Şimdi (bir sonraki kontrol döngüsünde)"
            except:
                sonraki_bildirim_text = "Bilinmiyor"
        else:
            sonraki_bildirim_text = "Belirsiz"
        
        embed = discord.Embed(
            title="📊 Oyun Bildirim Durumu",
            color=0x00ff00 if aktif else 0xff0000
        )
        
        embed.add_field(name="📢 Kanal", value=kanal_durumu, inline=False)
        embed.add_field(name="⏰ Bildirim Sıklığı", value=siklik_text, inline=True)
        embed.add_field(name="📊 Durum", value=durum_text, inline=True)
        embed.add_field(name="📅 Son Bildirim", value=son_bildirim_text, inline=True)
        embed.add_field(name="⏭️ Sonraki Bildirim", value=sonraki_bildirim_text, inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.app_commands.command(name="oyunbildirimkapat", description="Oyun bildirimlerini kapatır")
    @commands.has_permissions(administrator=True)
    async def oyunbildirimkapat(self, interaction: discord.Interaction):
        await self.c.execute('DELETE FROM GameNotifyChannels WHERE guild_id = ?', (interaction.guild.id,))
        deleted_rows = self.c.rowcount
        await self.conn.commit()
        
        if deleted_rows > 0:
            embed = discord.Embed(
                title="❌ Oyun Bildirimleri Kapatıldı",
                description="Bu sunucudaki tüm oyun bildirimleri kapatıldı.",
                color=0xff0000
            )
        else:
            embed = discord.Embed(
                title="ℹ️ Bilgi",
                description="Bu sunucuda zaten aktif oyun bildirimi bulunmuyor.",
                color=0xffaa00
            )
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def load_deals_from_api(self):
        params = {
            'key': API_KEY,
            'country': 'TR',
            'limit': 200,
            'sort': 'rank',
            'mature': 'false'
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, params=params) as response:
                    response.raise_for_status()
                    data = await response.json()
                    deals = data.get('list', [])
                    if not deals:
                        print("API'den oyun verisi alınamadı.")
                        return
                    
                    # JSON klasörünün var olduğundan emin ol
                    os.makedirs('json', exist_ok=True)
                    
                    async with aiofiles.open(JSON_FILE, 'w', encoding='utf-8') as f:
                        await f.write(json.dumps(deals, ensure_ascii=False, indent=2))
                    print(f"{len(deals)} indirimli oyun JSON dosyasına kaydedildi.")
        except aiohttp.ClientError as e:
            print(f"API isteğinde hata oluştu: {e}")
            logging.error(f"API isteği hatası: {e}")
        except Exception as e:
            print(f"Beklenmeyen hata (load_deals_from_api): {e}")
            logging.error(f"Load deals beklenmeyen hata: {e}")

    async def load_deals_from_file(self):
        try:
            if not os.path.exists(JSON_FILE):
                await self.load_deals_from_api()
            
            if os.path.exists(JSON_FILE):
                async with aiofiles.open(JSON_FILE, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    return json.loads(content)
            else:
                print("JSON dosyası oluşturulamadı.")
                return []
        except Exception as e:
            print(f"JSON dosyası okuma hatası: {e}")
            logging.error(f"JSON okuma hatası: {e}")
            return []

    @tasks.loop(minutes=5.0)
    async def check_deals(self):
        try:
            if not hasattr(self, 'conn') or not self.conn:
                return
                
            deals = await self.load_deals_from_file()
            if not deals:
                print("No deals available to check.")
                return
            
            # Aktif kanalları al
            await self.c.execute('''
                SELECT guild_id, channel_id, bildirim_sakligi, son_bildirim 
                FROM GameNotifyChannels 
                WHERE aktif = 1
            ''')
            channels = await self.c.fetchall()

            for guild_id, channel_id, siklik, son_bildirim in channels:
                try:
                    # Zaman kontrolü
                    if son_bildirim:
                        son_bildirim_dt = datetime.fromisoformat(son_bildirim)
                        gecen_dakika = (datetime.now() - son_bildirim_dt).total_seconds() / 60
                        
                        if gecen_dakika < siklik:
                            continue
                    
                    # Uygun oyun bul
                    for deal in deals:
                        title = deal.get('title')
                        deal_data = deal.get('deal', {})
                        price_data = deal_data.get('price', {})
                        regular_data = deal_data.get('regular', {})
                        shop_data = deal_data.get('shop', {})
                        
                        new_price = price_data.get('amount')
                        old_price = regular_data.get('amount')
                        discount = deal_data.get('cut', 0)
                        store = shop_data.get('name')
                        url = deal_data.get('url')
                        
                        # Banner URL
                        assets = deal.get('assets', {})
                        banner_url = assets.get('banner400') or assets.get('banner300') or assets.get('boxart')

                        if not all([title, new_price, old_price, discount, store, url]):
                            continue

                        if discount < 50:  # Minimum %50 indirim
                            continue

                        if not await self.check_if_deal_exists_for_guild(title, guild_id):
                            now = datetime.now()
                            await self.notify_channel_with_banner(
                                guild_id, channel_id, title, new_price, old_price, 
                                discount, store, url, banner_url, now
                            )
                            
                            # Zamanı güncelle
                            await self.c.execute('''
                                UPDATE GameNotifyChannels 
                                SET son_bildirim = ? 
                                WHERE guild_id = ? AND channel_id = ?
                            ''', (now, guild_id, channel_id))
                            await self.conn.commit()
                            
                            print(f"✅ Oyun bildirimi gönderildi: {title} (%{discount}) -> Guild: {guild_id}")
                            break
                            
                except Exception as e:
                    print(f"Error processing guild_id: {guild_id}, error: {e}")
                    
        except Exception as e:
            print(f"Error in check_deals loop: {e}")
            logging.error(f"Check deals loop hatası: {e}")

    async def notify_channel_with_banner(self, guild_id, channel_id, title, new_price, old_price, discount, store, url, banner_url, now):
        try:
            # Kanal bulma
            channel = None
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                guild = self.bot.get_guild(int(guild_id))
                if guild:
                    channel = guild.get_channel(int(channel_id))
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(int(channel_id))
                except:
                    pass

            if not channel:
                print(f"❌ Kanal bulunamadı: {channel_id}")
                await self.c.execute('DELETE FROM GameNotifyChannels WHERE guild_id = ? AND channel_id = ?', 
                                    (guild_id, channel_id))
                await self.conn.commit()
                return

            if not channel.permissions_for(channel.guild.me).send_messages:
                print(f"❌ Mesaj gönderme yetkisi yok: {channel.name}")
                return

            profit = old_price - new_price
            profit = round(profit, 2)

            # TEMİZ EMBED TASARIMI
            embed = discord.Embed(
                title=f"🎮 {title}",
                description=f"🔥 **%{discount} İndirim!**\n💰 **{old_price} ₺** → **{new_price} ₺**\n💸 **{profit} ₺ tasarruf!**",
                color=self.get_clean_color(discount),
                url=url
            )
            
            # Ana banner resmi
            if banner_url:
                embed.set_image(url=banner_url)
            
            # İnline field'lar - yan yana 3 tane
            embed.add_field(
                name="💰 Fiyat Detayları",
                value=f"**Şu an:** `{new_price} ₺` 🔻\n**Önceden:** `{old_price} ₺` 🔺\n**Tasarruf:** `{profit} ₺` 💸",
                inline=True
            )
            
            embed.add_field(
                name="🏪 Mağaza",
                value=f"**{store.upper()}**",
                inline=True
            )
            
            embed.add_field(
                name="📊 İndirim",
                value=f"**%{discount}**",
                inline=True
            )
            
            # Progress bar - tam genişlik
            progress_bar = self.create_clean_progress_bar(discount)
            embed.add_field(
                name="📊 İndirim Seviyesi",
                value=progress_bar,
                inline=False
            )
            
            # Footer - saat, tarih, bot
            turkey_time = now + timedelta(hours=3)
            embed.set_footer(
                text=f"🕐 {turkey_time.strftime('%H:%M')} • 📅 {turkey_time.strftime('%d.%m.%Y')} • 🤖 Çaycı Bot",
                icon_url="https://cdn.discordapp.com/emojis/851461487498821652.png"
            )
            
            await channel.send(embed=embed)
            await self.save_deal(title, guild_id, channel_id, new_price, old_price, discount, store, url, now)
            print(f"✅ Banner bildirimi gönderildi: {title} -> {channel.name}")

        except Exception as e:
            print(f"❌ Banner bildirim hatası: {e}")
            import traceback
            traceback.print_exc()

    def get_clean_color(self, discount):
        """Temiz renk paleti"""
        if discount >= 70:
            return 0x2ecc71    # Yeşil
        elif discount >= 50:
            return 0xf39c12    # Turuncu
        elif discount >= 30:
            return 0x3498db    # Mavi 
        else:
            return 0x9b59b6    # Mor

    def create_clean_progress_bar(self, discount):
        """Temiz progress bar"""
        filled = discount // 10
        empty = 10 - filled
        
        # Renk seçimi
        if discount >= 70:
            bar_emoji = "🟩"  # Yeşil
            level_text = "Harika İndirim"
        elif discount >= 50:
            bar_emoji = "🟨"  # Sarı
            level_text = "İyi İndirim"
        elif discount >= 30:
            bar_emoji = "🟦"  # Mavi
            level_text = "Orta İndirim"
        else:
            bar_emoji = "🟪"  # Mor
            level_text = "Standart İndirim"
        
        # Bar oluştur
        progress_bar = bar_emoji * filled + "⬜" * empty
        return f"{progress_bar} **{discount}%**"

    @tasks.loop(hours=24)
    async def daily_json_reset(self):
        print("Günlük JSON sıfırlanıyor...")
        if os.path.exists(JSON_FILE):
            os.remove(JSON_FILE)
        await self.load_deals_from_api()
        print("JSON dosyası sıfırlandı ve yeniden dolduruldu.")

    @daily_json_reset.before_loop
    async def before_daily_json_reset(self):
        await self.bot.wait_until_ready()
        now = datetime.now()
        next_run = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        await discord.utils.sleep_until(next_run)

    async def check_if_deal_exists_for_guild(self, title, guild_id):
        await self.c.execute("SELECT 1 FROM PostedDeals WHERE title = ? AND guild_id = ?", (title, guild_id))
        result = await self.c.fetchone()
        return result is not None

    async def save_deal(self, title, guild_id, channel_id, new_price, old_price, discount, store, url, now):
        try:
            await self.c.execute('''
                INSERT INTO PostedDeals (title, guild_id, channel_id, new_price, old_price, discount, store, url, last_shared)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (title, guild_id, channel_id, new_price, old_price, discount, store, url, now))
            await self.conn.commit()
            print(f"Saved deal {title} to DB for guild {guild_id}, channel {channel_id}")
        except aiosqlite.IntegrityError:
            print(f"Deal {title} already exists in DB for guild {guild_id}, channel {channel_id}")

    @tasks.loop(hours=360)  # 15 günde bir
    async def clear_old_deals(self):
        await self.c.execute("DELETE FROM PostedDeals WHERE last_shared < DATETIME('now', '-15 days')")
        await self.conn.commit()
        print("Eski indirimler silindi.")

    @clear_old_deals.before_loop
    async def before_clear_old_deals(self):
        await self.bot.wait_until_ready()

    @check_deals.before_loop
    async def before_check_deals(self):
        await self.bot.wait_until_ready()
        # Database'in hazır olmasını bekle
        while not hasattr(self, 'conn') or not self.conn:
            await asyncio.sleep(1)
        await self.load_deals_from_api()
        print("Oyun bildirim check_deals loop started.")

async def setup(bot):
    await bot.add_cog(Oyunbildirim(bot))