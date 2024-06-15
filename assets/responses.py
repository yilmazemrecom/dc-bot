from discord.ext import commands
import discord


class Responses(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        # Bu fonksiyonun tanımlı olduğundan emin olun
        # await add_user_to_economy(user_id=message.author.id, username=message.author.name)

        content = message.content.lower()
        responses = {
            "çaycı": "çay mı istiyon? :teapot: ",
        }

        for keyword, response in responses.items():
            if keyword in content:
                await message.channel.send(f"{message.author.mention}, {response}")
                return

        if "çay" in content:
            await message.channel.send("https://tenor.com/view/çaylar-çaycıhüseyin-gif-18623727")




async def setup(bot):
    await bot.add_cog(Responses(bot))
