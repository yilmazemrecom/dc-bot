from config import TOKEN
import discord
from discord.ext import commands, tasks
import aiosqlite
import os
from util import init_db, load_economy, save_economy, add_user_to_economy, update_user_server, update_existing_table

PREFIX = '!'

intents = discord.Intents.default()
intents.message_content = True


bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    try:
        await init_db()
        update_server_info.start()
        update_server_count.start()

        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

@tasks.loop(minutes=10) 
async def update_server_count():
    async with aiosqlite.connect('database/economy.db') as db:
        async with db.execute('SELECT SUM(sunucu_uye_sayisi) FROM sunucular') as cursor:
            row = await cursor.fetchone()
            total_users = row[0] if row[0] is not None else 0

    status = f"{total_users} kullanıcı | /komutlar "
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.listening , name=status))





@bot.tree.command(name="ping", description="Ping komutu")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message("Pong!")

# Slash komutu olarak 'komutlar'
@bot.tree.command(name="komutlar", description="Tüm komutları listeler")
async def slash_komutlar(interaction: discord.Interaction):
    try:
        embed = discord.Embed(title="Komut Listesi", color=discord.Color.blue())
        
        embed.add_field(name="Genel Komutlar", value=(
            "- `/komutlar`: Tüm komutları listeler\n"
            "- `/oyunbildirimac <kanal>`: Belirtilen kanal için oyun indirim bildirimlerini açar\n"
            "- `/oyunbildirimkapat`: Oyun bildirimlerini kapatır\n"
            "- `/haberbildirimac <kanal>`: Belirtilen kanal için haber bildirimlerini açar\n"
            "- `/haberbildirimkapat`: Haber bildirimlerini kapatır\n"
            "- `/filmbildirimac <kanal>`: Belirtilen kanal için film öneri bildirimlerini açar\n"
            "- `/filmbildirimkapat`: Film bildirimlerini kapatır\n"
            "- `/siralama`: En zengin 20 kişiyi sıralar - Tüm Sunucular\n"
            "- `/bakiye`: Bakiyenizi gösterir\n"
            "- `/btransfer <kisi> <tutar>`: Belirttiğiniz tutar kadar sikke transferi yapar."
        ), inline=False)
        
        embed.add_field(name="Müzik Komutları", value=(
            "- `/cal <şarkı adı veya Youtube URL>`: Belirtilen şarkıyı çalar\n"
        ), inline=False)
        
        embed.add_field(name="Eğlence Komutları", value=(
            "Para kazanmak için quiz veya bilmece bilebilirsiniz. Varsayılan bakiyeniz 100 sikke olarak eklenir.\n"
            "- `/bilmece`: Rastgele bir bilmece sorar\n"
            "- `/zar <bahis> <tahmin>`: Zar oyunu\n"
            "- `/yazitura <bahis> <yazı/tura>`: Yazı tura oyunu\n"
            "- `/quiz`: Rastgele bir quiz sorusu sorar\n"
            "- `/rulet <bahis>`: Rulet oyunu. Ya hep ya hiç"
            "- '/duello <kişi>': Seçtiğiniz kişiye duello isteği atar ve savaşırsınız."
        ), inline=False)
        
        embed.add_field(name="Takım Oyunu Komutları", value=(
            "- `/takimolustur <takım adı> <yatırım miktarı>`: Yeni bir takım oluşturur\n"
            "- `/takimyatirim <yatırım miktarı>`: Takımınıza yatırım yapar\n"
            "- `/macyap <bahis>`: Takımınızla maç yapar\n"
            "- `/takimim`: Takımınızı gösterir\n"
            "- `/lig`: Lig durumunu gösterir"
        ), inline=False)
        
        embed.add_field(name="Diğer komutlar, takım oyunu kuralları ve yardım için", value=(
            "Website: https://cayci.com.tr \n"

        ), inline=False)
        
        await interaction.response.send_message(embed=embed)
    except Exception as e:
        print(f"Hata: {e}")
        await interaction.response.send_message("Komutlar listesi alınırken bir hata oluştu.")

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
    for extension in ['extensions.responses', 'extensions.games', 'extensions.economy', 'extensions.takimoyunu', 'extensions.music', 'extensions.oyunbildirim', 'extensions.film', 'extensions.duel', 'extensions.haberbildirim' ]:
        await bot.load_extension(extension)

async def main():
    async with bot:
        await load_extensions()
        await update_existing_table()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
