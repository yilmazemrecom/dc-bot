import discord
from discord.ext import commands, tasks
import random
import aiosqlite
import json
import aiofiles
import datetime
import asyncio
from util import load_economy, save_economy, add_user_to_economy
from datetime import datetime, timedelta


DATABASE = 'database/economy.db'
WINNERS_FILE = 'json/lig_kazanan.json'

class takimoyunu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reset_lig.start()

    @commands.command()
    async def takimolustur(self, ctx, takim_adi: str, miktari: int):
        async with aiofiles.open('json/kufur_listesi.json', 'r', encoding='utf-8') as file:
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

    @commands.command()
    async def takimyatirim(self, ctx, miktar: int):
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

            # 'son_yatirim_zamani' sütununu kontrol edin
            son_yatirim_zamani = row[6]  # Son yatırım zamanı sütununun indeksini doğru şekilde ayarlayın
            if son_yatirim_zamani:
                son_yatirim_zamani = datetime.strptime(son_yatirim_zamani, '%Y-%m-%d %H:%M:%S')
                suanki_zaman = datetime.now()
                if suanki_zaman - son_yatirim_zamani < timedelta(hours=5):
                    kalan_sure = timedelta(hours=5) - (suanki_zaman - son_yatirim_zamani)
                    saat, dakika, saniye = kalan_sure.seconds // 3600, (kalan_sure.seconds // 60) % 60, kalan_sure.seconds % 60
                    await ctx.send(f"Son yatırımınızdan bu yana 5 saat geçmedi. Kalan süre: {saat} saat, {dakika} dakika, {saniye} saniye. Lütfen daha sonra tekrar deneyin.")
                    return

            yeni_miktar = row[3] + miktar
            yeni_yatirim_zamani = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await db.execute('UPDATE takimlar SET miktari = ?, son_yatirim_zamani = ? WHERE user_id = ?',
                            (yeni_miktar, yeni_yatirim_zamani, str(ctx.author.id)))
            await db.commit()

        new_balance = bakiye - miktar
        await save_economy(ctx.author.id, ctx.author.name, new_balance)
        await ctx.send(f"{ctx.author.mention}, '{row[1]}' takımınıza {miktar} sikke yatırım yaptınız.")

 
    @commands.command()
    async def macyap(self, ctx, bahis: int):
        if bahis < 2 or bahis > 1000:
            await ctx.send(f"{ctx.author.mention} Lütfen geçerli bir bahis miktarı belirtin. Bahis miktarı en az 2 ve en fazla 1000 olabilir.")
            return


        economy = await add_user_to_economy(ctx.author.id, ctx.author.name)
        bakiye = economy[2]
        if bakiye < bahis:
            await ctx.send(f"{ctx.author.mention} Yeterli bakiyeniz yok.")
            return

        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(ctx.author.id),))
            kullanici_takimi = await cursor.fetchone()
            if not kullanici_takimi:
                await ctx.send(f"{ctx.author.mention} Henüz bir takımınız yok. İlk önce bir takım oluşturun.")
                return

            son_mac_zamani = kullanici_takimi[6]
            now = datetime.now()

            if son_mac_zamani is not None:
                diff = now - datetime.datetime.fromisoformat(son_mac_zamani)
                if diff.total_seconds() < 3600:
                    await ctx.send(f"{ctx.author.mention} Bir saat içinde sadece bir maç yapabilirsiniz.")
                    return

            yeni_miktar = kullanici_takimi[3] - bahis
            await db.execute('UPDATE takimlar SET miktari = ?, son_mac_zamani = ? WHERE user_id = ?', (yeni_miktar, now.isoformat(), str(ctx.author.id)))
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

            await db.execute('UPDATE takimlar SET miktari = miktari + ? WHERE user_id = ?', (bahis, kazanan_takim_id))
            await db.execute('UPDATE takimlar SET miktari = miktari - ? WHERE user_id = ?', (bahis / 2, kaybeden_takim_id))

            if kazanan_takim_id == str(ctx.author.id):
                await ctx.send(f"{ctx.author.mention}, '{kullanici_takimi[1]}' takımı '{rakip_takimi[1]}' takımını mağlup etti! {bahis * 2} sikke kazandınız.")
                await db.execute('UPDATE economy SET bakiye = bakiye + ? WHERE user_id = ?', (bahis * 2, str(ctx.author.id)))
                await db.execute('UPDATE takimlar SET kazanilan_mac = kazanilan_mac + 1 WHERE user_id = ?', (kazanan_takim_id,))
                await db.execute('UPDATE takimlar SET kaybedilen_mac = kaybedilen_mac + 1 WHERE user_id = ?', (kaybeden_takim_id,))
            else:
                await ctx.send(f"{ctx.author.mention}, '{kullanici_takimi[1]}' takımı '{rakip_takimi[1]}' takımına yenildi.")
                await db.execute('UPDATE takimlar SET kaybedilen_mac = kaybedilen_mac + 1 WHERE user_id = ?', (kaybeden_takim_id,))
                await db.execute('UPDATE takimlar SET kazanilan_mac = kazanilan_mac + 1 WHERE user_id = ?', (kazanan_takim_id,))

            await db.commit()

    @commands.command()
    async def takimim(self, ctx):
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(ctx.author.id),))
            row = await cursor.fetchone()

        if not row:
            await ctx.send(f"{ctx.author.mention} Henüz bir takımınız yok. İlk önce bir takım oluşturun.")
            return

        mesaj = f"Takım Adı: {row[1]}\n"
        mesaj += f"Kaptan: {row[2]}\n"
        mesaj += f"Takım Kasası: {row[3]} sikke\n"
        mesaj += f"Kazanılan Maçlar: {row[4]}\n"
        mesaj += f"Kaybedilen Maçlar: {row[5]}\n"
        await ctx.send(mesaj)


    @commands.command()
    async def lig(self, ctx):
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT takim_adi, kaptan, kazanilan_mac FROM takimlar ORDER BY kazanilan_mac DESC LIMIT 20')
            rows = await cursor.fetchall()

        lig_mesaji = "**Türk Yıldızları Ligi:**\n\n"
        lig_mesaji += "```\n"
        lig_mesaji += "{:<4} {:<20} {:<15} {:<10}\n".format("Sıra", "Takım Adı", "Kaptan", "Puan (Galibiyet)")
        lig_mesaji += "-" * 50 + "\n"
        for index, row in enumerate(rows, start=1):
            kaptan_yildizli = row[1][:-3] + "***" if len(row[1]) > 3 else "***"
            lig_mesaji += "{:<4} {:<20} {:<15} {:<10}\n".format(index, row[0], f"{kaptan_yildizli}", f"{row[2]} galibiyet")
        lig_mesaji += "```"

        await ctx.send(lig_mesaji)

    @tasks.loop(hours=24)
    async def reset_lig(self):
        now = datetime.now()
        if now.day == 1:
            async with aiosqlite.connect(DATABASE) as db:
                cursor = await db.execute('SELECT takim_adi, kaptan FROM takimlar ORDER BY kazanilan_mac DESC LIMIT 1')
                winner = await cursor.fetchone()

                if winner:
                    async with aiofiles.open(WINNERS_FILE, 'r+') as file:
                        try:
                            data = json.loads(await file.read())
                        except json.JSONDecodeError:
                            data = []

                        data.append({
                            'Ay': now.strftime("%B %Y"),
                            'takim_adi': winner[0],
                            'kaptan': winner[1]
                        })

                        await file.seek(0)
                        await file.write(json.dumps(data, ensure_ascii=False, indent=4))

                await db.execute('UPDATE takimlar SET kazanilan_mac = 0')
                await db.execute('UPDATE takimlar SET kaybedilen_mac = 0')
                await db.execute('UPDATE takimlar SET bakiye = 100')
                await db.commit()

            print("Lig sıralaması sıfırlandı!")

    @reset_lig.before_loop
    async def before_reset_lig(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(takimoyunu(bot))
