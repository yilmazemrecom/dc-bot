import discord
from discord.ext import commands
import random

class GameSelector(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.app_commands.command(name="oyun_sec", description="Girilen oyunlar arasından rastgele seçim yapar")
    @discord.app_commands.describe(
        oyunlar="Oyun seçenekleri (virgülle ayırın, örn: Cyberpunk 2077, GTA V, Witcher 3)",
        secim_sayisi="Seçilecek oyun sayısı (varsayılan: 1)"
    )
    async def game_selector(self, interaction: discord.Interaction, oyunlar: str, secim_sayisi: int = 1):
        games_list = [game.strip() for game in oyunlar.split(',') if game.strip()]
        
        if not games_list:
            await interaction.response.send_message("❌ En az bir oyun belirtmelisiniz!", ephemeral=True)
            return

        if len(games_list) > 20:
            await interaction.response.send_message("❌ En fazla 20 oyun belirtebilirsiniz!", ephemeral=True)
            return

        if secim_sayisi < 1 or secim_sayisi > len(games_list):
            await interaction.response.send_message(f"❌ Seçim sayısı 1-{len(games_list)} arasında olmalı!", ephemeral=True)
            return

        if secim_sayisi > 10:
            await interaction.response.send_message("❌ En fazla 10 oyun seçebilirsiniz!", ephemeral=True)
            return

        selected_games = random.sample(games_list, secim_sayisi)

        if secim_sayisi == 1:
            embed = discord.Embed(
                title="🎮 Oyun Seçildi!",
                description=f"**Seçilen Oyun:** {selected_games[0]}",
                color=discord.Color.green()
            )
        else:
            games_text = "\n".join([f"• {game}" for game in selected_games])
            embed = discord.Embed(
                title="🎮 Oyunlar Seçildi!",
                description=f"**Seçilen Oyunlar ({secim_sayisi} adet):**\n{games_text}",
                color=discord.Color.green()
            )

        

        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(GameSelector(bot))