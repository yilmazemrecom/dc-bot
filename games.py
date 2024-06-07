from discord.ext import commands
import random
import asyncio
from util import load_economy, save_economy, add_user_to_economy, load_bilmeceler, load_quiz_questions
import aiosqlite
import json
import aiofiles

DATABASE = 'economy.db'

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Bilmece komutu
    @commands.command()
    async def bilmece(self, ctx):
        print("Bilmece komutu çağrıldı")
        bilmece_havuzu = await load_bilmeceler()
        selected_riddle = random.choice(bilmece_havuzu)
        soru = selected_riddle["soru"]
        cevap = selected_riddle["cevap"]
        await ctx.send(f"{ctx.author.mention}, işte bir bilmece: {soru}")

        def check(msg):
            return msg.author == ctx.author and msg.content.lower() == cevap.lower()

        try:
            msg = await self.bot.wait_for('message', timeout=30, check=check)
            economy = await add_user_to_economy(user_id=ctx.author.id, username=ctx.author.name)
            para = random.randint(1, 100)
            yeni_bakiye = economy[2] + para
            await save_economy(ctx.author.id, ctx.author.name, yeni_bakiye)
            await ctx.send(f"Tebrikler {msg.author.mention}! Doğru cevap: {cevap}! {para} sikke kazandınız.")
        except asyncio.TimeoutError:
            await ctx.send(f"Üzgünüm, zaman doldu. Doğru cevap: {cevap}")

    # Zar komutu
    @commands.command()
    async def zar(self, ctx, bahis: int, tahmin: int):
        print("Zar komutu çağrıldı")
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

    # Quiz komutu
    @commands.command()
    async def quiz(self, ctx):
        print("Quiz komutu çağrıldı")
        quiz_sorulari = await load_quiz_questions()
        selected_question = random.choice(quiz_sorulari)
        soru, cevap = selected_question["soru"], selected_question["cevap"]
        await ctx.send(f"{ctx.author.mention}, işte bir soru: {soru}")

        def check(msg):
            return msg.author == ctx.author

        try:
            msg = await self.bot.wait_for('message', timeout=30, check=check)
            if msg.content.lower() == cevap.lower():
                await ctx.send(f"Tebrikler {ctx.author.mention}, doğru cevap! 5 sikke kazandınız.")
                economy = await add_user_to_economy(ctx.author.id, ctx.author.name)
                new_balance = economy[2] + 5
                await save_economy(ctx.author.id, ctx.author.name, new_balance)
            else:
                await ctx.send(f"Üzgünüm {ctx.author.mention}, yanlış cevap. Doğru cevap: {cevap} ")
        except asyncio.TimeoutError:
            await ctx.send(f"Üzgünüm {ctx.author.mention}, zaman doldu. Doğru cevap: {cevap}")

    # Rulet komutu
    @commands.command()
    async def rulet(self, ctx, bahis: int):
        print("Rulet komutu çağrıldı")
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
    async def rulet_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Lütfen bir bahis miktarı belirtin. Örneğin: `!rulet <bahis miktarı>`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("Geçerli bir bahis miktarı belirtmelisiniz.")
    
    
    # adam asmaca
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

    def kelime_sec(self):
        return random.choice(self.kelimeler).lower()

    def harf_tahmin_et(self, kelime, tahmin_edilenler):
        return "".join(harf if harf in tahmin_edilenler else ":blue_circle:" for harf in kelime)

    @commands.command(name='asmaca')
    async def asmaca(self, ctx):
        kelime_listesi = await load_kelime_listesi()
        cevap = random.choice(kelime_listesi).lower()
        dogru_tahminler = set()
        yanlis_tahminler = set()
        can = len(self.adam_asmaca) - 1

        await ctx.send("Adam asmaca oyununa hoş geldiniz! Kelimeyi tahmin etmek için harfleri yazın.")
        await ctx.send(f"Kelime {len(cevap)} harften oluşuyor.")

        while can > 0:
            mesaj = self.harf_tahmin_et(cevap, dogru_tahminler)
            await ctx.send(mesaj)

            tahmin = await self.bot.wait_for('message', check=lambda m: m.author == ctx.author)
            tahmin = tahmin.content.lower()

            if tahmin in dogru_tahminler or tahmin in yanlis_tahminler:
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
                yanlis_tahminler.add(tahmin)
                can -= 1
                await ctx.send(f"Yanlış tahmin! Kalan can: {can}\n{self.adam_asmaca[len(self.adam_asmaca) - can - 1]}")

        if can == 0:
            await ctx.send(f"Maalesef, kelimeyi bulamadınız! Kelime: {cevap}")

async def setup(bot):
    await bot.add_cog(Games(bot))
