from config import TOKEN
import discord
from discord.ext import commands, tasks
import aiosqlite
import os
import asyncio
from datetime import datetime
from util import init_db, load_economy, save_economy, add_user_to_economy, update_user_server, update_existing_table

PREFIX = '!'

intents = discord.Intents.default()
intents.message_content = True


bot = commands.Bot(command_prefix=PREFIX, intents=intents)
bot.start_time = datetime.now()  # Bot başlangıç zamanını kaydet

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        # Create necessary directories
        os.makedirs('logs', exist_ok=True)
        os.makedirs('config', exist_ok=True)
        os.makedirs('backups', exist_ok=True)
        
        await init_db()
        update_server_info.start()
        update_server_count.start()

        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@tasks.loop(minutes=10) 
async def update_server_count():
    try:
        async with aiosqlite.connect('database/economy.db') as db:
            async with db.execute('SELECT SUM(sunucu_uye_sayisi) FROM sunucular') as cursor:
                row = await cursor.fetchone()
                total_users = row[0] if row[0] is not None else 0

        status = f"{total_users} kullanıcı | /komutlar "
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening , name=status))
    except Exception as e:
        print(f"Sunucu sayısı güncelleme hatası: {e}")





@bot.tree.command(name="ping", description="Ping komutu")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

# Slash komutu olarak 'komutlar'
@bot.tree.command(name="komutlar", description="Tüm komutları listeler")
async def komutlar(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🎮 Çaycı Bot - Komut Listesi",
        description="Aşağıdaki komutları `/` ile kullanabilirsiniz\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯",
        color=discord.Color.blue()
    )

    # Müzik Komutları
    music_commands = (
        "**`/cal`** • Şarkı çalar\n"
        "**`/siradakiler`** • Sıradaki şarkıları gösterir\n"
        "**`/favori`** • Şarkıyı favorilere ekler/çıkarır\n"
        "**`/favoriler`** • Favori listesini gösterir\n"
        "**`/favorical`** • Favorilerden şarkı çalar\n"
        "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯"
    )
    embed.add_field(
        name="🎵 Müzik Komutları", 
        value=music_commands, 
        inline=False
    )

    # Ekonomi Komutları
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

    # Oyun Komutları
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

    # Eğlence & Diğer
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
        "**`/haberbildirimac`** • Haber bildirimleri\n\n"
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

    # Daha detaylı footer
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

@update_server_info.before_loop
async def before_update_server_info():
    await bot.wait_until_ready()

async def load_extensions():
    for extension in ['extensions.responses', 
                      'extensions.games', 
                      'extensions.economy', 
                      'extensions.takimoyunu', 
                      'extensions.music', 
                      'extensions.oyunbildirim', 
                      'extensions.duel', 
                      'extensions.haberbildirim', 
                      'extensions.reminder', 
                      'extensions.api_endpoints',
                      'extensions.oyunsecim'
                      ]:
        await bot.load_extension(extension)

async def cleanup():
    print("Temizlik işlemleri başlatılıyor...")
    
    # Extension'ları kapat
    print("Extension'lar kapatılıyor...")
    extensions = list(bot.extensions.keys())
    for extension in extensions:
        try:
            await bot.unload_extension(extension)
            print(f"{extension} kapatıldı")
        except Exception as e:
            print(f"{extension} kapatılırken hata: {e}")

    # Task loop'ları zorla durdur
    print("Task loop'lar durduruluyor...")
    try:
        update_server_info.stop()
        update_server_count.stop()
    except Exception as e:
        print(f"Task loop durdurma hatası: {e}")

    # Tüm ses bağlantılarını kapat
    print("Ses bağlantıları kapatılıyor...")
    try:
        for vc in bot.voice_clients:
            try:
                await asyncio.wait_for(vc.disconnect(force=True), timeout=1.0)
            except:
                pass
    except Exception as e:
        print(f"Ses bağlantıları kapatma hatası: {e}")

    # Bot'u kapat
    print("Bot kapatılıyor...")
    try:
        await bot.close()
    except Exception as e:
        print(f"Bot kapatma hatası: {e}")

    print("Temizlik işlemleri tamamlandı.")
    
    # Zorla çıkış yap
    import os, signal
    os.kill(os.getpid(), signal.SIGTERM)

def force_exit():
    import os, sys
    try:
        sys.exit(0)
    except:
        os._exit(0)

async def main():
    try:
        async with bot:
            await load_extensions()
            await bot.start(TOKEN)
    except asyncio.CancelledError:
        print("Bot kapatılıyor...")
    except Exception as e:
        print(f"Beklenmeyen hata: {e}")
    finally:
        await cleanup()
        
        # Son bir kez daha kalan görevleri kontrol et
        remaining = [t for t in asyncio.all_tasks() if not t.done() and t is not asyncio.current_task()]
        if remaining:
            print(f"Kalan {len(remaining)} görev zorla kapatılıyor...")
            for task in remaining:
                task.cancel()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\nBot kapatma sinyali alındı...")
        try:
            loop.run_until_complete(cleanup())
        except:
            pass
        finally:
            loop.stop()
            loop.close()
            print("Bot güvenli bir şekilde kapatıldı.")
            # Zorla çıkış yap
            force_exit()
    except Exception as e:
        print(f"Beklenmeyen hata: {e}")
        loop.close()