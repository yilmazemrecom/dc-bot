from config import TOKEN
import discord
from discord.ext import commands
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
    print(f'{bot.user.name} olarak giriş yapıldı!')
    await bot.change_presence(activity=discord.Game(name="Çay Yapıyor!"))

    sunucular = bot.guilds
    async with aiosqlite.connect('economy.db') as db:
        for sunucu in sunucular:
            await db.execute('''
                INSERT OR REPLACE INTO sunucular (sunucu_id, sunucu_ismi, sunucu_uye_sayisi)
                VALUES (?, ?, ?)
            ''', (sunucu.id, sunucu.name, sunucu.member_count))
        await db.commit()
    
    print("Sunucular listesi çekildi ve veritabanına kaydedildi.")

@bot.event
async def on_shutdown():
    print("Bot kapatılıyor...")
    await bot.close()

@bot.command(name='komutlar')
async def list_commands(ctx):
    komutlar = [
        "!komutlar: Tüm komutları listeler",
        "",
        "**Genel Komutlar:**",
        "- `sa`: Aleyküm selam!",
        "- `selam`: Merhaba!",
        "- `nasılsın`: Botun nasıl olduğunu sorar",
        "- `hoş geldin`: Hoş geldin mesajı verir",
        "- `görüşürüz`: Görüşmek üzere!",
        "- `naber`: Nasıl olduğunu sorar",
        "- `iyi`: İyi olduğunu belirtir",
        "- `kötü`: Kötü olduğunu belirtir",
        "- `teşekkürler`: Teşekkür eder",
        "- `iyi geceler`: İyi geceler mesajı verir",
        "- `günaydın`: Günaydın mesajı verir",
        "- `iyi akşamlar`: İyi akşamlar mesajı verir",
        "- `iyi günler`: İyi günler mesajı verir",
        "- `çay`: Çay getirir",
        "- `kahve`: Kahve getirir (belki de getirmez)",
        "- `çaycı`: Çay mı istediğini sorar",
        "",
        "**Döviz Kuru Komutları:**",
        "- `dolar`: 1 doların kaç TL olduğunu gösterir",
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
        "Takım oyununda bir takım oluşturabilir, takımınıza yatırım yapabilir ve diğer takımlarla maç yapabilirsiniz.",
        "Takımlar gerçek kişilerdir.",
        "**Takım oyunu kuralları**",
        "1. Her kullanıcı yalnızca bir takıma sahip olabilir",
        "2. Takımınızın kasasına yatırım yaparak takımınızı güçlendirebilirsiniz",
        "3. Takımınızla maç yaparak diğer takımlardan sikke kazanabilirsiniz aynı zamanda bahis miktarı*2 de kasanıza gelir",
        "4. Maç yaparken kasada kimin daha çok sikkesi varsa o kazanır.",
        "",
        "- `!takimolustur <takim_adi> <yatirim miktarı>`: Yeni bir takım oluşturur",
        "- `!takimyatirim <yatırım miktarı>`: Takımınıza yatırım yapar",
        "- `!macyap <bahis>`: Takımınızla maç yapar",
        "- `!takimim`: Takımınızı gösterir",
    ]
    await ctx.send('\n'.join(komutlar))

async def load_extensions():
    for extension in ['responses', 'games', 'economy', 'takimoyunu','music' ]:
        await bot.load_extension(extension)

async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())