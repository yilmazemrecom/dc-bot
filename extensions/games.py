import discord
from discord.ext import commands
import random
import asyncio
from util import load_economy, save_economy, add_user_to_economy, load_bilmeceler, load_quiz_questions, load_kelime_listesi, update_user_server
import aiosqlite
import json
import aiofiles

DATABASE = 'database/economy.db'

class Games(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="bilmece", description="Bir bilmece sorar")
    async def slash_bilmece(self, interaction: discord.Interaction):
        await update_user_server(user_id, interaction.guild.id)
        bilmece_havuzu = await load_bilmeceler()
        selected_riddle = random.choice(bilmece_havuzu)
        soru = selected_riddle["soru"]
        cevap = selected_riddle["cevap"]
        embed = discord.Embed(title="Bilmece", description=f"{interaction.user.mention}, işte bir bilmece: {soru}", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

        def check(msg):
            return msg.author == interaction.user and msg.content.lower() == cevap.lower()

        try:
            msg = await self.bot.wait_for('message', timeout=30, check=check)
            economy = await add_user_to_economy(user_id=interaction.user.id, username=interaction.user.name)
            para = random.randint(1, 100)
            yeni_bakiye = economy[2] + para
            await save_economy(interaction.user.id, interaction.user.name, yeni_bakiye)
            embed = discord.Embed(title="Doğru Cevap", description=f"Tebrikler {msg.author.mention}! Doğru cevap: {cevap}! {para} sikke kazandınız.", color=discord.Color.green())
            await msg.reply(embed=embed)
        except asyncio.TimeoutError:
            embed = discord.Embed(title="Zaman Doldu", description=f"{interaction.user.mention}, Üzgünüm, zaman doldu. Doğru cevap: {cevap}", color=discord.Color.red())
            await interaction.followup.send(embed=embed)

    @discord.app_commands.command(name="zar", description="Zar atar ve tahmininizi kontrol eder")
    async def slash_zar(self, interaction: discord.Interaction, bahis: int, tahmin: int):
        await update_user_server(user_id, interaction.guild.id)
        if bahis <= 0 or tahmin < 1 or tahmin > 6:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention}, Geçerli bir bahis miktarı ve tahmin belirtmelisiniz.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        economy = await add_user_to_economy(interaction.user.id, interaction.user.name)
        bakiye = economy[2]
        if bakiye <= 0:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention}, Bakiyeniz 0'dan az olduğu için bu oyunu oynayamazsınız. Quiz veya bilmece çözerek bakiyenizi arttırın.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return
        
        if bahis > bakiye:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention}, Yeterli bakiyeniz yok.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        zar_sayisi = random.randint(1, 6)
        if tahmin == zar_sayisi:
            kazanc = bahis * 3
            new_balance = bakiye + kazanc
            embed = discord.Embed(title="Tebrikler", description=f"{interaction.user.mention} Tebrikler! Zar atılan sayı {zar_sayisi} ve tahmininiz doğru! {kazanc} sikke kazandınız.", color=discord.Color.green())
        else:
            new_balance = bakiye - bahis
            embed = discord.Embed(title="Kaybettiniz", description=f"{interaction.user.mention} Maalesef! Zar atılan sayı {zar_sayisi} ve tahmininiz {tahmin}. Bilemediniz. {bahis} sikke kaybettiniz.", color=discord.Color.red())
        await save_economy(interaction.user.id, interaction.user.name, new_balance)
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="quiz", description="Bir quiz sorusu sorar")
    async def slash_quiz(self, interaction: discord.Interaction):
        await update_user_server(user_id, interaction.guild.id)
        quiz_sorulari = await load_quiz_questions()
        selected_question = random.choice(quiz_sorulari)
        soru, cevap = selected_question["soru"], selected_question["cevap"]
        embed = discord.Embed(title="Quiz", description=f"{interaction.user.mention}, işte bir soru: {soru}", color=discord.Color.blue())
        await interaction.response.send_message(embed=embed)

        def check(msg):
            return msg.author == interaction.user

        try:
            msg = await self.bot.wait_for('message', timeout=30, check=check)
            if msg.content.lower() == cevap.lower():
                embed = discord.Embed(title="Doğru Cevap", description=f"Tebrikler {interaction.user.mention}, doğru cevap! 20 sikke kazandınız.", color=discord.Color.green())
                await msg.reply(embed=embed)
                economy = await add_user_to_economy(interaction.user.id, interaction.user.name)
                new_balance = economy[2] + 20
                await save_economy(interaction.user.id, interaction.user.name, new_balance)
            else:
                embed = discord.Embed(title="Yanlış Cevap", description=f"Üzgünüm {interaction.user.mention}, yanlış cevap. Doğru cevap: {cevap}", color=discord.Color.red())
                await msg.reply(embed=embed)
        except asyncio.TimeoutError:
            embed = discord.Embed(title="Zaman Doldu", description=f"Üzgünüm {interaction.user.mention}, zaman doldu. Doğru cevap: {cevap}", color=discord.Color.red())
            await interaction.followup.send(embed=embed)

    @discord.app_commands.command(name="rulet", description="Rulet oynar")
    async def slash_rulet(self, interaction: discord.Interaction, bahis: int):
        await update_user_server(user_id, interaction.guild.id)
        if bahis <= 0:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention} Geçerli bir bahis miktarı belirtmelisiniz.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        economy = await add_user_to_economy(interaction.user.id, interaction.user.name)
        bakiye = economy[2]
        if bakiye <= 0:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention}, Bakiyeniz 0'dan az olduğu için bu oyunu oynayamazsınız. Quiz veya bilmece çözerek bakiyenizi arttırın.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        if bahis > bakiye:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention} Yeterli bakiyeniz yok.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        kazandi = random.choice([True, False])
        if kazandi:
            new_balance = bakiye + bahis
            embed = discord.Embed(title="Tebrikler", description=f"{interaction.user.mention} Tebrikler! Rulet kazandınız. {bahis} sikke kazandınız.", color=discord.Color.green())
        else:
            new_balance = bakiye - bahis
            embed = discord.Embed(title="Kaybettiniz", description=f"{interaction.user.mention} Maalesef! Rulet kaybettiniz. {bahis} sikke kaybettiniz.", color=discord.Color.red())
        await save_economy(interaction.user.id, interaction.user.name, new_balance)
        await interaction.response.send_message(embed=embed)

    @discord.app_commands.command(name="yazitura", description="Yazı tura oyunu oynar")
    async def slash_yazitura(self, interaction: discord.Interaction, bahis: int, secim: str):
        await update_user_server(user_id, interaction.guild.id)
        if bahis <= 0:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention} Geçerli bir bahis miktarı belirtmelisiniz.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        secim = secim.lower()
        if secim not in ["yazı", "tura"]:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention} Geçerli bir seçim yapmalısınız: yazı veya tura.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        economy = await add_user_to_economy(user_id=interaction.user.id, username=interaction.user.name)
        bakiye = economy[2]
        if bakiye < bahis:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention} Yeterli bakiyeniz yok.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        if bakiye < -100:
            embed = discord.Embed(title="Hata", description=f"{interaction.user.mention} Bakiyeniz -100'den az olduğu için bu oyunu oynayamazsınız. Quiz veya bilmece çözerek bakiyenizi arttırın.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed)
            return

        yanit = random.choice(["yazı", "tura"])

        if secim == yanit:
            kazanc = bahis * 2
            yeni_bakiye = bakiye + kazanc
            await save_economy(interaction.user.id, interaction.user.name, yeni_bakiye)
            embed = discord.Embed(title="Tebrikler", description=f"{interaction.user.mention} Tebrikler! Sonuç {yanit}, tahmininiz doğru! {kazanc} sikke kazandınız.", color=discord.Color.green())
        else:
            yeni_bakiye = bakiye - bahis
            await save_economy(interaction.user.id, interaction.user.name, yeni_bakiye)
            embed = discord.Embed(title="Kaybettiniz", description=f"{interaction.user.mention} Maalesef! Sonuç {yanit}, tahmininiz {secim}. Bilemediniz. {bahis} sikke kaybettiniz.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(Games(bot))

