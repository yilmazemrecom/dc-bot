from config import TOKEN
import discord
from discord.ext import commands, tasks
import aiosqlite
import os
import asyncio
from datetime import datetime
from util import init_db, update_user_server
import random
import wavelink

PREFIX = '!'

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix=PREFIX, 
    intents=intents,
    max_messages=1000,
    member_cache_flags=discord.MemberCacheFlags.none(),
    chunk_guilds_at_startup=False,
    heartbeat_timeout=120.0,
    enable_debug_events=False
)

# Botun başlangıç zamanını kaydet
bot.start_time = datetime.now()

# Bot hazır olduğunda çalışacak olay
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        os.makedirs('logs', exist_ok=True)
        os.makedirs('config', exist_ok=True)
        os.makedirs('backups', exist_ok=True)
        
        await init_db()
        
        # Görevleri başlat
        update_server_info.start()
        update_status.start(bot)
        
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error during bot startup: {e}")

# Botun aktivitesini dinamik olarak değiştirecek görevler
STATUS_MESSAGES = [
    "🎶 Müzik listesi hazırlıyor, kimse duymasın.",
    "🎧 En sevdiğiniz şarkıyı fısıldıyor.",
    "🎵 Komutlar için /komutlar yazın, yoksa çalmaya devam eder.",
    "💿 Eski kasetleri karıştırıyor...",
    "📢 Discord'u müzikle dolduruyor!",
    "🍵 Çay demliyor ve müzik dinliyor!",
    "🍵 Çaylaarr diye bağırıyor...",
    "Birazdan geliyorum, çay demliyorum...",
    "Bağış yapmak için mağazamızı ziyaret edin!",
    "🎶 Müzik dünyasında kaybolmuşum gibi hissediyorum...",
    "Dertleniyorum...",
    "Çaycı burada, keyifler yerinde!",
    "Bir türkü tutturmuş gidiyorum...",
    "Çayımı yudumlarken, en iyi şarkıları buluyorum.",
    "Müziği aç, çayları koy.",
    "Sessiz olun, en sevdiğiniz şarkı çalıyor.",
    "Çaycı size özel bir playlist hazırlıyor.",
    "Kanalda {queue_count} şarkı var, çaylar taze!",
    "Toplam {user_count} kişiyle en sevdiğim şarkıyı dinliyorum.",
    "Bugün de çay demledik, müziği açtık.",
    "Eski 45'likleri buldum, şimdiki gençler bilmez.",
    "🎮 Oyun indirimi beklerken çay içiyor...",
    "🕹️ Son boss'u kesmeye çalışıyor, rahatsız etmeyin.",
    "👾 En iyi strateji rehberlerini okuyor.",
    "🎯 'Sadece bir el daha' diyor...",
    "👾 Yeni çıkan oyunun metasını çözüyor.",
    "📈 Oyun fiyatlarını takip ediyor.",
    "🎮 Level kasmaktan yoruldu, bir şarkı molası veriyor.",
    "🍵 Oyunda AFK kaldı, çay demliyor.",
    "🔫 Rainbow'da Q-E yapmaktan boynum tutuldu.",
    "👾 CS'de aimim kaydı, çayımı yudumluyorum.",
    "🕹️ PUBG'de son 1 kişi kaldı, çayımı içerken bekliyorum.",
    "🎯 Valorant'ta ace attıktan sonra çay molası veriyor.",
    "Detroit'teki o kıza çok üzüldüm...",
    "Elden Ring'de Malenia'yı kesemedim, moralim bozuk.",
    "Witcher 3'te bir Gwent maçı yapmadan duramıyor.",
    "Geralt'ın çayını demlemiş, şarkı dinliyor.",
    "Stardew Valley'de ekinlerimi sularken şarkı çalıyor.",
    "Cyberpunk'ta V'nin şarkısını dinliyor.",
    "Babaaa! Ne diyon sen ya?",
    "Çaycı Hüseyin de mi oynamasın?",
    "Duygusal anlar yaşıyor, çay demlemeye devam ediyor.",
    "Ne oldu, yoksa çayınız mı bitti?",
    "Dardayım, anla beni...",
    "O long gözledi, ben de onu...",
    "Bir çay demlemişim, sanırsın müziğin tanrısı.",
    "Müziği açtım, çayları koydum, patron gelsin.",
    "☕ Gmod'da çayımı içerken prop'ları izliyor.",
    "🐉 Skyrim'de Fusu! Ro! Dah! diye bağırıyor.",
    "🏹 Hangi ok daha güçlü, yay mı çay mı?",
    "💥 Gta'da 5 yıldızla aranıyor, kaçarken şarkı dinliyor.",
    "🪓 Minecraft'ta odun kesmekten yoruldu, bir fincan çay molası verdi.",
]
@tasks.loop(minutes=2)
async def update_status(bot):
    try:
        selected_status = random.choice(STATUS_MESSAGES)
        
        if "{user_count}" in selected_status or "{queue_count}" in selected_status:
            async with aiosqlite.connect('database/economy.db') as db:
                async with db.execute('SELECT SUM(sunucu_uye_sayisi) FROM sunucular') as cursor:
                    row = await cursor.fetchone()
                    total_users = row[0] if row[0] is not None else 0
            
            total_queue_count = 0
            music_cog = bot.get_cog("Music")
            if music_cog:
                for guild in bot.guilds:
                    if guild.id in music_cog.guild_states:
                        state = music_cog.guild_states[guild.id]
                        total_queue_count += len(state["queue"])

            selected_status = selected_status.format(user_count=total_users, queue_count=total_queue_count)
            
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.listening,
                name=selected_status
            )
        )
        
    except Exception as e:
        print(f"Durum mesajı güncelleme hatası: {e}")

# Sunucu bilgilerini veritabanında güncelleyecek görev
@tasks.loop(hours=1)
async def update_server_info():
    sunucular = bot.guilds
    async with aiosqlite.connect('database/economy.db') as db:
        async with db.execute('SELECT sunucu_id FROM sunucular') as cursor:
            mevcut_sunucu_ids = [row[0] for row in await cursor.fetchall()]

        bot_sunucu_ids = [sunucu.id for sunucu in sunucular]
        
        silinecek_sunucu_ids = set(mevcut_sunucu_ids) - set(bot_sunucu_ids)
        if silinecek_sunucu_ids:
            await db.executemany('DELETE FROM sunucular WHERE sunucu_id = ?', 
                                 [(sunucu_id,) for sunucu_id in silinecek_sunucu_ids])
            print(f"{len(silinecek_sunucu_ids)} sunucu silindi.")

        for sunucu in sunucular:
            await db.execute('''
                INSERT OR REPLACE INTO sunucular (sunucu_id, sunucu_ismi, sunucu_uye_sayisi)
                VALUES (?, ?, ?)
            ''', (sunucu.id, sunucu.name, sunucu.member_count))
        
        await db.commit()
    print("Sunucu bilgileri güncellendi.")

# Görevler başlamadan önce botun hazır olmasını bekle
@update_server_info.before_loop
async def before_update_server_info():
    await bot.wait_until_ready()

@update_status.before_loop
async def before_update_status():
    await bot.wait_until_ready()

# Slash komutu olarak 'ping'
@bot.tree.command(name="ping", description="Bot gecikmesini gösterir")
async def slash_ping(interaction: discord.Interaction):
    import time
    start_time = time.perf_counter()
    
    embed = discord.Embed(
        title="🏓 Pong!",
        color=discord.Color.green()
    )
    
    websocket_ping = round(bot.latency * 1000, 2)
    embed.add_field(
        name="📡 WebSocket Gecikmesi",
        value=f"`{websocket_ping}ms`",
        inline=True
    )
    
    await interaction.response.send_message(embed=embed)
    
    end_time = time.perf_counter()
    response_time = round((end_time - start_time) * 1000, 2)
    
    embed.add_field(
        name="⚡ Yanıt Süresi",
        value=f"`{response_time}ms`",
        inline=True
    )
    
    status_color = discord.Color.green() if websocket_ping < 100 else discord.Color.orange() if websocket_ping < 200 else discord.Color.red()
    embed.color = status_color
    
    await interaction.edit_original_response(embed=embed)

# Slash komutu olarak 'komutlar'
@bot.tree.command(name="komutlar", description="Tüm komutları listeler")
async def komutlar(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 Çaycı Bot - Komut Listesi",
        description="Aşağıdaki komutları `/` ile kullanabilirsiniz\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
        color=discord.Color.blue()
    )

    music_commands = (
        "**`/cal`** • Şarkı çalar\n"
        "**`/siradakiler`** • Sıradaki şarkıları gösterir\n"
        "**`/favori`** • Şarkıyı favorilere ekler/çıkarır\n"
        "**`/favoriler`** • Favori listesini gösterir\n"
        "**`/favoricallist`** • Favorilerden şarkı çalar\n"
        "**`/favorisil`** • Favori şarkı siler\n"
        "**`/favoritümünüsil`** • Tüm favori şarkıları siler\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    )
    embed.add_field(
        name="🎵 Müzik Komutları", 
        value=music_commands, 
        inline=False
    )
    
    economy_commands = (
        "**`/bakiye`** • Bakiyenizi gösterir\n"
        "**`/btransfer`** • Para transferi yapar\n"
        "**`/siralama`** • En zenginleri listeler\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    )
    embed.add_field(
        name="💰 Ekonomi Komutları", 
        value=economy_commands, 
        inline=False
    )

    game_commands = (
        "🎲 **Kumar Oyunları**\n"
        "**`/zar`** • Zar atarsın\n"
        "**`/yazitura`** • Yazı tura atarsın\n"
        "**`/rulet`** • Rulet oynarsın\n"
        "**`/duello`** • Düello yaparsın\n\n"
        "⚽ **Takım Sistemi**\n"
        "**`/takimolustur`** • Takım kurarsın\n"
        "**`/macyap`** • Maç yaparsın\n"
        "**`/lig`** • Lig durumunu görürsün\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    )
    embed.add_field(
        name="🎮 Oyun Komutları", 
        value=game_commands, 
        inline=False
    )

    other_commands = (
        "🎯 **Mini Oyunlar**\n"
        "**`/bilmece`** • Bilmece çözersin\n"
        "**`/quiz`** • Quiz oynarsın\n\n"
        "🎉 **Çekiliş Sistemi**\n"
        "**`/cekilis_basla`** • Çekiliş başlatırsın\n"
        "**`/cekilis_bitir`** • Çekilişi erkenden bitirirsin\n"
        "**`/cekilisler`** • Aktif çekilişleri görürsün\n\n"
        "📢 **Bildirimler**\n"
        "**`/oyunbildirimac`** • İndirim bildirimleri\n"
        "⏰ **Hatırlatıcı**\n"
        "**`/hatirlatici_ekle`** • Hatırlatıcı eklersin\n"
        "**`/hatirlaticilar`** • Hatırlatıcıları görürsün\n"
        "🎮 **Oyun Seçim Sistemi**\n"
        "**`/oyunsecim`** • Kararsız kalanlar için oyun seçimi yapar\n"
    )
    embed.add_field(
        name="🎯 Eğlence & Diğer", 
        value=other_commands, 
        inline=False
    )

    embed.add_field(
        name="🔗 Bağlantılar",
        value=(
            "**[🌐 Web Sitemiz](https://caycibot.com.tr)**\n"
            "**[💬 Discord Sunucumuz](https://discord.gg/dSVRs26v5t)**"
        ),
        inline=False
    )
    
    embed.set_footer(
        text="Çaycı Bot - Geliştirici: Emre YILMAZ",
        icon_url=bot.user.display_avatar.url
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)

# Extensionları yükle
async def load_extensions():
    for extension in ['extensions.responses', 
                      'extensions.games', 
                      'extensions.economy', 
                      'extensions.takimoyunu', 
                      'extensions.music', 
                      'extensions.oyunbildirim', 
                      'extensions.duel', 
                      'extensions.reminder', 
                      'extensions.api_endpoints',
                      'extensions.oyunsecim'
                      ]:
        try:
            await bot.load_extension(extension)
            print(f"Extension '{extension}' loaded successfully.")
        except Exception as e:
            print(f"Failed to load extension {extension}: {e}")

async def cleanup():
    print("Temizlik işlemleri başlatılıyor...")

    # Wavelink Pool'u temizle ve bağlantıyı kes
    try:
        if wavelink.Pool.is_connected():
            await wavelink.Pool.disconnect()
            print("Wavelink nodes disconnected.")
    except Exception as e:
        print(f"Wavelink node'ları kapatılırken hata: {e}")

    # Tüm ses bağlantılarını kapat
    print("Ses bağlantıları kapatılıyor...")
    try:
        for vc in bot.voice_clients:
            await vc.disconnect(force=True)
        print("Tüm ses bağlantıları kapatıldı.")
    except Exception as e:
        print(f"Ses bağlantıları kapatma hatası: {e}")

    # Task loop'lar durdur
    print("Task loop'lar durduruluyor...")
    try:
        if 'update_server_info' in globals() and update_server_info.is_running():
            update_server_info.stop()
        if 'update_status' in globals() and update_status.is_running():
            update_status.stop()
        print("Task loop'lar durduruldu.")
    except Exception as e:
        print(f"Task loop durdurma hatası: {e}")

    # Extension'ları kapat
    print("Extension'lar kapatılıyor...")
    extensions = list(bot.extensions.keys())
    for extension in extensions:
        try:
            await bot.unload_extension(extension)
            print(f"{extension} kapatıldı")
        except Exception as e:
            print(f"{extension} kapatılırken hata: {e}")

    # Bot'u kapat
    print("Bot kapatılıyor...")
    try:
        await bot.close()
        print("Bot kapandı.")
    except Exception as e:
        print(f"Bot kapatma hatası: {e}")

    print("Temizlik işlemleri tamamlandı.")

async def main():
    try:
        async with bot:
            await load_extensions()
            await bot.start(TOKEN)
    except asyncio.CancelledError:
        print("Bot is shutting down gracefully...")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
        await cleanup()
        
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot shutdown signal received...")
        asyncio.run(main())
    except Exception as e:
        print(f"An unexpected error occurred during startup: {e}")