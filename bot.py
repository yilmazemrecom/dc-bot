from config import TOKEN
import discord
from discord.ext import commands, tasks
import aiosqlite
import os
from util import init_db, load_economy, save_economy, add_user_to_economy

PREFIX = '!'

intents = discord.Intents.default()
intents.messages = True  # Mesaj içeriği izni
intents.presences = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

@bot.event
async def on_ready():
    await init_db()
    await bot.change_presence(activity=discord.Game(name="ŞUAN BOT BAKIMDADIR!"))
    update_server_info.start()

@tasks.loop(hours=1)  # Her saat başı çalışır
async def update_server_info():
    sunucular = bot.guilds
    async with aiosqlite.connect('economy.db') as db:
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
        komutlar = [
            "!komutlar: Tüm komutları listeler",
            "",
            "**Genel Komutlar**",
            "- `!oyunbilayar #kanal`: Kanala Steam ve Epic oyun indirimlerini atar",
            "",
            "**Müzik Komutları**",
            "- `!cal <şarkı adı veya URL>`: Belirtilen şarkıyı çalar",
            "- `!dur`: Müziği durdurur",
            "- `!devam`: Müziği devam ettirir",
            "- `!siradakiler`: Sıradaki şarkıları gösterir",
            "- `!gec`: Sıradaki şarkıya geçer",
            "- `!cik`: Ses kanalından ayrılır",
            "",
            "**Eğlence Komutları:**",
            "Para kazanmak için quiz veya bilmece bilebilirsiniz. Varsayılan bakiyeniz 100 sikke olarak eklenir.",
            "- `!siralama`: En zengin 20 kişiyi sıralar - Tüm Sunucular",
            "- `!bakiye`: Bakiyeninizi gösterir",
            "- `!btransfer <kişi etiket> <tutar>`: Belirttiğiniz tutar kadar sikke transferi yapar.",
            "- `!bilmece`: Rastgele bir bilmece sorar",
            "- `!zar <bahis> <tahmin>`: Zar oyunu",
            "- `!yazitura <bahis> <yazı/tura>`: Yazı tura oyunu",
            "- `!quiz`: Rastgele bir quiz sorusu sorar",
            "- `!asmaca`: Adam asmaca oyunu",
            "- `!rulet <bahis>`: Rulet oyunu. Ya hep ya hiç",
            "",
            "**Takım Oyunu Komutları:**",
            "- `!takimolustur <takim_adi> <yatirim miktarı>`: Yeni bir takım oluşturur",
            "- `!takimyatirim <yatırım miktarı>`: Takımınıza yatırım yapar",
            "- `!macyap <bahis>`: Takımınızla maç yapar",
            "- `!takimim`: Takımınızı gösterir",
            "- `!lig`: Lig durumunu gösterir",
            "",
            "**Diğer komutlar, takım oyunu kuralları ve yardım için**",
            "https://emreylmzcom.github.io/cayci/"
        ]
        await ctx.send('\n'.join(komutlar))
    except Exception as e:
        print(f"Hata: {e}")
        await ctx.send("Komutlar listesi alınırken bir hata oluştu.")


async def load_extensions():
    for extension in ['responses', 'games', 'economy', 'takimoyunu','music', 'oyunbildirim' ]:
        await bot.load_extension(extension)

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())