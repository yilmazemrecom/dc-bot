from discord.ext import commands
import discord
from util import add_user_to_economy

class Responses(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author == self.bot.user:
            return

        await add_user_to_economy(user_id=message.author.id, username=message.author.name)

        content = message.content.lower()
        responses = {
            "selam": "Merhaba!",
            "nasılsın": "iyiyim, sen nasılsın?",
            "hoş geldin": "Teşekkürler!",
            "görüşürüz": "Görüşmek üzere!",
            "merhaba": "Merhabana merhaba kardeş!",
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

        for keyword, response in responses.items():
            if keyword in content:
                await message.channel.send(f"{message.author.mention}, {response}")
                return

        if "dolar" in content:
            try:
                from currency_converter import CurrencyConverter
                c = CurrencyConverter()
                amount = c.convert(1, 'USD', 'TRY')
                await message.channel.send(f"{message.author.mention}, 1 dolar {amount:.2f} TL ediyor!")
            except Exception as e:
                await message.channel.send(f"{message.author.mention}, döviz kurunu alırken bir hata oluştu: {str(e)}")

        elif "çay" in content:
            await message.channel.send("https://tenor.com/view/çaylar-çaycıhüseyin-gif-18623727")

async def setup(bot):
    await bot.add_cog(Responses(bot))
