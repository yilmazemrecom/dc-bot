from config import TOKEN
import discord
from discord.ext import commands, tasks
import aiosqlite
import os
from util import init_db, load_economy, save_economy, add_user_to_economy

PREFIX = '!'

intents = discord.Intents.default()
intents.messages = True  # Mesaj içeriği izni

intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    await init_db()

    update_server_info.start()

@tasks.loop(hours=1)  # Her saat başı çalışır
async def update_server_info():
    sunucular = bot.guilds
    async with aiosqlite.connect('database/economy.db') as db:
        # Veritabanındaki mevcut sunucuları al
        async with db.execute('SELECT sunucu_id FROM sunucular') as cursor:
            mevcut_sunucu_ids = [row[0] for row in await cursor.fetchall()]

        # Mevcut sunucular ile botun bağlı olduğu sunucuları karşılaştır
        bot_sunucu_ids = [sunucu.id for sunucu in sunucular]
        
        # Botun artık bağlı olmadığı sunucuları sil
        silinecek_sunucu_ids = set(mevcut_sunucu_ids) - set(bot_sunucu_ids)
        if silinecek_sunucu_ids:
            await db.executemany('DELETE FROM sunucular WHERE sunucu_id = ?', 
                                 [(sunucu_id,) for sunucu_id in silinecek_sunucu_ids])
            print(f"{len(silinecek_sunucu_ids)} sunucu silindi.")

        # Mevcut sunucuların bilgilerini güncelle veya ekle
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

@bot.command(name='komutlar')
async def list_commands(ctx):
    try:
        embed = discord.Embed(title="Komut Listesi", color=discord.Color.blue())
        
        # Genel Komutlar
        embed.add_field(name="Genel Komutlar", value=(
            "- `!komutlar`: Tüm komutları listeler\n"
            "- `!oyunbildirimac <#kanal>`: Belirtilen kanal için oyun indirim bildirimlerini açar\n"
            "- `!oyunbildirimkapat`: Oyun bildirimlerini kapatır\n"
            "- `!siralama`: En zengin 20 kişiyi sıralar - Tüm Sunucular\n"
            "- `!bakiye`: Bakiyenizi gösterir\n"
            "- `!btransfer <kişi etiket> <tutar>`: Belirttiğiniz tutar kadar sikke transferi yapar."
        ), inline=False)
        
        # Müzik Komutları
        embed.add_field(name="Müzik Komutları", value=(
            "- `!cal <şarkı adı veya URL>`: Belirtilen şarkıyı çalar\n"
            "- `!dur`: Müziği durdurur\n"
            "- `!devam`: Müziği devam ettirir\n"
            "- `!siradakiler`: Sıradaki şarkıları gösterir\n"
            "- `!gec`: Sıradaki şarkıya geçer\n"
            "- `!cik`: Ses kanalından ayrılır"
        ), inline=False)
        
        # Eğlence Komutları
        embed.add_field(name="Eğlence Komutları", value=(
            "Para kazanmak için quiz veya bilmece bilebilirsiniz. Varsayılan bakiyeniz 100 sikke olarak eklenir.\n"
            "- `!bilmece`: Rastgele bir bilmece sorar\n"
            "- `!zar <bahis> <tahmin>`: Zar oyunu\n"
            "- `!yazitura <bahis> <yazı/tura>`: Yazı tura oyunu\n"
            "- `!quiz`: Rastgele bir quiz sorusu sorar\n"
            "- `!asmaca`: Adam asmaca oyunu\n"
            "- `!rulet <bahis>`: Rulet oyunu. Ya hep ya hiç"
        ), inline=False)
        
        # Takım Oyunu Komutları
        embed.add_field(name="Takım Oyunu Komutları", value=(
            "- `!takimolustur <takım adı> <yatırım miktarı>`: Yeni bir takım oluşturur\n"
            "- `!takimyatirim <yatırım miktarı>`: Takımınıza yatırım yapar\n"
            "- `!macyap <bahis>`: Takımınızla maç yapar\n"
            "- `!takimim`: Takımınızı gösterir\n"
            "- `!lig`: Lig durumunu gösterir"
        ), inline=False)
        
        # Yardım ve Diğer Komutlar
        embed.add_field(name="Diğer komutlar, takım oyunu kuralları ve yardım için", value=(
            "https://emreylmzcom.github.io/cayci/"
        ), inline=False)
        
        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Hata: {e}")
        await ctx.send("Komutlar listesi alınırken bir hata oluştu.")

async def load_extensions():
    for extension in ['responses', 'games', 'economy', 'takimoyunu','music', 'oyunbildirim', 'film' ]:
        await bot.load_extension(f'extensions.{extension}')

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())