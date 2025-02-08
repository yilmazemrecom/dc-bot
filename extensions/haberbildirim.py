from config import TELEGRAM_BOT_TOKEN
from config import TELEGRAM_CHANNEL_ID
import requests
import discord
from discord.ext import commands, tasks
import aiosqlite


class HaberBildirim(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_update_id = None
        self.bot.loop.create_task(self.init_db())
        self.check_telegram_channel.start()  # Bot açıldığında döngü başlar
        print("Haberbildirim initialized and check_telegram_channel started.")

    async def init_db(self):
        self.conn = await aiosqlite.connect('database/haber.db')
        self.c = await self.conn.cursor()
        await self.c.execute('''
            CREATE TABLE IF NOT EXISTS NewsNotifyChannels (
                guild_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            )
        ''')
        await self.conn.commit()
        print("Database initialized.")

    def cog_unload(self):
        self.check_telegram_channel.cancel()
        if self.conn:
            asyncio.create_task(self.conn.close())
        print("Haberbildirim cog unloaded.")

    @discord.app_commands.command(name="haberbildirimac", description="Belirtilen kanalda Telegram bildirimlerini açar")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def haberbildirimac(self, interaction: discord.Interaction, kanal: discord.TextChannel):
        await self.c.execute('INSERT OR REPLACE INTO NewsNotifyChannels (guild_id, channel_id) VALUES (?, ?)',
                             (interaction.guild.id, kanal.id))
        await self.conn.commit()
        print(f"Telegram notifications enabled in guild {interaction.guild.id}, channel {kanal.id}.")

        await interaction.response.send_message(f"Telegram'dan gelen mesajlar, belirttiğiniz {kanal.mention} kanalında paylaşılacak.", ephemeral=True)

    @discord.app_commands.command(name="haberbildirimkapat", description="Belirtilen kanalda Telegram bildirimlerini kapatır")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def haberbildirimkapat(self, interaction: discord.Interaction, kanal: discord.TextChannel):
        await self.c.execute('DELETE FROM NewsNotifyChannels WHERE guild_id = ? AND channel_id = ?',
                             (interaction.guild.id, kanal.id))
        await self.conn.commit()
        print(f"Telegram notifications disabled in guild {interaction.guild.id}, channel {kanal.id}.")

        await interaction.response.send_message(f"Telegram'dan gelen mesajlar {kanal.mention} kanalında paylaşılmayacak.", ephemeral=True)

    @tasks.loop(seconds=10.0)
    async def check_telegram_channel(self):
        url = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates'
        if self.last_update_id:
            url += f'?offset={self.last_update_id + 1}'
        
        response = requests.get(url)
        data = response.json()

        if 'result' in data:
            for update in data['result']:
                if 'channel_post' in update:
                    message = update['channel_post']
                    chat_id = message['chat']['id']
                    
                    if str(chat_id) == TELEGRAM_CHANNEL_ID:
                        print("Channel ID matched, processing message...")
                        self.last_update_id = update['update_id']

                        text = message.get('text', '')
                        caption = message.get('caption', '')
                        photos = message.get('photo', [])

                        # Metin veya açıklama varsa işle
                        if text or caption:
                            content = text if text else caption
                            embed = discord.Embed(
                                title="Çaycı Haber Bildirimi",
                                description=content,
                                color=discord.Color.green(),
                            )

                            if photos:
                                first_photo = photos[-1]
                                file_id = first_photo['file_id']
                                file_path_response = requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}")
                                
                                if file_path_response.status_code == 200 and 'result' in file_path_response.json():
                                    file_path = file_path_response.json()['result']['file_path']
                                    media_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
                                    embed.set_image(url=media_url)

                            embed.set_footer(text="Kaynak: Mint Haber")

                            await self.c.execute('SELECT guild_id, channel_id FROM NewsNotifyChannels')
                            channels = await self.c.fetchall()

                            for guild_id, channel_id in channels:
                                discord_channel = self.bot.get_channel(int(channel_id))
                                if discord_channel:
                                    await discord_channel.send(embed=embed)
                                    print(f"Sent message and media to guild {guild_id}, channel {channel_id}.")
                                else:
                                    print(f"Channel {channel_id} not found in guild {guild_id}.")

                        # Bu güncelleme işlendi, sıradakine geç
                        continue

            # Tüm güncellemeleri işledikten sonra fonksiyonu sonlandır
            return

    @check_telegram_channel.before_loop
    async def before_check_telegram_channel(self):
        await self.bot.wait_until_ready()
        print("Bot is ready, starting check_telegram_channel loop.")

async def setup(bot):
    await bot.add_cog(HaberBildirim(bot))
    print("Haberbildirim cog loaded.")
