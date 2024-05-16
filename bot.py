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
    "Merhaba": "Merhabana merhaba kardeş!",
    "s.a": "Aleyküm selam!",
    "naber": "iyiyim, sen nasılsın?",
    "kötü": "üzüldüm, umarım bir an önce düzelirsin.",
    "teşekkürler": "rica ederim!",
    "iyi geceler": "iyi geceler!",
    "günaydın": "günaydın!",
    "iyi akşamlar": "iyi akşamlar!",
    "iyi günler": "iyi günler!",
    "kahve": "Starbucks mı burası kardeşim? :coffee: ",
    "çaycı": "çay mı istiyon? :teapot: ",


}

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Bakiye oluştur
    await add_user_to_economy(user_id=message.author.id, username=message.author.name)

    content = message.content.lower()
    await bot.process_commands(message)
    # Özel durumlar için yanıt verme
    for keyword, response in responses.items():
        if keyword in content:
            await message.channel.send(f"{message.author.mention}, {response}")
            return  # işlemi sonlandır



    if "dolar" in content:
        try:
            c = CurrencyConverter()
            amount = c.convert(1, 'USD', 'TRY')
            await message.channel.send(f"{message.author.mention}, 1 dolar {amount:.2f} TL ediyor!")
        except Exception as e:
            await message.channel.send(f"{message.author.mention}, döviz kurunu alırken bir hata oluştu: {str(e)}")

    elif "çay" in content:
        await message.channel.send("https://tenor.com/view/çaylar-çaycıhüseyin-gif-18623727")
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
            await ctx.send(f"Tebrikler {ctx.author.mention}, doğru cevap! 5 sikke kazandınız.")
            # Doğru cevap için kullanıcıya 5 sikke ekle
            economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
            economy[str(ctx.author.id)]['bakiye'] += 5
            await save_economy(economy)
        else:
            await ctx.send(f"Üzgünüm {ctx.author.mention}, yanlış cevap. Doğru cevap: {cevap} ")
    except asyncio.TimeoutError:
        await ctx.send(f"Üzgünüm {ctx.author.mention}, zaman doldu. Doğru cevap: {cevap}")




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
    return "".join(harf if harf in tahmin_edilenler else ":blue_circle:" for harf in kelime)



@bot.command(name='asmaca')
async def asmaca(ctx):
    cevap = kelime_sec()
    dogru_tahminler = set()
    yanlis_tahminlar = set()
    can = len(adam_asmaca) - 1

    await ctx.send("Adam asmaca oyununa hoş geldiniz! Kelimeyi tahmin etmek için harfleri yazın.")
    await ctx.send(f"Kelime {len(cevap)} harften oluşuyor.")

    while can > 0:
        mesaj = harf_tahmin_et(cevap,dogru_tahminler)
        await ctx.send(mesaj)

        tahmin = await bot.wait_for('message', check=lambda m: m.author == ctx.author)
        tahmin = tahmin.content.lower()

        if tahmin in dogru_tahminler or tahmin in yanlis_tahminlar:
            await ctx.send("Bu harfi zaten tahmin ettiniz!")
            continue

        if len(tahmin) > 1 and tahmin == cevap:
            await ctx.send("Tebrikler, kelimeyi doğru tahmin ettiniz!")
            break

        if tahmin in cevap:
            dogru_tahminler.add(tahmin)
            if set(cevap) == dogru_tahminler:
                await ctx.send("Tebrikler, kelimeyi doğru tahmin ettiniz!")
                break
        else:
            yanlis_tahminlar.add(tahmin)
            can -= 1
            await ctx.send(f"Yanlış tahmin! Kalan can: {can}\n{adam_asmaca[len(adam_asmaca) - can - 1]}")

    if can == 0:
        await ctx.send(f"Maalesef, kelimeyi bulamadınız! Kelime: {cevap}")





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
        "- `sa`: Aleyküm selam!",
        "- `selam`: Merhaba!",
        "- `nasılsın`: Botun nasıl olduğunu sorar",
        "- `hoş geldin`: Hoş geldin mesajı verir",
        "- `görüşürüz`: Görüşürüz mesajı verir",
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
        "- `!bilmece`: Rastgele bir bilmece sorar",
        "- `!bakiye`: Bakiyeninizi gosterir",
        "- `!zar <bahis> <tahmin>`: Zar oyunu",
        "- `!yazitura <bahis> <yazı/tura>`: Yazı tura oyunu",
        "- `!quiz`: Rastgele bir quiz sorusu sorar",
        "- `!asmaca`: Adam asmaca oyunu",
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




# futbol oyunu


@bot.command()
async def takimolustur(ctx, takim_adi: str, miktari: int):
        # JSON dosyasından küfür listesini oku
    async with aiofiles.open('kufur_listesi.json', 'r', encoding='utf-8') as file:
        kufur_listesi_json = await file.read()

    kufur_listesi = json.loads(kufur_listesi_json)["kufurler"]

    # Takım adında küfür bulunup bulunmadığını kontrol et
    if any(word.lower() in takim_adi.lower() for word in kufur_listesi):
        await ctx.send("Takım adında küfürlü veya uygunsuz bir kelime bulunmaktadır. Lütfen başka bir takım adı belirtin.")
        return

    # Takım adı ve miktarı boş olamaz
    if not takim_adi:
        await ctx.send("Lütfen geçerli bir takım adı belirtin.")
        return
    if miktari <= 0:
        await ctx.send("Lütfen geçerli bir miktar belirtin.")
        return

    # Kullanıcının bakiyesini kontrol et
    economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
    bakiye = economy[str(ctx.author.id)]['bakiye']

    # Kullanıcının yeterli bakiyesi var mı kontrol et
    if bakiye < miktari:
        await ctx.send("Yeterli bakiyeniz yok.")
        return

    # Takım oluştur
    takimlar = {}
    if os.path.exists('takimlar.json'):
        async with aiofiles.open('takimlar.json', mode='r', encoding='utf-8') as f:
            takimlar = json.loads(await f.read())

    if str(ctx.author.id) in takimlar:
        await ctx.send("Zaten bir takımınız var.")
        return

    takimlar[str(ctx.author.id)] = {
        'takim_adi': takim_adi,
        'kaptan': ctx.author.name,
        'miktari': miktari,
        'kazanilan_mac': 0,
        'kaybedilen_mac': 0
    }

    async with aiofiles.open('takimlar.json', mode='w', encoding='utf-8') as f:
        await f.write(json.dumps(takimlar, indent=4))

    # Kullanıcının bakiyesinden miktarı düş
    economy[str(ctx.author.id)]['bakiye'] -= miktari
    await save_economy(economy)

    await ctx.send(f"{ctx.author.mention}, '{takim_adi}' adında yeni bir takım oluşturdunuz ve {miktari} sikke harcadınız.")



@bot.command()
async def takimyatirim(ctx, miktar: int):
    # Miktar geçerli mi kontrol et
    if miktar <= 0:
        await ctx.send("Lütfen geçerli bir miktar belirtin.")
        return

    # Kullanıcının bakiyesini kontrol et
    economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
    bakiye = economy[str(ctx.author.id)]['bakiye']

    # Kullanıcının yeterli bakiyesi var mı kontrol et
    if bakiye < miktar:
        await ctx.send("Yeterli bakiyeniz yok.")
        return

    # Kullanıcının takımını al
    takimlar = {}
    if os.path.exists('takimlar.json'):
        async with aiofiles.open('takimlar.json', mode='r', encoding='utf-8') as f:
            takimlar = json.loads(await f.read())

    if str(ctx.author.id) not in takimlar:
        await ctx.send("Henüz bir takımınız yok. İlk önce bir takım oluşturun.")
        return

    takim = takimlar[str(ctx.author.id)]
    takim_adi = takim['takim_adi']

    # Takıma yatırım yap
    takim['miktari'] += miktar

    async with aiofiles.open('takimlar.json', mode='w', encoding='utf-8') as f:
        await f.write(json.dumps(takimlar, indent=4))

    # Kullanıcının bakiyesinden miktarı düş
    economy[str(ctx.author.id)]['bakiye'] -= miktar
    await save_economy(economy)

    await ctx.send(f"{ctx.author.mention}, '{takim_adi}' takımınıza {miktar} sikke yatırım yaptınız.")


@bot.command()
async def macyap(ctx, bahis: int):
    # Bahis miktarını kontrol et
    if bahis <= 0:
        await ctx.send("Lütfen geçerli bir bahis miktarı belirtin.")
        return

    # Kullanıcının bakiyesini kontrol et
    economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
    bakiye = economy[str(ctx.author.id)]['bakiye']

    # Kullanıcının yeterli bakiyesi var mı kontrol et
    if bakiye < bahis:
        await ctx.send("Yeterli bakiyeniz yok.")
        return

    # Takımları yükle
    takimlar = {}
    if os.path.exists('takimlar.json'):
        async with aiofiles.open('takimlar.json', mode='r', encoding='utf-8') as f:
            takimlar = json.loads(await f.read())

    if str(ctx.author.id) not in takimlar:
        await ctx.send("Henüz bir takımınız yok. İlk önce bir takım oluşturun.")
        return

    kullanici_takimi = takimlar[str(ctx.author.id)]

    # Takıma yatırılan bahis miktarını güncelle
    kullanici_takimi['miktari'] -= bahis

    # Rastgele bir rakip seç
    rakip_id = random.choice(list(takimlar.keys()))
    while rakip_id == str(ctx.author.id) or kullanici_takimi['takim_adi'] == takimlar[rakip_id]['takim_adi']:
        rakip_id = random.choice(list(takimlar.keys()))

    rakip_takimi = takimlar[rakip_id]

    # Takımlar arasında maç yap
    if kullanici_takimi['miktari'] > rakip_takimi['miktari']:
        kazanan_takim_id = str(ctx.author.id)
    else:
        kazanan_takim_id = rakip_id

    # Kazanan takımın bakiyesine bahis miktarını ekle 
    takimlar[kazanan_takim_id]['miktari'] += bahis *2

    # Kaybeden takımdan bahis miktarını çıkar
    takimlar[rakip_id]['miktari'] -= bahis

    # Maç sonucunu bildir
    if kazanan_takim_id == str(ctx.author.id):
        await ctx.send(f"{ctx.author.mention}, '{kullanici_takimi['takim_adi']}' takımı '{rakip_takimi['takim_adi']}' takımını mağlup etti! {bahis * 2} sikke kazandınız.")
        economy[str(ctx.author.id)]['bakiye'] += bahis * 2
        kullanici_takimi['kazanilan_mac'] += 1
        rakip_takimi['kaybedilen_mac'] += 1
    else:
        await ctx.send(f"{ctx.author.mention}, '{kullanici_takimi['takim_adi']}' takımı '{rakip_takimi['takim_adi']}' takımına yenildi.")
        kullanici_takimi['kaybedilen_mac'] += 1
        rakip_takimi['kazanilan_mac'] += 1

    # Takım verilerini kaydet
    async with aiofiles.open('takimlar.json', mode='w', encoding='utf-8') as f:
        await f.write(json.dumps(takimlar, indent=4))

    # Kullanıcının bakiyesini güncelle
    economy[str(ctx.author.id)]['bakiye'] -= bahis
    await save_economy(economy)




@bot.command()
async def takimim(ctx):
    # Takımları yükle
    takimlar = {}
    if os.path.exists('takimlar.json'):
        async with aiofiles.open('takimlar.json', mode='r', encoding='utf-8') as f:
            takimlar = json.loads(await f.read())

    if str(ctx.author.id) not in takimlar:
        await ctx.send("Henüz bir takımınız yok. İlk önce bir takım oluşturun.")
        return

    kullanici_takimi = takimlar[str(ctx.author.id)]
    mesaj = f"Takım Adı: {kullanici_takimi['takim_adi']}\n"
    mesaj += f"Kaptan: {kullanici_takimi['kaptan']}\n"
    mesaj += f"Takım Kasası: {kullanici_takimi['miktari']} sikke\n"
    mesaj += f"Kazanılan Maçlar: {kullanici_takimi['kazanilan_mac']}\n"
    mesaj += f"Kaybedilen Maçlar: {kullanici_takimi['kaybedilen_mac']}\n"

    await ctx.send(mesaj)



# Botunuzu başlatın
bot.run(TOKEN)