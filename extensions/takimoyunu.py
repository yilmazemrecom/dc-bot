import discord
from discord.ext import commands, tasks
import random
import aiosqlite
import json
import aiofiles
import datetime
from util import load_economy, save_economy, add_user_to_economy
from datetime import datetime, timedelta
from typing import Optional
from discord.app_commands import Range

DATABASE = 'database/economy.db'
WINNERS_FILE = 'json/lig_kazanan.json'

class TakimOyunu(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.reset_lig.start()

    @discord.app_commands.command(name="takimolustur")
    @discord.app_commands.describe(
        takim_adi="Takımınızın adı",
        yatirim="Başlangıç yatırım miktarı (minimum 1000 sikke)"
    )
    async def slash_takimolustur(self, interaction: discord.Interaction,
        takim_adi: str,
        yatirim: Range[int, 1000, None]
    ):
        async with aiofiles.open('json/kufur_listesi.json', 'r', encoding='utf-8') as file:
            kufur_listesi_json = await file.read()

        kufur_listesi = json.loads(kufur_listesi_json)["kufurler"]
        if any(word.lower() in takim_adi.lower() for word in kufur_listesi):
            embed = discord.Embed(title="Hata", description="Takım adında küfürlü veya uygunsuz bir kelime bulunmaktadır. Lütfen başka bir takım adı belirtin.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        if not takim_adi or yatirim < 1000:
            embed = discord.Embed(title="Hata", description="Lütfen geçerli bir takım adı ve yatırım miktarı belirtin.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        economy = await add_user_to_economy(interaction.user.id, interaction.user.name)
        bakiye = economy[2]
        if bakiye < yatirim:
            embed = discord.Embed(title="Hata", description="Yeterli bakiyeniz yok.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(interaction.user.id),))
            row = await cursor.fetchone()
            if row:
                embed = discord.Embed(title="Hata", description="Zaten bir takımınız var.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await db.execute('''
                INSERT INTO takimlar (user_id, takim_adi, kaptan, miktari, kazanilan_mac, kaybedilen_mac)
                VALUES (?, ?, ?, ?, 0, 0)
            ''', (str(interaction.user.id), takim_adi, interaction.user.name, yatirim, 0, 0))
            await db.commit()

        new_balance = bakiye - yatirim
        await save_economy(interaction.user.id, interaction.user.name, new_balance)
        embed = discord.Embed(title="Takım Oluşturuldu", description=f"{interaction.user.mention}, '{takim_adi}' adında yeni bir takım oluşturdunuz ve {yatirim} sikke harcadınız.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.app_commands.command(name="takimyatirim", description="Takıma yatırım yapar")
    async def slash_takimyatirim(self, interaction: discord.Interaction, miktar: int):
        if miktar <= 0:
            embed = discord.Embed(title="Hata", description="Lütfen geçerli bir miktar belirtin.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        economy = await add_user_to_economy(interaction.user.id, interaction.user.name)
        bakiye = economy[2]
        if bakiye < miktar:
            embed = discord.Embed(title="Hata", description="Yeterli bakiyeniz yok.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(interaction.user.id),))
            row = await cursor.fetchone()
            if not row:
                embed = discord.Embed(title="Hata", description="Henüz bir takımınız yok. İlk önce bir takım oluşturun.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            son_yatirim_zamani = row[6]  # Son yatırım zamanı sütununun indeksini doğru şekilde ayarlayın
            if son_yatirim_zamani:
                son_yatirim_zamani = datetime.strptime(son_yatirim_zamani, '%Y-%m-%d %H:%M:%S')
                suanki_zaman = datetime.now()
                if suanki_zaman - son_yatirim_zamani < timedelta(hours=5):
                    kalan_sure = timedelta(hours=5) - (suanki_zaman - son_yatirim_zamani)
                    saat, dakika, saniye = kalan_sure.seconds // 3600, (kalan_sure.seconds // 60) % 60, kalan_sure.seconds % 60
                    embed = discord.Embed(title="Hata", description=f"Son yatırımınızdan bu yana 5 saat geçmedi. Kalan süre: {saat} saat, {dakika} dakika, {saniye} saniye. Lütfen daha sonra tekrar deneyin.", color=discord.Color.red())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

            yeni_miktar = row[3] + miktar
            yeni_yatirim_zamani = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            await db.execute('UPDATE takimlar SET miktari = ?, son_yatirim_zamani = ? WHERE user_id = ?',
                            (yeni_miktar, yeni_yatirim_zamani, str(interaction.user.id)))
            await db.commit()

        new_balance = bakiye - miktar
        await save_economy(interaction.user.id, interaction.user.name, new_balance)
        embed = discord.Embed(title="Yatırım Başarılı", description=f"{interaction.user.mention}, '{row[1]}' takımınıza {miktar} sikke yatırım yaptınız.", color=discord.Color.green())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.app_commands.command(name="macyap")
    @discord.app_commands.describe(
        bahis="Maç bahis miktarı (minimum 100 sikke)",
        rakip="Maç yapmak istediğiniz takım (opsiyonel)"
    )
    async def slash_macyap(self, interaction: discord.Interaction,
        bahis: Range[int, 100, None],
        rakip: Optional[discord.Member] = None
    ):
        if bahis <= 1 or bahis >= 1001:
            embed = discord.Embed(title="Hata", description="Lütfen geçerli bir bahis miktarı belirtin. Bahis miktarı en az 2 ve en fazla 1000 olabilir.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        economy = await add_user_to_economy(interaction.user.id, interaction.user.name)
        bakiye = economy[2]
        if bakiye < bahis:
            embed = discord.Embed(title="Hata", description="Yeterli bakiyeniz yok.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(interaction.user.id),))
            kullanici_takimi = await cursor.fetchone()
            if not kullanici_takimi:
                embed = discord.Embed(title="Hata", description="Henüz bir takımınız yok. İlk önce bir takım oluşturun.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            son_mac_zamani = kullanici_takimi[7]
            now = datetime.now()

            if son_mac_zamani is not None:
                diff = now - datetime.fromisoformat(son_mac_zamani)
                if diff.total_seconds() < 3600:
                    kalan_sure = 3600 - diff.total_seconds()
                    dakika = kalan_sure // 60
                    saniye = kalan_sure % 60
                    embed = discord.Embed(title="Hata", description=f"Bir saat içinde sadece bir maç yapabilirsiniz. Kalan süre: {int(dakika)} dakika {int(saniye)} saniye.", color=discord.Color.red())
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return

            yeni_miktar = kullanici_takimi[3] - bahis
            await db.execute('UPDATE takimlar SET miktari = ?, son_mac_zamani = ? WHERE user_id = ?', (yeni_miktar, now.isoformat(), str(interaction.user.id)))
            await db.commit()

            cursor = await db.execute('SELECT * FROM takimlar WHERE user_id != ?', (str(interaction.user.id),))
            rakip_takimlar = await cursor.fetchall()
            if not rakip_takimlar:
                embed = discord.Embed(title="Hata", description="Maç yapacak rakip bulunamadı.", color=discord.Color.red())
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            rakip_takimi = random.choice(rakip_takimlar)

            if kullanici_takimi[3] > rakip_takimi[3]:
                kazanan_takim_id = str(interaction.user.id)
                kaybeden_takim_id = rakip_takimi[0]
            else:
                kazanan_takim_id = rakip_takimi[0]
                kaybeden_takim_id = str(interaction.user.id)

            await db.execute('UPDATE takimlar SET miktari = miktari + ? WHERE user_id = ?', (bahis, kazanan_takim_id))
            await db.execute('UPDATE takimlar SET miktari = miktari - ? WHERE user_id = ?', (max(0, bahis / 2), kaybeden_takim_id))

            if kazanan_takim_id == str(interaction.user.id):
                embed = discord.Embed(title="Maç Sonucu", description=f"{interaction.user.mention}, '{kullanici_takimi[1]}' takımı '{rakip_takimi[1]}' takımını mağlup etti! {bahis * 2} sikke kazandınız.", color=discord.Color.green())
                await db.execute('UPDATE economy SET bakiye = bakiye + ? WHERE user_id = ?', (bahis * 2, str(interaction.user.id)))
                await db.execute('UPDATE takimlar SET kazanilan_mac = kazanilan_mac + 1 WHERE user_id = ?', (kazanan_takim_id,))
                await db.execute('UPDATE takimlar SET kaybedilen_mac = kaybedilen_mac + 1 WHERE user_id = ?', (kaybeden_takim_id,))
            else:
                embed = discord.Embed(title="Maç Sonucu", description=f"{interaction.user.mention}, '{kullanici_takimi[1]}' takımı '{rakip_takimi[1]}' takımına yenildi.", color=discord.Color.red())
                await db.execute('UPDATE takimlar SET kaybedilen_mac = kaybedilen_mac + 1 WHERE user_id = ?', (kaybeden_takim_id,))
                await db.execute('UPDATE takimlar SET kazanilan_mac = kazanilan_mac + 1 WHERE user_id = ?', (kazanan_takim_id,))

            await db.commit()  # Veri yazma işlemini tamamlama

            await interaction.response.send_message(embed=embed)


    @discord.app_commands.command(name="takimim", description="Takım bilgilerinizi gösterir")
    async def slash_takimim(self, interaction: discord.Interaction):
        async with aiosqlite.connect(DATABASE) as db:
            cursor = await db.execute('SELECT * FROM takimlar WHERE user_id = ?', (str(interaction.user.id),))
            row = await cursor.fetchone()

        if not row:
            embed = discord.Embed(title="Hata", description=f"Henüz bir takımınız yok. İlk önce bir takım oluşturun.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(title="Takım Bilgileri", color=discord.Color.blue())
        embed.add_field(name="Takım Adı", value=row[1], inline=False)
        embed.add_field(name="Kaptan", value=row[2], inline=False)
        embed.add_field(name="Takım Kasası", value=f"{row[3]} sikke", inline=False)
        embed.add_field(name="Kazanılan Maçlar", value=row[4], inline=True)
        embed.add_field(name="Kaybedilen Maçlar", value=row[5], inline=True)
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="lig", description="Lig sıralamasını gösterir")
    async def slash_lig(self, interaction: discord.Interaction):
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

        embed = discord.Embed(title="Lig Sıralaması", description=lig_mesaji, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

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
    await bot.add_cog(TakimOyunu(bot))
