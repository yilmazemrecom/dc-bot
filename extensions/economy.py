from discord.ext import commands
from util import load_economy, save_economy, add_user_to_economy
import aiosqlite
import discord
from currency_converter import CurrencyConverter


class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command()
    async def bakiye(self, ctx):
        user_id = str(ctx.author.id)
        username = ctx.author.name
        economy = await add_user_to_economy(user_id, username)
        bakiye = economy[2]
        if bakiye <= -100:
            await ctx.send(f"{ctx.author.mention} Bakiyeniz -100'den az olamaz, lütfen biraz bilmece veya quiz çözerek bakiyenizi artırın.")
        else:
            await ctx.send(f'{ctx.author.mention}, {bakiye} sikkeniz var. :sunglasses: ')

    @commands.command()
    async def btransfer(self, ctx, user: discord.Member, amount: int):
        economy = await load_economy(str(ctx.author.id))
        if not economy or economy[2] < amount:
            await ctx.send(f"{ctx.author.mention},Yetersiz bakiye.")
            return

        target_economy = await load_economy(str(user.id))
        if not target_economy:
            target_economy = (str(user.id), user.name, 0)

        new_author_balance = economy[2] - amount
        new_target_balance = target_economy[2] + amount

        await save_economy(ctx.author.id, ctx.author.name, new_author_balance)
        await save_economy(user.id, user.name, new_target_balance)
        await ctx.send(f"{ctx.author.mention}, {amount} sikke, {user.name}'in hesabına aktarıldı.")

    @btransfer.error
    async def btransfer_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{ctx.author.mention},Lütfen bir kullanıcı ve miktar belirtin. Örneğin: `!btransfer @kullanıcı 100`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"{ctx.author.mention}, Geçerli bir kullanıcı ve miktar belirtmelisiniz. Örneğin: `!btransfer @kullanıcı 100`")


    @commands.command()
    async def siralama(self, ctx):
        async with aiosqlite.connect('database/economy.db') as db:
            cursor = await db.execute('SELECT * FROM economy ORDER BY bakiye DESC LIMIT 20')
            rows = await cursor.fetchall()

        sıralama_mesajı = "Sıralama:\n"
        for index, row in enumerate(rows, start=1):
            username = row[1][:-3] + "***" if len(row[1]) > 3 else "***"
            bakiye = row[2]
            sıralama_mesajı += f"{index}. {username} = {bakiye} sikke\n"

        await ctx.send(sıralama_mesajı)

    @commands.command()
    async def dolar(self, ctx):
        try:
            from currency_converter import CurrencyConverter
            c = CurrencyConverter()
            amount = c.convert(1, 'USD', 'TRY')
            await ctx.send(f"{ctx.author.mention} 1 dolar {amount:.2f} TL ediyor!")
        except Exception as e:
            await ctx.send(f"Döviz kurunu alırken bir hata oluştu.")



async def setup(bot):
    await bot.add_cog(Economy(bot))
