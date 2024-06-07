from config import TOKEN
import discord
from discord.ext import commands
from discord.utils import get
from discord import TextChannel
import os
import random
from currency_converter import CurrencyConverter
import json
import asyncio
import aiosqlite

PREFIX = '!'

# Gerekli izinler
intents = discord.Intents.default()
intents.messages = True  # Mesaj içeriği izni
intents.presences = True
intents.message_content = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

DATABASE = 'economy.db'

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS economy (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                bakiye INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sunucular (
                sunucu_id TEXT PRIMARY KEY,
                sunucu_ismi TEXT,
                sunucu_uye_sayisi INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS takimlar (
                user_id TEXT PRIMARY KEY,
                takim_adi TEXT,
                kaptan TEXT,
                miktari INTEGER,
                kazanilan_mac INTEGER,
                kaybedilen_mac INTEGER
            )
        ''')
        await db.commit()

async def load_economy(user_id):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('SELECT * FROM economy WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        return row

async def save_economy(user_id, username, bakiye):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('REPLACE INTO economy (user_id, username, bakiye) VALUES (?, ?, ?)', (user_id, username, bakiye))
        await db.commit()

async def add_user_to_economy(user_id, username):
    economy = await load_economy(user_id)
    if not economy:
        await save_economy(user_id, username, 100)
        economy = (user_id, username, 100)
    return economy

async def load_bilmeceler():
    if os.path.exists('bilmeceler.json'):
        async with aiofiles.open('bilmeceler.json', mode='r', encoding='utf-8') as f:
            return json.loads(await f.read())
    return []

async def load_quiz_questions():
    if os.path.exists('quiz_sorulari.json'):
        async with aiofiles.open('quiz_sorulari.json', mode='r', encoding='utf-8') as f:
            return json.loads(await f.read())
    return []

@bot.event
async def on_guild_join(guild):
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

    await add_user_to_economy(user_id=message.author.id, username=message.author.name)

    content = message.content.lower()
    await bot.process_commands(message)
    for keyword, response in responses.items():
        if keyword in content:
            await message.channel.send(f"{message.author.mention}, {response}")
            return

    if "dolar" in content:
        try:
            c = CurrencyConverter()
            amount = c.convert(1, 'USD', 'TRY')
            await message.channel.send(f"{message.author.mention}, 1 dolar {amount:.2f} TL ediyor!")
        except Exception as e:
            await message.channel.send(f"{message.author.mention}, döviz kurunu alırken bir hata oluştu: {str(e)}")

    elif "çay" in content:
        await message.channel.send("https://tenor.com/view/çaylar-çaycıhüseyin-gif-18623727")

@bot.command()
async def bilmece(ctx):
    bilmece_havuzu = await load_bilmeceler()
    selected_riddle = random.choice(bilmece_havuzu)
    soru = selected_riddle["soru"]
    cevap = selected_riddle["cevap"]
    await ctx.send(f"{ctx.author.mention}, işte bir bilmece: {soru}")

    def check(msg):
        return msg.author == ctx.author and msg.content.lower() == cevap.lower()

    try:
        msg = await bot.wait_for('message', timeout=30, check=check)
        economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
        para = random.randint(1, 100)
        yeni_bakiye = economy[2] + para
        await save_economy(ctx.author.id, ctx.author.name, yeni_bakiye)
        await ctx.send(f"Tebrikler {msg.author.mention}! Doğru cevap: {cevap}! {para} sikke kazandınız.")
    except asyncio.TimeoutError:
        await ctx.send(f"Üzgünüm, zaman doldu. Doğru cevap: {cevap}")

@bot.command()
async def bakiye(ctx):
    user_id = str(ctx.author.id)
    username = ctx.author.name
    economy = await add_user_to_economy(user_id, username)
    bakiye = economy[2]
    if bakiye <= -100:
        await ctx.send("Bakiyeniz -100'den az olamaz, lütfen biraz bilmece veya quiz çözerek bakiyenizi artırın.")
    else:
        await ctx.send(f'{bakiye} sikkeniz var. :sunglasses: ')

    commands.command()
    async def btransfer(self, ctx, user: discord.Member, amount: int):
        economy = await load_economy(str(ctx.author.id))
        if not economy or economy[2] < amount:
            await ctx.send("Yetersiz bakiye.")
            return

        target_economy = await load_economy(str(user.id))
        if not target_economy:
            target_economy = (str(user.id), user.name, 0)

        new_author_balance = economy[2] - amount
        new_target_balance = target_economy[2] + amount

        await save_economy(ctx.author.id, ctx.author.name, new_author_balance)
        await save_economy(user.id, user.name, new_target_balance)
        await ctx.send(f"{amount} sikke, {user.name}'in hesabına aktarıldı.")

    @btransfer.error
    async def btransfer_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Lütfen bir kullanıcı ve miktar belirtin. Örneğin: `!btransfer @kullanıcı 100`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Geçerli bir kullanıcı ve miktar belirtmelisiniz. Örneğin: `!btransfer @kullanıcı 100`")


@bot.command()
async def zar(ctx, bahis: int, tahmin: int):
    if bahis <= 0 or tahmin < 1 or tahmin > 6:
        await ctx.send("Geçerli bir bahis miktarı ve tahmin belirtmelisiniz.")
        return

    economy = await add_user_to_economy(ctx.author.id, ctx.author.name)
    bakiye = economy[2]
    if bakiye < -100:
        await ctx.send("Bakiyeniz -100'den az olduğu için bu oyunu oynayamazsınız. Quiz veya bilmece çözerek bakiyenizi arttırın.")
        return

    zar_sayisi = random.randint(1, 6)
    if tahmin == zar_sayisi:
        kazanc = bahis * 2
        new_balance = bakiye + kazanc
        await ctx.send(f"Tebrikler! Zar atılan sayı {zar_sayisi} ve tahmininiz doğru! {kazanc} sikke kazandınız.")
    else:
        new_balance = bakiye - bahis
        await ctx.send(f"Maalesef! Zar atılan sayı {zar_sayisi} ve tahmininiz {tahmin}. Bilemediniz. {bahis} sikke kaybettiniz.")
    await save_economy(ctx.author.id, ctx.author.name, new_balance)

@zar.error
async def zar_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Lütfen bir bahis miktarı belirtin. Örneğin: `!zar <bahis miktarı> <tahmin>`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Geçerli bir bahis miktarı belirtmelisiniz.")

@bot.command()
async def yazitura(ctx, bahis: int, secim: str):
    if bahis <= 0 or secim.lower() not in ["yazı", "tura"]:
        await ctx.send("Geçerli bir bahis miktarı ve seçim belirtmelisiniz: yazı veya tura.")
        return

    economy = await add_user_to_economy(ctx.author.id, ctx.author.name)
    bakiye = economy[2]
    if bakiye < -100:
        await ctx.send("Bakiyeniz -100'den az olduğu için bu oyunu oynayamazsınız. Quiz veya bilmece çözerek bakiyenizi arttırın.")
        return

    yanit = random.choice(["yazı", "tura"])
    if secim.lower() == yanit:
        kazanc = bahis * 2
        new_balance = bakiye + kazanc
        await ctx.send(f"Tebrikler! Sonuç {yanit}, tahmininiz doğru! {kazanc} sikke kazandınız.")
    else:
        new_balance = bakiye - bahis
        await ctx.send(f"Maalesef! Sonuç {yanit}, tahmininiz {secim}. Bilemediniz. {bahis} sikke kaybettiniz.")
    await save_economy(ctx.author.id, ctx.author.name, new_balance)

@yazitura.error
async def yazitura_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Lütfen bir bahis miktarı ve seçim belirtin. Örneğin: `!yazitura <bahis miktarı> <yazı/tura>`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Geçerli bir bahis miktarı belirtmelisiniz.")

@bot.command()
async def quiz(ctx):
    quiz_sorulari = await load_quiz_questions()
    selected_question = random.choice(quiz_sorulari)
    soru, cevap = selected_question["soru"], selected_question["cevap"]
    await ctx.send(f"{ctx.author.mention}, işte bir soru: {soru}")

    def check(msg):
        return msg.author == ctx.author

    try:
        msg = await bot.wait_for('message', timeout=30, check=check)
        if msg.content.lower() == cevap.lower():
            await ctx.send(f"Tebrikler {ctx.author.mention}, doğru cevap! 5 sikke kazandınız.")
            economy = await add_user_to_economy(ctx.author.id, ctx.author.name)
            new_balance = economy[2] + 5
            await save_economy(ctx.author.id, ctx.author.name, new_balance)
        else:
            await ctx.send(f"Üzgünüm {ctx.author.mention}, yanlış cevap. Doğru cevap: {cevap} ")
    except asyncio.TimeoutError:
        await ctx.send(f"Üzgünüm {ctx.author.mention}, zaman doldu. Doğru cevap: {cevap}")

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
    yanlis_tahminler = set()
    can = len(adam_asmaca) - 1

    await ctx.send("Adam asmaca oyununa hoş geldiniz! Kelimeyi tahmin etmek için harfleri yazın.")
    await ctx.send(f"Kelime {len(cevap)} harften oluşuyor.")

    while can > 0:
        mesaj = harf_tahmin_et(cevap, dogru_tahminler)
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
async def rulet(ctx, bahis: int):
    if bahis <= 0:
        await ctx.send("Geçerli bir bahis miktarı belirtmelisiniz.")
        return

    economy = await add_user_to_economy(ctx.author.id, ctx.author.name)
    bakiye = economy[2]
    if bakiye < -100:
        await ctx.send("Bakiyeniz -100'den az olduğu için bu oyunu oynayamazsınız. Quiz veya bilmece çözerek bakiyenizi arttırın.")
        return
    
    kazandi = random.choice([True, False])
    if kazandi:
        new_balance = bakiye + bahis
        await ctx.send(f"Tebrikler! Rulet kazandınız. {bahis} sikke kazandınız.")
    else:
        new_balance = bakiye - bahis
        await ctx.send(f"Maalesef! Rulet kaybettiniz. {bahis} sikke kaybettiniz.")
    await save_economy(ctx.author.id, ctx.author.name, new_balance)

@rulet.error
async def rulet_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Lütfen bir bahis miktarı belirtin. Örneğin: `!rulet <bahis miktarı>`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Geçerli bir bahis miktarı belirtmelisiniz.")

@bot.command()
async def siralama(ctx):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('SELECT * FROM economy ORDER BY bakiye DESC LIMIT 20')
        rows = await cursor.fetchall()

    sıralama_mesajı = "Sıralama:\n"
    for index, row in enumerate(rows, start=1):
        username = row[1]
        bakiye = row[2]
        sıralama_mesajı += f"{index}. {username} - {bakiye} sikke\n"

    await ctx.send(sıralama_mesajı)

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

@bot.event
async def on_ready():
    await init_db()
    print(f'{bot.user.name} olarak giriş yapıldı!')
    await bot.change_presence(activity=discord.Game(name="Çay Yapıyor!"))
    
    sunucular = bot.guilds
    async with aiosqlite.connect(DATABASE) as db:
        for sunucu in sunucular:
            await db.execute('''
                INSERT OR REPLACE INTO sunucular (sunucu_id, sunucu_ismi, sunucu_uye_sayisi)
                VALUES (?, ?, ?)
            ''', (sunucu.id, sunucu.name, sunucu.member_count))
        await db.commit()
    print("Sunucular listesi çekildi ve veritabanına kaydedildi.")

    print("Bot hazır, komutlar çalıştırılabilir.")

@bot.command()
async def takimolustur(ctx, takim_adi: str, miktari: int):
    async with aiofiles.open('kufur_listesi.json', 'r', encoding='utf-8') as file:
        kufur_listesi_json = await file.read()

    kufur_listesi = json.loads(kufur_listesi_json)["kufurler"]
    if any(word.lower() in takim_adi.lower() for word in kufur_listesi):
        await ctx.send("Takım adında küfürlü veya uygunsuz bir kelime bulunmaktadır. Lütfen başka bir takım adı belirtin.")
        return

    if not takim_adi or miktari <= 0:
        await ctx.send("Lütfen geçerli bir takım adı ve miktar belirtin.")
        return

    economy = await add_user_to_economy(ctx.author.id, ctx.author.name)
    bakiye = economy[2]
    if bakiye < miktari:
        await ctx.send("Yeterli bakiyeniz yok.")
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(ctx.author.id),))
        row = await cursor.fetchone()
        if row:
            await ctx.send("Zaten bir takımınız var.")
            return

        await db.execute('''
            INSERT INTO takimlar (user_id, takim_adi, kaptan, miktari, kazanilan_mac, kaybedilen_mac)
            VALUES (?, ?, ?, ?, 0, 0)
        ''', (str(ctx.author.id), takim_adi, ctx.author.name, miktari))
        await db.commit()

    new_balance = bakiye - miktari
    await save_economy(ctx.author.id, ctx.author.name, new_balance)
    await ctx.send(f"{ctx.author.mention}, '{takim_adi}' adında yeni bir takım oluşturdunuz ve {miktari} sikke harcadınız.")

@bot.command()
async def takimyatirim(ctx, miktar: int):
    if miktar <= 0:
        await ctx.send("Lütfen geçerli bir miktar belirtin.")
        return

    economy = await add_user_to_economy(ctx.author.id, ctx.author.name)
    bakiye = economy[2]
    if bakiye < miktar:
        await ctx.send("Yeterli bakiyeniz yok.")
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(ctx.author.id),))
        row = await cursor.fetchone()
        if not row:
            await ctx.send("Henüz bir takımınız yok. İlk önce bir takım oluşturun.")
            return

        yeni_miktar = row[3] + miktar
        await db.execute('UPDATE takimlar SET miktari = ? WHERE user_id = ?', (yeni_miktar, str(ctx.author.id)))
        await db.commit()

    new_balance = bakiye - miktar
    await save_economy(ctx.author.id, ctx.author.name, new_balance)
    await ctx.send(f"{ctx.author.mention}, '{row[1]}' takımınıza {miktar} sikke yatırım yaptınız.")

@bot.command()
async def macyap(ctx, bahis: int):
    if bahis <= 0:
        await ctx.send("Lütfen geçerli bir bahis miktarı belirtin.")
        return

    economy = await add_user_to_economy(ctx.author.id, ctx.author.name)
    bakiye = economy[2]
    if bakiye < bahis:
        await ctx.send("Yeterli bakiyeniz yok.")
        return

    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(ctx.author.id),))
        kullanici_takimi = await cursor.fetchone()
        if not kullanici_takimi:
            await ctx.send("Henüz bir takımınız yok. İlk önce bir takım oluşturun.")
            return

        yeni_miktar = kullanici_takimi[3] - bahis
        await db.execute('UPDATE takimlar SET miktari = ? WHERE user_id = ?', (yeni_miktar, str(ctx.author.id)))
        await db.commit()

        cursor = await db.execute('SELECT * FROM takimlar WHERE user_id != ?', (str(ctx.author.id),))
        rakip_takimlar = await cursor.fetchall()
        rakip_takimi = random.choice(rakip_takimlar)

        if kullanici_takimi[3] > rakip_takimi[3]:
            kazanan_takim_id = str(ctx.author.id)
            kaybeden_takim_id = rakip_takimi[0]
        else:
            kazanan_takim_id = rakip_takimi[0]
            kaybeden_takim_id = str(ctx.author.id)

        await db.execute('UPDATE takimlar SET miktari = miktari + ? WHERE user_id = ?', (bahis * 2, kazanan_takim_id))
        await db.execute('UPDATE takimlar SET miktari = miktari - ? WHERE user_id = ?', (bahis, kaybeden_takim_id))

        if kazanan_takim_id == str(ctx.author.id):
            await ctx.send(f"{ctx.author.mention}, '{kullanici_takimi[1]}' takımı '{rakip_takimi[1]}' takımını mağlup etti! {bahis * 2} sikke kazandınız.")
            await db.execute('UPDATE economy SET bakiye = bakiye + ? WHERE user_id = ?', (bahis * 2, str(ctx.author.id)))
        else:
            await ctx.send(f"{ctx.author.mention}, '{kullanici_takimi[1]}' takımı '{rakip_takimi[1]}' takımına yenildi.")
        await db.commit()

@bot.command()
async def takimim(ctx):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(ctx.author.id),))
        row = await cursor.fetchone()

    if not row:
        await ctx.send("Henüz bir takımınız yok. İlk önce bir takım oluşturun.")
        return

    mesaj = f"Takım Adı: {row[1]}\n"
    mesaj += f"Kaptan: {row[2]}\n"
    mesaj += f"Takım Kasası: {row[3]} sikke\n"
    mesaj += f"Kazanılan Maçlar: {row[4]}\n"
    mesaj += f"Kaybedilen Maçlar: {row[5]}\n"
    await ctx.send(mesaj)

bot.run(TOKEN)
