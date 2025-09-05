import discord
from discord.ext import commands
from discord.ui import Button, View
import random


MAX_ACTIVE_DUELS_PER_USER = 1

class DuelGame:
    def __init__(self, player1, player2):
        self.player1 = player1
        self.player2 = player2
        self.player1_hp = 100
        self.player2_hp = 100
        self.player1_ammo = {"Roketatar": 1, "El Bombası": 2, "Bandaj": 2, "Dron": 1}
        self.player2_ammo = {"Roketatar": 1, "El Bombası": 2, "Bandaj": 2, "Dron": 1}
        self.turn = player1





    def get_status_embed(self):
        embed = discord.Embed(title="Düello Durumu", color=discord.Color.blue())
        embed.add_field(name=f"{self.player1.display_name} Durumu", value=(
            f"Can: {'█' * (self.player1_hp // 10)}{'░' * (10 - (self.player1_hp // 10))} {self.player1_hp}%\n"
            f"Cephane\n"
            f"🔫 Piyade Tüfeği: Sınırsız\n"
            f"🎯 Dron: {self.player1_ammo['Dron']}x\n"
            f"🚀 Roketatar: {self.player1_ammo['Roketatar']}x\n"
            f"💣 El Bombası: {self.player1_ammo['El Bombası']}x\n"
            f"🩹 Bandaj: {self.player1_ammo['Bandaj']}x"
        ), inline=False)
        embed.add_field(name=f"{self.player2.display_name} Durumu", value=(
            f"Can: {'█' * (self.player2_hp // 10)}{'░' * (10 - (self.player2_hp // 10))} {self.player2_hp}%\n"
            f"Cephane\n"
            f"🔫 Piyade Tüfeği: Sınırsız\n"
            f"🎯 Dron: {self.player2_ammo['Dron']}x\n"
            f"🚀 Roketatar: {self.player2_ammo['Roketatar']}x\n"
            f"💣 El Bombası: {self.player2_ammo['El Bombası']}x\n"
            f"🩹 Bandaj: {self.player2_ammo['Bandaj']}x"
        ), inline=False)
        embed.set_footer(text=f"Sıradaki hamle: {self.turn.display_name}")
        return embed

    def attack(self, weapon):
        ptufek_attack = random.randint(5, 10)
        dron_attack = random.randint(10, 20)
        rocket_attack = random.randint(20, 30)
        el_bombasi_attack = random.randint(10, 20)
        damage = {"Piyade Tüfeği": ptufek_attack, "Dron": dron_attack, "Roketatar": rocket_attack, "Bıçak": 5, "El Bombası": el_bombasi_attack}
        ammo = self.player1_ammo if self.turn == self.player1 else self.player2_ammo

        if weapon not in ["Piyade Tüfeği", "Bıçak"]:
            if ammo[weapon] > 0:
                ammo[weapon] -= 1
            else:
                return f"{self.turn.mention}, {weapon} için yeterli cephaneniz yok!", False
        
        if self.turn == self.player1:
            self.player2_hp -= damage[weapon]
            result = f"{self.turn.mention}, {weapon} ile saldırdı! {self.player2.mention} {damage[weapon]} can kaybetti."
            self.turn = self.player2
        else:
            self.player1_hp -= damage[weapon]
            result = f"{self.turn.mention}, {weapon} ile saldırdı! {self.player1.mention} {damage[weapon]} can kaybetti."
            self.turn = self.player1

        game_over = self.player1_hp <= 0 or self.player2_hp <= 0
        if game_over:
            winner = self.player1 if self.player1_hp > 0 else self.player2
            return f"{result}\n\n{winner.mention} kazandı!", True
        return result, False

    def heal(self):
        if self.turn == self.player1:
            ammo = self.player1_ammo
            hp = self.player1_hp
            current_player = self.player1
        else:
            ammo = self.player2_ammo
            hp = self.player2_hp
            current_player = self.player2

        if hp == 100:
            return f"{current_player.mention}, canınız zaten dolu!", False

        if ammo["Bandaj"] > 0:
            ammo["Bandaj"] -= 1
            hp = min(100, hp + 25)

            if self.turn == self.player1:
                self.player1_hp = hp
            else:
                self.player2_hp = hp

            self.turn = self.player1 if self.turn == self.player2 else self.player2

            return f"{current_player.mention} bir bandaj kullandı ve 25 can kazandı.", False
        else:
            return f"{current_player.mention}, bandajınız kalmadı!", False


    def surrender(self):
        winner = self.player2 if self.turn == self.player1 else self.player1
        return f"{self.turn.mention} teslim oldu! {winner.mention} kazandı!"

duels = {}

class DuelView(View):
    def __init__(self, duel):
        super().__init__(timeout=None)
        self.duel = duel

    async def handle_attack(self, interaction: discord.Interaction, weapon):
        result, game_over = self.duel.attack(weapon)
        embed = self.duel.get_status_embed()
        if game_over:
            await interaction.response.edit_message(content=result, embed=embed, view=None)
            del duels[self.duel.player1.id]
            del duels[self.duel.player2.id]
        else:
            await interaction.response.edit_message(content=result, embed=embed, view=self)

    async def handle_heal(self, interaction: discord.Interaction):
        result, game_over = self.duel.heal()
        embed = self.duel.get_status_embed()
        if game_over:
            await interaction.response.edit_message(content=result, embed=embed, view=None)
            del duels[self.duel.player1.id]
            del duels[self.duel.player2.id]
        else:
            await interaction.response.edit_message(content=result, embed=embed, view=self)

    @discord.ui.button(label="Piyade Tüfeği", emoji="🔫", style=discord.ButtonStyle.secondary)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.duel.turn:
            await interaction.response.send_message("Sıra sizde değil!", ephemeral=True)
            return
        await self.handle_attack(interaction, "Piyade Tüfeği")

    @discord.ui.button(label="Dron", emoji="🎯", style=discord.ButtonStyle.secondary)
    async def special_attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.duel.turn:
            await interaction.response.send_message("Sıra sizde değil!", ephemeral=True)
            return
        await self.handle_attack(interaction, "Dron")

    @discord.ui.button(label="Roketatar", emoji="🚀", style=discord.ButtonStyle.secondary)
    async def rocket_attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.duel.turn:
            await interaction.response.send_message("Sıra sizde değil!", ephemeral=True)
            return
        await self.handle_attack(interaction, "Roketatar")

    @discord.ui.button(label="Bıçak", emoji="🔪", style=discord.ButtonStyle.secondary)
    async def knife_attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.duel.turn:
            await interaction.response.send_message("Sıra sizde değil!", ephemeral=True)
            return
        await self.handle_attack(interaction, "Bıçak")

    @discord.ui.button(label="El Bombası", emoji="💣", style=discord.ButtonStyle.secondary)
    async def grenade_attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.duel.turn:
            await interaction.response.send_message("Sıra sizde değil!", ephemeral=True)
            return
        await self.handle_attack(interaction, "El Bombası")

    @discord.ui.button(label="Bandaj", emoji="🩹", style=discord.ButtonStyle.secondary)
    async def heal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.duel.turn:
            await interaction.response.send_message("Sıra sizde değil!", ephemeral=True)
            return
        await self.handle_heal(interaction)

    @discord.ui.button(label="Teslim Ol", emoji="🏳️", style=discord.ButtonStyle.red)
    async def surrender_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.duel.turn:
            await interaction.response.send_message("Sıra sizde değil!", ephemeral=True)
            return
        result = self.duel.surrender()
        await interaction.response.edit_message(content=result, view=None)
        del duels[self.duel.player1.id]
        del duels[self.duel.player2.id]

class DuelCog(commands.Cog):
    @commands.cooldown(1, 60, commands.BucketType.user)  
    def __init__(self, bot):
        self.bot = bot
        

    @discord.app_commands.command(name="pvp", description="Başka bir oyuncuyla düello yaparsınız")
    async def slash_duello(self, interaction: discord.Interaction, kullanıcı: discord.Member):
        active_duels = sum(1 for duel in duels.values() if interaction.user.id in (duel.player1.id, duel.player2.id))
        if active_duels >= MAX_ACTIVE_DUELS_PER_USER:
            await interaction.response.send_message("Zaten aktif bir düellonuz var. Lütfen mevcut düellonuzu bitirin.", ephemeral=True)
            return      
        if interaction.user.id in duels or kullanıcı.id in duels:
            await interaction.response.send_message("Bir oyuncu zaten bir düello yapıyor!", ephemeral=True)
            return

        if kullanıcı.bot:
            await interaction.response.send_message("Botlarla düello yapamazsınız!", ephemeral=True)
            return

        invite = DuelInvite(interaction.user, kullanıcı)
        duel_invites[kullanıcı.id] = invite

        view = DuelInviteView(invite)
        await interaction.response.send_message(
            f"{kullanıcı.mention}, {interaction.user.mention} sizi düelloya davet ediyor! Kabul ediyor musunuz?",
            view=view
        )
        view.message = await interaction.original_response()

    @slash_duello.error
    async def duello_error(self, interaction: discord.Interaction, error):
        if isinstance(error, commands.CommandOnCooldown):
            await interaction.response.send_message(f"Bu komutu çok sık kullanıyorsunuz. Lütfen {error.retry_after:.2f} saniye sonra tekrar deneyin.", ephemeral=True)


class DuelInvite:
    def __init__(self, challenger, challenged):
        self.challenger = challenger
        self.challenged = challenged

duel_invites = {}

class DuelInviteView(discord.ui.View):
    def __init__(self, invite):
        super().__init__(timeout=60)
        self.invite = invite
        self.message = None

    @discord.ui.button(label="Kabul Et", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.invite.challenged:
            await interaction.response.send_message("Bu daveti sadece davet edilen kişi kabul edebilir!", ephemeral=True)
            return

        del duel_invites[self.invite.challenged.id]
        duel = DuelGame(self.invite.challenger, self.invite.challenged)
        duels[self.invite.challenger.id] = duel
        duels[self.invite.challenged.id] = duel

        view = DuelView(duel)
        embed = duel.get_status_embed()
        await interaction.response.edit_message(content=f"Düello başladı! {self.invite.challenger.mention} ile {self.invite.challenged.mention} savaşıyor!", embed=embed, view=view)
        self.stop()

    @discord.ui.button(label="Reddet", style=discord.ButtonStyle.red)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.invite.challenged:
            await interaction.response.send_message("Bu daveti sadece davet edilen kişi reddedebilir!", ephemeral=True)
            return

        del duel_invites[self.invite.challenged.id]
        self.message = interaction.message
        await interaction.response.edit_message(content=f"{self.invite.challenged.mention} düello davetini reddetti.", view=None)

    async def on_timeout(self):
        if self.invite.challenged.id in duel_invites:
            del duel_invites[self.invite.challenged.id]
        try:
            await self.message.edit(content="Düello daveti zaman aşımına uğradı.", view=None)
        except:
            pass

async def setup(bot):
    await bot.add_cog(DuelCog(bot))