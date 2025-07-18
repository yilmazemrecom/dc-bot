import discord
from discord.ext import commands
from discord import app_commands
from util import load_economy, save_economy, add_user_to_economy, update_user_server
import aiosqlite
from currency_converter import CurrencyConverter
import logging

logger = logging.getLogger(__name__)

class Economy(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.sikke_sku_id = "1387057245036216391"  # Sizin 10000 sikke SKU ID'niz

    # ✅ Discord Entitlement Event'leri
    @commands.Cog.listener()
    async def on_entitlement_create(self, entitlement):
        """Sikke satın alındığında tetiklenir"""
        logger.info(f"💰 Yeni satın alma: {entitlement}")
        
        user_id = str(entitlement.user_id)
        sku_id = str(entitlement.sku_id)
        
        # 10000 sikke SKU'su satın alındı mı?
        if sku_id == self.sikke_sku_id:
            try:
                # Kullanıcıyı economy sistemine ekle
                economy = await add_user_to_economy(user_id, "User")
                
                # Mevcut bakiyeye 10000 sikke ekle
                current_balance = economy[2] if economy else 0
                new_balance = current_balance + 10000
                
                # Bakiyeyi güncelle
                await save_economy(int(user_id), "User", new_balance)
                
                # Kullanıcıya bildirim gönder
                try:
                    user = await self.bot.fetch_user(int(user_id))
                    embed = discord.Embed(
                        title="🎉 Satın Alma Tamamlandı!",
                        description="**10,000 sikke** hesabınıza başarıyla eklendi!",
                        color=discord.Color.gold(),
                        timestamp=discord.utils.utcnow()
                    )
                    
                    embed.add_field(
                        name="💰 Güncel Bakiye",
                        value=f"**{new_balance:,}** sikke",
                        inline=True
                    )
                    
                    embed.add_field(
                        name="☕ Kullanabileceğiniz Yerler",
                        value="• Transfer işlemleri\n• Özel komutlar\n• Gelecek özellikler",
                        inline=False
                    )
                    
                    embed.set_footer(text="Çaycı Bot", icon_url=self.bot.user.avatar.url if self.bot.user.avatar else None)
                    
                    await user.send(embed=embed)
                    logger.info(f"✅ 10,000 sikke eklendi: {user_id}, Yeni bakiye: {new_balance}")
                    
                except discord.HTTPException as e:
                    logger.error(f"DM gönderilemedi {user_id}: {e}")
                    
            except Exception as e:
                logger.error(f"Sikke ekleme hatası {user_id}: {e}")



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
            embed.title = "💰 Bakiyeniz"
            embed.description = f'{interaction.user.mention}, **{bakiye:,}** sikkeniz var. :sunglasses:'
            
            # Sikke satın alma bilgisi (eğer bakiye düşükse)
            if bakiye < 1000:
                embed.add_field(
                    name="☕ Sikke Satın Al",
                    value="Discord'un Çaycı mağazasından sikke satın alabilirsiniz!",
                    inline=False
                )

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.app_commands.command(name="btransfer")
    @discord.app_commands.describe(
        kullanici="Sikke göndermek istediğiniz kullanıcı",
        miktar="Göndermek istediğiniz sikke miktarı (minimum 1)"
    )
    async def slash_btransfer(self, interaction: discord.Interaction,
        kullanici: discord.Member,
        miktar: app_commands.Range[int, 1, None]
    ):
        # Bot'lara transfer engeli
        if kullanici.bot:
            embed = discord.Embed(
                title="❌ Hata",
                description="Bot'lara sikke transfer edemezsiniz!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        
        # Kendine transfer engeli
        if kullanici.id == interaction.user.id:
            embed = discord.Embed(
                title="❌ Hata", 
                description="Kendinize sikke transfer edemezsiniz!",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        economy = await load_economy(str(interaction.user.id))
        embed = discord.Embed(color=discord.Color.red())

        if not economy or economy[2] < miktar:
            embed.title = "❌ Yetersiz Bakiye"
            embed.description = f"{interaction.user.mention}, Yetersiz bakiye."
            embed.add_field(
                name="💡 Nasıl Sikke Alırım?",
                value="Discord'un Çaycı mağazasından sikke satın alabilirsiniz!",
                inline=False
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        target_economy = await load_economy(str(kullanici.id))
        if not target_economy:
            target_economy = (str(kullanici.id), kullanici.name, 0)

        new_author_balance = economy[2] - miktar
        new_target_balance = target_economy[2] + miktar

        await save_economy(interaction.user.id, interaction.user.name, new_author_balance)
        await save_economy(kullanici.id, kullanici.name, new_target_balance)

        embed.color = discord.Color.green()
        embed.title = "✅ Transfer Başarılı"
        embed.description = f"{interaction.user.mention}, **{miktar:,}** sikke {kullanici.mention}'in hesabına aktarıldı."
        embed.add_field(name="💰 Kalan Bakiyeniz", value=f"{new_author_balance:,} sikke", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        # Alıcıya bildirim gönder
        try:
            receiver_embed = discord.Embed(
                title="💰 Sikke Aldınız!",
                description=f"{interaction.user.mention}'den **{miktar:,}** sikke aldınız!",
                color=discord.Color.gold()
            )
            receiver_embed.add_field(name="💰 Yeni Bakiyeniz", value=f"{new_target_balance:,} sikke", inline=True)
            await kullanici.send(embed=receiver_embed)
        except:
            pass  # DM gönderilemezse sessizce geç

    @slash_btransfer.error
    async def slash_btransfer_error(self, interaction: discord.Interaction, error):
        embed = discord.Embed(color=discord.Color.red())
        if isinstance(error, commands.MissingRequiredArgument):
            embed.title = "❌ Hata"
            embed.description = f"{interaction.user.mention}, Lütfen bir kullanıcı ve miktar belirtin. Örneğin: `/btransfer @kullanıcı 100`"
        elif isinstance(error, commands.BadArgument):
            embed.title = "❌ Hata"
            embed.description = f"{interaction.user.mention}, Geçerli bir kullanıcı ve miktar belirtmelisiniz. Örneğin: `/btransfer @kullanıcı 100`"
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="siralama", description="En zengin 20 kişiyi sıralar")
    async def slash_siralama(self, interaction: discord.Interaction):
        async with aiosqlite.connect('database/economy.db') as db:
            cursor = await db.execute('SELECT * FROM economy ORDER BY bakiye DESC LIMIT 20')
            rows = await cursor.fetchall()

        sıralama_mesajı = "🏆 **Global Sıralama**\n\n"
        for index, row in enumerate(rows, start=1):
            username = row[1][:-3] + "***" if len(row[1]) > 3 else "***"
            bakiye = row[2]
            
            # Medalya emojileri
            medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"{index}."
            sıralama_mesajı += f"{medal} {username} = **{bakiye:,}** sikke\n"

        embed = discord.Embed(
            title="💰 En Zengin Kullanıcılar", 
            description=sıralama_mesajı, 
            color=discord.Color.gold()
        )
        embed.set_footer(text="Çaycı Economy System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="sunucu_sikke_siralamasi", description="Sunucudaki üyelerin sikkelerini gösterir")
    async def slash_sunucu_sikke_siralamasi(self, interaction: discord.Interaction):
        await self.update_user_server(interaction.user.id, interaction.guild.id)
        async with aiosqlite.connect('database/economy.db') as db:
            cursor = await db.execute('SELECT username, bakiye FROM economy WHERE sunucu_id = ? ORDER BY bakiye DESC LIMIT 20', (str(interaction.guild.id),))
            rows = await cursor.fetchall()

        siralama_mesaji = f"🏆 **{interaction.guild.name} Sıralaması**\n\n"
        for index, (username, bakiye) in enumerate(rows, start=1):
            masked_username = username[:-3] + "***" if len(username) > 3 else "***"
            medal = "🥇" if index == 1 else "🥈" if index == 2 else "🥉" if index == 3 else f"{index}."
            siralama_mesaji += f"{medal} {masked_username} = **{bakiye:,}** sikke\n"

        embed = discord.Embed(
            title="💰 Sunucu Sıralaması", 
            description=siralama_mesaji, 
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"{interaction.guild.name} • Çaycı")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def update_user_server(self, user_id: int, server_id: int):
        async with aiosqlite.connect('database/economy.db') as db:
            await db.execute('INSERT OR IGNORE INTO economy (user_id, sunucu_id, bakiye) VALUES (?, ?, 0)', (user_id, server_id))
            await db.commit()


    async def cog_unload(self):
        # Veritabanı bağlantılarını kapat
        if hasattr(self, 'db'):
            await self.db.close()



async def setup(bot):
    await bot.add_cog(Economy(bot))