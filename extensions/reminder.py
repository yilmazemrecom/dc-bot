import os
import json
import aiofiles
from datetime import timezone, datetime, timedelta
from typing import Optional, List, Dict, Any
import discord
from discord.ext import commands, tasks
from discord import Embed, Color


class Reminder(commands.Cog):
    BASE_PATH = './json/reminders/'

    def __init__(self, bot):
        self.bot = bot
        self.check_reminders.start()

    @discord.app_commands.command(name='hatirlatici_ekle', description='Yeni bir hatırlatıcı ekle')
    async def hatirlatici_ekle(self, interaction: discord.Interaction, icerik: str, gun: int, saat: int, dakika: int):
        """
        Hatırlatıcı ekler.
        :param icerik: Hatırlatıcı içeriği
        :param gun: Kaç gün sonra
        :param saat: Kaç saat sonra
        :param dakika: Kaç dakika sonra
        """
        user_id = interaction.user.id
        try:
            current_time = datetime.now(timezone.utc)
            reminder_time = current_time + timedelta(days=gun, hours=saat, minutes=dakika)
            await Reminder.add(user_id, icerik, reminder_time)
            turkey_time = reminder_time + timedelta(hours=3)
            embed = discord.Embed(
                title="🔔 Yeni Hatırlatıcı Eklendi!",
                description=f"**{interaction.user.name}**, hatırlatıcınız başarıyla ayarlandı.",
                color=discord.Color.green()
            )
            embed.add_field(name="📝 İçerik", value=icerik, inline=False)
            embed.add_field(name="🕰️ Zaman", value=turkey_time.strftime('%d %B %Y, %H:%M'), inline=False)
            embed.set_footer(text="CayciBot - Sizin dijital çaycınız | caycibot.com.tr")
            
            await interaction.response.send_message(embed=embed)

        except ValueError as e:
            await interaction.response.send_message(f"Geçersiz zaman: {str(e)}")

    @discord.app_commands.command(name='hatirlatici_sil', description='Bir hatırlatıcı sil')
    async def hatirlatici_sil(self, interaction: discord.Interaction, hatirlatici_id: int):
        user_id = interaction.user.id
        await Reminder.delete(user_id, hatirlatici_id)
        await interaction.response.send_message(f"Hatırlatıcı silindi: {hatirlatici_id}")

    @discord.app_commands.command(name='hatirlaticilar', description='Tüm hatırlatıcıları listele')
    async def hatirlaticilar(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        reminders = await Reminder.get_reminders(user_id)

        if reminders:
            embed = Embed(
                title="⏰ Mevcut Hatırlatıcılar",
                description=f"{interaction.user.name}, işte ayarladığınız hatırlatıcılar:",
                color=Color.blue()
            )

            for r in reminders:
                reminder_time = (datetime.fromtimestamp(r['timestamp'], tz=timezone.utc) + timedelta(hours=3)).strftime('%Y-%m-%d %H:%M')
                embed.add_field(
                    name=f"📝 Hatırlatıcı {r['id']}", 
                    value=f"**İçerik:** {r['content']}\n**Zaman:** {reminder_time} (Türkiye saati)", 
                    inline=False
                )

            embed.set_footer(text="ÇaycıBot - Sizin dijital çaycınız | caycibot.com.tr")
            await interaction.response.send_message(embed=embed)
        
        else:
            await interaction.response.send_message("Hiç hatırlatıcı yok.")

    @tasks.loop(minutes=1)
    async def check_reminders(self):
        await self.bot.wait_until_ready()
        current_time = datetime.now(timezone.utc).timestamp()
        for filename in os.listdir(Reminder.BASE_PATH):
            if filename.endswith("_reminders.json"):
                user_id = int(filename.split('_')[0])
                reminders = await Reminder.get_reminders(user_id)
                for reminder in reminders:
                    if reminder['timestamp'] <= current_time:
                        await self.send_dm(user_id, reminder['content'])
                        await Reminder.delete(user_id, reminder['id'])

    async def send_dm(self, user_id: int, content: str):
        try:
            user = await self.bot.fetch_user(user_id)
            if user:
                embed = discord.Embed(
                    title="🔔 Hatırlatıcı Zamanı!",
                    description=content,
                    color=discord.Color.blue()
                )
                embed.set_author(name="CayciBot", icon_url="https://caycibot.com.tr/static/images/logo.png")
                current_time = datetime.now(timezone.utc) + timedelta(hours=3)
                embed.add_field(name="📅 Tarih", value=current_time.strftime("%d.%m.%Y"), inline=True)
                embed.add_field(name="⏰ Saat", value=current_time.strftime("%H:%M"), inline=True)
                embed.set_footer(text="CayciBot - Sizin dijital çaycınız | caycibot.com.tr")
                
                await user.send(embed=embed)
                print(f"Hatırlatıcı gönderildi: {user_id} - {content}")
            else:
                print(f"Kullanıcı bulunamadı: {user_id}.")
        except discord.NotFound:
            print(f"Kullanıcı bulunamadı: {user_id}.")
        except discord.Forbidden:
            print(f"Kullanıcı {user_id} DM'leri kapalı.")
        except Exception as e:
            print(f"Mesaj gönderim hatası: {e}")

    @staticmethod
    def current_time() -> float:
        return datetime.now(timezone.utc).timestamp()

    @staticmethod
    def has_expired(timestamp: float) -> bool:
        return timestamp <= Reminder.current_time()

    @classmethod
    async def add(cls, user_id: int, content: str, reminder_time: datetime) -> None:
        timestamp = reminder_time.timestamp()
        user_file = cls.get_user_file(user_id)
        reminders = await cls.get_reminders(user_id)
        reminder_id = max([r["id"] for r in reminders], default=-1) + 1

        reminder_context = {
            "id": reminder_id,
            "content": content,
            "timestamp": timestamp
        }

        reminders.append(reminder_context)
        await cls.save_reminders(user_id, reminders)

    @classmethod
    async def delete(cls, user_id: int, reminder_id: int) -> None:
        reminders = await cls.get_reminders(user_id)
        reminder = cls.find_reminder(reminders, reminder_id)

        if reminder:
            reminders.remove(reminder)
            await cls.save_reminders(user_id, reminders)
        else:
            print(f"There is no reminder with ID {reminder_id}!")

    @classmethod
    def find_reminder(cls, reminders: List[Dict[str, Any]], reminder_id: int) -> Optional[Dict[str, Any]]:
        return next((reminder for reminder in reminders if reminder["id"] == reminder_id), None)

    @classmethod
    async def get_reminders(cls, user_id: int) -> List[Dict[str, Any]]:
        user_file = cls.get_user_file(user_id)
        if not os.path.exists(user_file):
            await cls.create_empty_reminder_file(user_file)

        async with aiofiles.open(user_file, 'r') as f:
            content = await f.read()
            return sorted(json.loads(content), key=lambda x: x['timestamp']) if content else []

    @classmethod
    async def save_reminders(cls, user_id: int, reminders: List[Dict[str, Any]]) -> None:
        user_file = cls.get_user_file(user_id)
        async with aiofiles.open(user_file, 'w') as f:
            await f.write(json.dumps(reminders, indent=4))

    @staticmethod
    async def create_empty_reminder_file(file_path: str) -> None:
        async with aiofiles.open(file_path, 'w') as f:
            await f.write(json.dumps([]))

    @staticmethod
    def get_user_file(user_id: int) -> str:
        return os.path.join(Reminder.BASE_PATH, f'{user_id}_reminders.json')

async def setup(bot):
    await bot.add_cog(Reminder(bot))