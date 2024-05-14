import discord
from discord.ext import commands
from discord.utils import get
from discord import TextChannel
import os
import random
from currency_converter import CurrencyConverter
import json
import asyncio
import aiofiles

# Botunuzu Discord Developer Portal'dan aldığınız token ile başlatın
TOKEN = 'MTIzOTI0NjU1Mzg2MDgwMDYxNA.G6KXUJ.KfVxkeS1GWdF60q2BPn_QyV9b8UhF63371PW40'

# Botunuzun ön ekini belirleyin
PREFIX = '!'

# Botunuzu başlatın ve gerekli izinleri belirtin
intents = discord.Intents.default()
intents.messages = True  # Mesaj içeriği iznini etkinleştirin
intents.presences = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

async def load_economy():
    if os.path.exists('economy.json'):
        async with aiofiles.open('economy.json', mode='r') as f:
            return json.loads(await f.read())
    return {}

async def save_economy(economy):
    async with aiofiles.open('economy.json', mode='w') as f:
        await f.write(json.dumps(economy, indent=4))

async def add_user_to_economy(user_id, username):
    economy = await load_economy()
    if str(user_id) not in economy:
        economy[str(user_id)] = {'bakiye': 100, "username": username}
        await save_economy(economy)
    return economy



async def load_bilmeceler():
    if os.path.exists('bilmeceler.json'):
          async with aiofiles.open('bilmeceler.json', mode='r', encoding='utf-8') as f:
            return json.loads(await f.read())
    return []

# Quiz sorularını yükle
async def load_quiz_questions():
    if os.path.exists('quiz_sorulari.json'):
        async with aiofiles.open('quiz_sorulari.json', mode='r', encoding='utf-8') as f:
            return json.loads(await f.read())
    return []





# bot bir sunucuya katıldıgında calısacak kodlar
@bot.event
async def on_guild_join(guild):
    # Sunucuya katıldığında hoş geldin mesajı gönder
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            await channel.send(f"Merhaba! Ben {bot.user.name}, beni eklediğiniz için teşekkür ederim. Benimle sohbet etmek için `{PREFIX}komutlar` yazabilirsiniz.")
            await channel.send(f"Çaylaaaağrrrrrr!!! :teapot: ")
        break





responses = {
    "selam": "Merhaba!",
    "nasılsın": "iyiyim, sen nasılsın?",
    "hoş geldin": "Teşekkürler!",
    "görüşürüz": "Görüşmek üzere!",
    "sa": "Aleyküm selam!",
    "naber": "iyiyim, sen nasılsın?",
    "iyi": "Ne güzel!",
    "kötü": "üzüldüm, umarım bir an önce düzelirsin.",
    "teşekkürler": "rica ederim!",
    "iyi geceler": "iyi geceler!",
    "günaydın": "günaydın!",
    "iyi akşamlar": "iyi akşamlar!",
    "iyi günler": "iyi günler!",
    "çay": "Çayllaaaağğrr Geliyooo!! :teapot: ",
    "kahve": "Starbucks mı burası kardeşim? :coffee: ",
    "çaycı": "çay mı istiyon? :teapot: ",
    "çay ver abine": "çayın geliyor abim :teapot: "
}

# Event listener for messages
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Bakiye olustur
    await add_user_to_economy(user_id=message.author.id, username=message.author.name)

    content = message.content.lower()
    words = content.split() 

    if content in responses:
        await message.channel.send(f"{message.author.mention}, {responses[content]}")

    elif "çay ver abine" in content:
        for mentioned_user in message.mentions:
            await message.channel.send(f"{mentioned_user.name}, çayın geliyor abim :teapot: ")

    elif "dolar" in content:
        try:
            c = CurrencyConverter()
            amount = c.convert(1, 'USD', 'TRY')
            await message.channel.send(f"{message.author.mention}, 1 dolar {amount:.2f} TL ediyor!")
        except Exception as e:
            await message.channel.send(f"{message.author.mention}, döviz kurunu alırken bir hata oluştu: {str(e)}")

    elif "çay" in words:
        await message.channel.send(f"{message.author.mention} Çayllaaaağğrr Geliyooo!! :teapot: ")






    await bot.process_commands(message)

# oyun

@bot.command()
async def bilmece(ctx):
    bilmece_havuzu = await load_bilmeceler()

    # Rastgele bir bilmece seçin
    selected_riddle = random.choice(bilmece_havuzu)
    soru = selected_riddle["soru"]
    cevap = selected_riddle["cevap"]

    # Kullanıcıya bilmeceyi sorun
    await ctx.send(f"{ctx.author.mention}, işte bir bilmece: {soru}")

    # Kullanıcının cevabını kontrol edin
    def check(msg):
        return msg.author == ctx.author and msg.content.lower() == cevap.lower()

    # Kullanıcının doğru cevabı vermesini bekleyin
    try:
        msg = await bot.wait_for('message', timeout=30, check=check)
        economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
        para = random.randint(1, 100)
        economy[str(ctx.author.id)]['bakiye'] += para
        await save_economy(economy)
        await ctx.send(f"Tebrikler {msg.author.mention}! Doğru cevap: {cevap}! {para} sikke kazandınız.")
    except asyncio.TimeoutError:
        await ctx.send("Üzgünüm, zaman doldu. Doğru cevap:" f"{cevap}")

@bot.command()
async def bakiye(ctx):
    economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
    bakiye = economy[str(ctx.author.id)]['bakiye']
    if bakiye <= -100:
        await ctx.send("Bakiyeniz -100'den az olamaz, lütfen biraz bilmece veya quiz çözerek bakiyenizi artırın.")
        await ctx.send(f'{bakiye} sikkeniz var.')
    else:
        await ctx.send(f'{bakiye} sikkeniz var. :sunglasses: ')

# Zar Oyunu
@bot.command()
async def zar(ctx, bahis: int, tahmin: int):
    # Bahis miktarını kontrol et
    if bahis <= 0:
        await ctx.send("Geçerli bir bahis miktarı belirtmelisiniz.")
        return

    # Tahminin geçerli bir zar değeri olup olmadığını kontrol et
    if tahmin < 1 or tahmin > 6:
        await ctx.send("Geçerli bir zar tahmini belirtmelisiniz (1 ile 6 arasında).")
        return

    # Kullanıcının bakiyesini kontrol et
    economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
    bakiye = economy[str(ctx.author.id)]['bakiye']
    if bakiye < -100:
        await ctx.send("Bakiyeniz -100'den az olduğu için bu oyunu oynayamazsınız. Quiz veya bilmece çözerek bakiyenizi arttırın.")
        return

    # Zar atılacak sayıyı belirle (1 ile 6 arasında)
    zar_sayisi = random.randint(1, 6)

    # Kullanıcının tahmini ile zar atılan sayıyı karşılaştır
    if tahmin == zar_sayisi:
        kazanc = bahis * 2
        economy[str(ctx.author.id)]['bakiye'] += kazanc
        await save_economy(economy)
        await ctx.send(f"Tebrikler! Zar atılan sayı {zar_sayisi} ve tahmininiz doğru! {kazanc} sikke kazandınız.")
    else:
        economy[str(ctx.author.id)]['bakiye'] -= bahis
        await save_economy(economy)
        await ctx.send(f"Maalesef! Zar atılan sayı {zar_sayisi} ve tahmininiz {tahmin}. Bilemediniz. {bahis} sikke kaybettiniz.")


@zar.error
async def zar_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Lütfen bir bahis miktarı belirtin. Örneğin: `!zar <bahis miktarı> <tahmin>`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Geçerli bir bahis miktarı belirtmelisiniz.")


# Yazı Tura
@bot.command()
async def yazitura(ctx, bahis: int, secim: str):
    # Bahis miktarını kontrol et
    if bahis <= 0:
        await ctx.send("Geçerli bir bahis miktarı belirtmelisiniz.")
        return

    # Kullanıcının seçiminin geçerli olup olmadığını kontrol et
    secim = secim.lower()
    if secim not in ["yazı", "tura"]:
        await ctx.send("Geçerli bir seçim yapmalısınız: yazı veya tura.")
        return

        # Kullanıcının bakiyesini kontrol et
    economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
    bakiye = economy[str(ctx.author.id)]['bakiye']
    if bakiye < -100:
        await ctx.send("Bakiyeniz -100'den az olduğu için bu oyunu oynayamazsınız. Quiz veya bilmece çözerek bakiyenizi arttırın.")
        return

    # Rastgele yazı veya tura seç
    yanit = random.choice(["yazı", "tura"])

    # Kullanıcının seçimi ile gerçek sonucu karşılaştır
    if secim == yanit:
        economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
        kazanc = bahis * 2
        economy[str(ctx.author.id)]['bakiye'] += kazanc
        await save_economy(economy)
        await ctx.send(f"Tebrikler! Sonuç {yanit}, tahmininiz doğru! {kazanc} sikke kazandınız.")
    else:
        economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
        economy[str(ctx.author.id)]['bakiye'] -= bahis
        await save_economy(economy)
        await ctx.send(f"Maalesef! Sonuç {yanit}, tahmininiz {secim}. Bilemediniz. {bahis} sikke kaybettiniz.")

@yazitura.error
async def yazitura_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Lütfen bir bahis miktarı ve seçim belirtin. Örneğin: `!yazitura <bahis miktarı> <yazı/tura>`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Geçerli bir bahis miktarı belirtmelisiniz.")




@bot.command()
async def quiz(ctx):
    # Quiz sorularını yükle
    quiz_sorulari = await load_quiz_questions()

    # Rastgele bir soru seç
    selected_question = random.choice(quiz_sorulari)
    soru, cevap = selected_question["soru"], selected_question["cevap"]

    # Kullanıcıya soruyu sor
    await ctx.send(f"{ctx.author.mention}, işte bir soru: {soru}")

    def check(msg):
        return msg.author == ctx.author

    try:
        # Kullanıcının cevabını al
        msg = await bot.wait_for('message', timeout=30, check=check)

        # Kullanıcının cevabını kontrol et
        if msg.content.lower() == cevap.lower():
            await ctx.send("Tebrikler, doğru cevap! 5 sikke kazandınız.")
            # Doğru cevap için kullanıcıya 5 sikke ekle
            economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
            economy[str(ctx.author.id)]['bakiye'] += 5
            await save_economy(economy)
        else:
            await ctx.send(f"Üzgünüm, yanlış cevap. Doğru cevap: {cevap} ")
    except asyncio.TimeoutError:
        await ctx.send(f"Üzgünüm, zaman doldu. Doğru cevap: {cevap}")




# Adam asma grafiği
adam_asmaca = [
    """
    +---+
        |
        |
        |
        |
        |
  =========
    """,
    """
    +---+
    O   |
        |
        |
        |
        |
  =========
    """,
    """
    +---+
    O   |
   /|   |
        |
        |
        |
  =========
    """,
    """
    +---+
    O   |
   /|\\  |
        |
        |
        |
  =========
    """,
    """
    +---+
    O   |
   /|\\  |
   /    |
        |
        |
  =========
    """,
    """
    +---+
    O   |
   /|\\  |
   / \\  |
        |
        |
  =========
    """
]

# Kelimeler listesi
kelimeler = [
    "bilgisayar", "internet", "müzik", "sanat", "tarih", "edebiyat", "gezegen", 
    "evrim", "kültür", "dil", "geometri", "biyoloji", "kimya", "fizik", "matematik", 
    "arkeoloji", "jeoloji", "teknoloji", "kriptografi", "filozofi", "astronomi", 
    "antropoloji", "meteoroloji", "psikoloji", "sosyoloji", "ekonomi", "politika", 
    "tarım", "mimarlık", "müze", "mimari", "sağlık", "insanlık", "din", "inanç", 
    "coğrafya", "jeopolitik", "spor", "medya", "toplum", "iletişim", "ulaşım", 
    "enerji", "ekoloji", "çevre", "sürdürülebilirlik", "turizm"
]


def kelime_sec():
    return random.choice(kelimeler).lower()

def harf_tahmin_et(kelime, tahmin_edilenler):
    return "".join(harf if harf in tahmin_edilenler else "_" for harf in kelime)



@bot.command(name='asmaca')
async def asmaca(ctx):
    kelime = kelime_sec()
    dogru_tahminler = set()
    yanlis_tahminlar = set()
    can = len(adam_asmaca) - 1

    await ctx.send("Adam asmaca oyununa hoş geldiniz! Kelimeyi tahmin etmek için harfleri yazın.")
    await ctx.send(f"Kelime {len(kelime)} harften oluşuyor.")

    while can > 0:
        mesaj = ""
        for harf in kelime:
            if harf in dogru_tahminler:
                mesaj += harf + " "
            else:
                mesaj += "_ "
        await ctx.send(mesaj)

        tahmin = await bot.wait_for('message', check=lambda m: m.author == ctx.author)
        tahmin = tahmin.content.lower()

        if tahmin in dogru_tahminler or tahmin in yanlis_tahminlar:
            await ctx.send("Bu harfi zaten tahmin ettiniz!")
            continue

        if tahmin in kelime:
            dogru_tahminler.add(tahmin)
            if set(kelime) == dogru_tahminler:
                await ctx.send("Tebrikler, kelimeyi doğru tahmin ettiniz!")
                break
        else:
            yanlis_tahminlar.add(tahmin)
            can -= 1
            await ctx.send(f"Yanlış tahmin! Kalan can: {can}\n{adam_asmaca[len(adam_asmaca) - can - 1]}")

    if can == 0:
        await ctx.send(f"Maalesef, kelimeyi bulamadınız! Kelime: {kelime}")







@bot.command()
async def siralama(ctx):
    economy = await load_economy()

    # Bakiyeye göre sıralama yap
    sorted_economy = sorted(economy.items(), key=lambda x: x[1]['bakiye'], reverse=True)

    # İlk 20 kişiyi al
    top_20 = sorted_economy[:20]

    # Sıralamayı göster
    sıralama_mesajı = "Sıralama:\n"
    for index, (user_id, user_data) in enumerate(top_20, start=1):
        # Kullanıcı adını al
        user = await bot.fetch_user(int(user_id))
        username = user.name if user else user_data['username']

        # Bakiyeyi al
        bakiye = user_data['bakiye']

        # Mesajı oluştur
        sıralama_mesajı += f"{index}. {username} - {bakiye} sikke\n"

    await ctx.send(sıralama_mesajı)




# tüm komutları listeleme
@bot.command(name='komutlar')
async def list_commands(ctx):
    komutlar = [
        "!komutlar: Tüm komutları listeler",

        "",
        "**Genel Komutlar:**",
        "`sa`: Aleyküm selam!",
        "`selam`: Merhaba!",
        "`nasılsın`: Botun nasıl olduğunu sorar",
        "`hoş geldin`: Hoş geldin mesajı verir",
        "`görüşürüz`: Görüşürüz mesajı verir",
        "`naber`: Nasıl olduğunu sorar",
        "`iyi`: İyi olduğunu belirtir",
        "`kötü`: Kötü olduğunu belirtir",
        "`teşekkürler`: Teşekkür eder",
        "`iyi geceler`: İyi geceler mesajı verir",
        "`günaydın`: Günaydın mesajı verir",
        "`iyi akşamlar`: İyi akşamlar mesajı verir",
        "`iyi günler`: İyi günler mesajı verir",
        "`çay`: Çay getirir",
        "`kahve`: Kahve getirir (belki de getirmez)",
        "`çaycı`: Çay mı istediğini sorar",
        "",
        "**Döviz Kuru Komutları:**",
        "`dolar`: 1 doların kaç TL olduğunu gösterir",

        "",
        "**Eğlence Komutları:**",

        "`!siralama`: En zengin 20 kişiyi sıralar - Tüm Sunucular",
        "`!bilmece`: Rastgele bir bilmece sorar",
        "`!bakiye`: Bakiyeninizi gosterir",
        "`!zar <bahis> <tahmin>`: Zar oyunu oynar",
        "`!yazitura <bahis> <yazı/tura>`: Yazı tura oyunu oynar",
        "`!quiz`: Rastgele bir quiz sorusu sorar",
        "`!asmaca`: Adam asmaca oyunu oynar (üç beş yeri sorunlu ama genel mantık çalışıyor)",

    ]
    await ctx.send('\n'.join(komutlar))







# Sunucuları listeleme

@bot.event
async def on_ready():
    print(f'{bot.user.name} olarak giriş yapıldı!')

    await bot.change_presence(activity=discord.Game(name="Çay Yapıyor!"))


    sunucular = bot.guilds
    sunucular_listesi = []
    for sunucu in sunucular:
        sunucular_listesi.append({
            "sunucu_id": sunucu.id,
            "sunucu_ismi": sunucu.name,
            "sunucu_üye_sayısı": sunucu.member_count
        })

    async with aiofiles.open('sunucular.json', mode='w', encoding='utf-8') as f:
        await f.write(json.dumps(sunucular_listesi, indent=4, ensure_ascii=False))


    print("Sunucular listesi sunucular.json dosyasına yazıldı.")
    print("Bot hazır, komutlar çalıştırılabilir.")








# Botunuzu başlatın
bot.run(TOKEN)
