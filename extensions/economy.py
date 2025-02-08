import discord
from discord.ext import commands
from discord import app_commands
from util import load_economy, save_economy, add_user_to_economy, update_user_server
import aiosqlite
from currency_converter import CurrencyConverter

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="bakiye", description="Bakiyenizi gösterir")
    async def slash_bakiye(self, interaction: discord.Interaction):
        user_id = str(interaction.user.id)
        username = interaction.user.name
        economy = await add_user_to_economy(user_id, username)
        await update_user_server(user_id, interaction.guild.id)
       
        bakiye = economy[2]
        embed = discord.Embed(color=discord.Color.blue())

        if bakiye <= -100:
            embed.title = "Dikkat"
            embed.description = f"{interaction.user.mention} Bakiyeniz -100'den az olamaz, lütfen biraz bilmece veya quiz çözerek bakiyenizi artırın."
        else:
            embed.title = "Bakiyeniz"
            embed.description = f'{interaction.user.mention}, {bakiye} sikkeniz var. :sunglasses: '

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="btransfer", description="Başka bir kullanıcıya bakiye transferi yapar")
    async def slash_btransfer(self, interaction: discord.Interaction, user: discord.Member, amount: int):
        economy = await load_economy(str(interaction.user.id))
        embed = discord.Embed(color=discord.Color.red())

        if not economy or economy[2] < amount:
            embed.title = "Yetersiz Bakiye"
            embed.description = f"{interaction.user.mention}, Yetersiz bakiye."
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        target_economy = await load_economy(str(user.id))
        if not target_economy:
            target_economy = (str(user.id), user.name, 0)

        new_author_balance = economy[2] - amount
        new_target_balance = target_economy[2] + amount

        await save_economy(interaction.user.id, interaction.user.name, new_author_balance)
        await save_economy(user.id, user.name, new_target_balance)

        embed.color = discord.Color.green()
        embed.title = "Transfer Başarılı"
        embed.description = f"{interaction.user.mention}, {amount} sikke, {user.name}'in hesabına aktarıldı."
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @slash_btransfer.error
    async def slash_btransfer_error(self, interaction: discord.Interaction, error):
        embed = discord.Embed(color=discord.Color.red())
        if isinstance(error, commands.MissingRequiredArgument):
            embed.title = "Hata"
            embed.description = f"{interaction.user.mention}, Lütfen bir kullanıcı ve miktar belirtin. Örneğin: `/btransfer @kullanıcı 100`"
        elif isinstance(error, commands.BadArgument):
            embed.title = "Hata"
            embed.description = f"{interaction.user.mention}, Geçerli bir kullanıcı ve miktar belirtmelisiniz. Örneğin: `/btransfer @kullanıcı 100`"
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="siralama", description="En zengin 20 kişiyi sıralar")
    async def slash_siralama(self, interaction: discord.Interaction):
        async with aiosqlite.connect('database/economy.db') as db:
            cursor = await db.execute('SELECT * FROM economy ORDER BY bakiye DESC LIMIT 20')
            rows = await cursor.fetchall()

        sıralama_mesajı = "Sıralama:\n"
        for index, row in enumerate(rows, start=1):
            username = row[1][:-3] + "***" if len(row[1]) > 3 else "***"
            bakiye = row[2]
            sıralama_mesajı += f"{index}. {username} = {bakiye} sikke\n"

        embed = discord.Embed(title="Sıralama", description=sıralama_mesajı, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="sunucu_sikke_siralamasi", description="Sunucudaki üyelerin sikkelerini gösterir")
    async def slash_sunucu_sikke_siralamasi(self, interaction: discord.Interaction):
        await self.update_user_server(interaction.user.id, interaction.guild.id)
        async with aiosqlite.connect('database/economy.db') as db:
            cursor = await db.execute('SELECT username, bakiye FROM economy WHERE sunucu_id = ? ORDER BY bakiye DESC LIMIT 20', (str(interaction.guild.id),))
            rows = await cursor.fetchall()

        siralama_mesaji = "Sunucunun En Zengin 20 Kişisi:\n"
        for index, (username, bakiye) in enumerate(rows, start=1):
            masked_username = username[:-3] + "***" if len(username) > 3 else "***"
            siralama_mesaji += f"{index}. {masked_username} = {bakiye:,} sikke\n"

        embed = discord.Embed(title="Sunucu Sıralaması", description=siralama_mesaji, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def update_user_server(self, user_id: int, server_id: int):
        async with aiosqlite.connect('database/economy.db') as db:
            await db.execute('INSERT OR IGNORE INTO economy (user_id, sunucu_id, bakiye) VALUES (?, ?, 0)', (user_id, server_id))
            await db.commit()


    @app_commands.command(name="dolar", description="1 Dolar'ın TL karşılığını gösterir")
    async def slash_dolar(self, interaction: discord.Interaction):
        try:
            c = CurrencyConverter()
            amount = c.convert(1, 'USD', 'TRY')
            embed = discord.Embed(title="Döviz Kuru", description=f"{interaction.user.mention} 1 dolar {amount:.2f} TL ediyor!", color=discord.Color.green())
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            embed = discord.Embed(title="Hata", description="Döviz kurunu alırken bir hata oluştu.", color=discord.Color.red())
            await interaction.response.send_message(embed=embed, ephemeral=True)

    async def cog_unload(self):
        # Veritabanı bağlantılarını kapat
        if hasattr(self, 'db'):
            await self.db.close()

async def setup(bot):
    await bot.add_cog(Economy(bot))

