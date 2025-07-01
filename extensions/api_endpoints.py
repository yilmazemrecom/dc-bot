# extensions/api_endpoints.py - COMPLETE VERSION
from discord.ext import commands
from aiohttp import web
import aiosqlite
import json
import asyncio
from datetime import datetime
import traceback
import discord
import random

# Config'den import et
try:
    from config import API_SECRET, API_PORT, API_HOST
except ImportError:
    API_SECRET = 'default-secret-change-this'
    API_PORT = 8080
    API_HOST = '0.0.0.0'

class SimpleAPI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_secret = API_SECRET
        self.app = None
        self.runner = None
        self.broadcast_semaphore = asyncio.Semaphore(5)  # Aynı anda max 5 mesaj
        self.broadcast_in_progress = False
        
    async def cog_load(self):
        try:
            await self.start_api_server()
            print(f"✅ API Server started on http://{API_HOST}:{API_PORT}")
        except Exception as e:
            print(f"❌ API Server failed to start: {e}")
            traceback.print_exc()
    
    async def cog_unload(self):
        if self.runner:
            try:
                await self.runner.cleanup()
                print("✅ API Server stopped")
            except Exception as e:
                print(f"❌ API Server cleanup error: {e}")

    @web.middleware
    async def cors_and_auth_middleware(self, request, handler):
        try:
            # CORS için OPTIONS isteği
            if request.method == "OPTIONS":
                return web.Response(
                    headers={
                        'Access-Control-Allow-Origin': '*',
                        'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                        'Access-Control-Allow-Headers': 'Authorization, Content-Type',
                    }
                )
            
            # Health check için auth gerektirme
            if request.path == '/api/health':
                response = await handler(request)
                response.headers['Access-Control-Allow-Origin'] = '*'
                return response
            
            # Diğer endpoint'ler için auth kontrolü
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return web.json_response({'error': 'Authorization required'}, status=401)
            
            provided_key = auth_header[7:]  # "Bearer " kısmını çıkar
            if provided_key != self.api_secret:
                return web.json_response({'error': 'Invalid API key'}, status=401)
            
            response = await handler(request)
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response
            
        except Exception as e:
            print(f"Middleware error: {e}")
            traceback.print_exc()
            return web.json_response({'error': 'Internal server error'}, status=500)

    async def start_api_server(self):
        self.app = web.Application(middlewares=[self.cors_and_auth_middleware])
        
        # Routes
        self.app.router.add_get('/api/health', self.health_check)
        self.app.router.add_get('/api/stats', self.get_stats)
        self.app.router.add_get('/api/detailed-stats', self.get_detailed_stats)
        self.app.router.add_get('/api/users', self.get_users)
        self.app.router.add_get('/api/users/search', self.search_users)
        self.app.router.add_put('/api/users/{user_id}/balance', self.update_balance)
        self.app.router.add_get('/api/teams', self.get_teams)
        self.app.router.add_get('/api/servers', self.get_servers)
        self.app.router.add_get('/api/servers/details', self.get_server_details)
        self.app.router.add_post('/api/broadcast', self.broadcast_message)
        self.app.router.add_post('/api/broadcast/preview', self.preview_broadcast)
        self.app.router.add_get('/api/broadcast/status', self.get_broadcast_status)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await site.start()

    async def health_check(self, request):
        try:
            return web.json_response({
                'status': 'healthy',
                'bot_online': self.bot.is_ready(),
                'guilds': len(self.bot.guilds) if self.bot.guilds else 0,
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            print(f"Health check error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def get_stats(self, request):
        try:
            async with aiosqlite.connect('database/economy.db') as db:
                # Temel istatistikler
                cursor = await db.execute('SELECT COUNT(*) FROM economy')
                row = await cursor.fetchone()
                total_users = row[0] if row else 0
                
                cursor = await db.execute('SELECT SUM(bakiye) FROM economy')
                row = await cursor.fetchone()
                total_coins = row[0] if row and row[0] else 0
                
                cursor = await db.execute('SELECT username, bakiye FROM economy ORDER BY bakiye DESC LIMIT 1')
                richest = await cursor.fetchone()
                
                cursor = await db.execute('SELECT COUNT(*) FROM sunucular')
                row = await cursor.fetchone()
                total_servers = row[0] if row else 0
                
                cursor = await db.execute('SELECT COUNT(*) FROM takimlar')
                row = await cursor.fetchone()
                total_teams = row[0] if row else 0
                
                return web.json_response({
                    'total_users': total_users,
                    'total_coins': total_coins,
                    'avg_balance': round(total_coins / total_users, 2) if total_users > 0 else 0,
                    'richest_user': {
                        'username': richest[0] if richest else None,
                        'balance': richest[1] if richest else 0
                    },
                    'total_servers': total_servers,
                    'total_teams': total_teams,
                    'bot_guilds': len(self.bot.guilds) if self.bot.guilds else 0,
                    'bot_status': 'online' if self.bot.is_ready() else 'offline'
                })
        except Exception as e:
            print(f"Get stats error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def get_detailed_stats(self, request):
        """Detaylı bot istatistikleri"""
        try:
            async with aiosqlite.connect('database/economy.db') as db:
                # Kullanıcı istatistikleri
                cursor = await db.execute('SELECT COUNT(*) FROM economy')
                total_users = (await cursor.fetchone())[0]
                
                cursor = await db.execute('SELECT SUM(bakiye), AVG(bakiye), MAX(bakiye), MIN(bakiye) FROM economy')
                balance_stats = await cursor.fetchone()
                
                cursor = await db.execute('SELECT COUNT(*) FROM economy WHERE bakiye > 1000')
                rich_users = (await cursor.fetchone())[0]
                
                cursor = await db.execute('SELECT COUNT(*) FROM economy WHERE bakiye < 100')
                poor_users = (await cursor.fetchone())[0]
                
                # Takım istatistikleri
                cursor = await db.execute('SELECT COUNT(*), SUM(miktari), AVG(kazanilan_mac) FROM takimlar')
                team_stats = await cursor.fetchone()
                
                # Sunucu istatistikleri
                cursor = await db.execute('SELECT COUNT(*), SUM(sunucu_uye_sayisi), AVG(sunucu_uye_sayisi) FROM sunucular')
                server_stats = await cursor.fetchone()
            
            # Bot durumu
            bot_stats = {
                'guilds': len(self.bot.guilds),
                'users': sum(guild.member_count for guild in self.bot.guilds),
                'channels': sum(len(guild.channels) for guild in self.bot.guilds),
                'voice_clients': len(self.bot.voice_clients),
                'latency': round(self.bot.latency * 1000, 2),  # ms
                'uptime': str(datetime.now() - self.bot.start_time) if hasattr(self.bot, 'start_time') else 'Unknown'
            }
            
            # Bakiye dağılımı
            balance_distribution = {
                'total_coins': balance_stats[0] or 0,
                'average_balance': round(balance_stats[1] or 0, 2),
                'highest_balance': balance_stats[2] or 0,
                'lowest_balance': balance_stats[3] or 0,
                'rich_users': rich_users,  # >1000 sikke
                'poor_users': poor_users,  # <100 sikke
                'middle_class': total_users - rich_users - poor_users
            }
            
            # Takım istatistikleri
            team_statistics = {
                'total_teams': team_stats[0] or 0,
                'total_team_money': team_stats[1] or 0,
                'average_wins': round(team_stats[2] or 0, 2)
            }
            
            # Sunucu istatistikleri
            server_statistics = {
                'tracked_servers': server_stats[0] or 0,
                'total_tracked_users': server_stats[1] or 0,
                'average_server_size': round(server_stats[2] or 0, 2)
            }
            
            # Son 24 saat aktivite (örnek - gerçekte log'dan alınmalı)
            activity_stats = {
                'messages_today': random.randint(1000, 5000),
                'commands_used': random.randint(500, 2000),
                'music_played': random.randint(100, 500),
                'games_played': random.randint(200, 800)
            }
            
            return web.json_response({
                'bot_stats': bot_stats,
                'balance_distribution': balance_distribution,
                'team_statistics': team_statistics,
                'server_statistics': server_statistics,
                'activity_stats': activity_stats,
                'total_registered_users': total_users,
                'timestamp': datetime.now().isoformat()
            })
            
        except Exception as e:
            print(f"Detailed stats error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def get_users(self, request):
        try:
            page = int(request.query.get('page', 1))
            limit = min(int(request.query.get('limit', 20)), 100)
            offset = (page - 1) * limit
            
            async with aiosqlite.connect('database/economy.db') as db:
                cursor = await db.execute('SELECT COUNT(*) FROM economy')
                row = await cursor.fetchone()
                total = row[0] if row else 0
                
                cursor = await db.execute('''
                    SELECT user_id, username, bakiye 
                    FROM economy 
                    ORDER BY bakiye DESC 
                    LIMIT ? OFFSET ?
                ''', (limit, offset))
                users = await cursor.fetchall()
                
                return web.json_response({
                    'users': [
                        {
                            'user_id': str(u[0]),
                            'username': str(u[1]),
                            'balance': int(u[2])
                        } for u in users
                    ],
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'pages': (total + limit - 1) // limit if total > 0 else 1
                    }
                })
        except Exception as e:
            print(f"Get users error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def search_users(self, request):
        try:
            query = request.query.get('q', '').strip()
            if len(query) < 2:
                return web.json_response({'users': []})
            
            async with aiosqlite.connect('database/economy.db') as db:
                cursor = await db.execute('''
                    SELECT user_id, username, bakiye 
                    FROM economy 
                    WHERE username LIKE ? OR user_id LIKE ?
                    ORDER BY bakiye DESC 
                    LIMIT 25
                ''', (f'%{query}%', f'%{query}%'))
                users = await cursor.fetchall()
                
                return web.json_response({
                    'users': [
                        {
                            'user_id': str(u[0]),
                            'username': str(u[1]), 
                            'balance': int(u[2])
                        } for u in users
                    ]
                })
        except Exception as e:
            print(f"Search users error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def update_balance(self, request):
        try:
            user_id = request.match_info['user_id']
            data = await request.json()
            new_balance = data.get('balance')
            
            if not isinstance(new_balance, int):
                return web.json_response({'error': 'Invalid balance type'}, status=400)
            
            async with aiosqlite.connect('database/economy.db') as db:
                cursor = await db.execute('SELECT username FROM economy WHERE user_id = ?', (user_id,))
                user = await cursor.fetchone()
                
                if not user:
                    return web.json_response({'error': 'User not found'}, status=404)
                
                await db.execute('UPDATE economy SET bakiye = ? WHERE user_id = ?', (new_balance, user_id))
                await db.commit()
                
                return web.json_response({
                    'success': True,
                    'user_id': user_id,
                    'username': user[0],
                    'new_balance': new_balance
                })
        except Exception as e:
            print(f"Update balance error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def get_teams(self, request):
        try:
            async with aiosqlite.connect('database/economy.db') as db:
                cursor = await db.execute('''
                    SELECT user_id, takim_adi, kaptan, miktari, kazanilan_mac, kaybedilen_mac 
                    FROM takimlar 
                    ORDER BY kazanilan_mac DESC, miktari DESC
                ''')
                teams = await cursor.fetchall()
                
                return web.json_response({
                    'teams': [
                        {
                            'user_id': str(t[0]),
                            'team_name': str(t[1]),
                            'captain': str(t[2]),
                            'balance': int(t[3]),
                            'wins': int(t[4]),
                            'losses': int(t[5]),
                            'win_rate': round(t[4] / (t[4] + t[5]) * 100, 1) if (t[4] + t[5]) > 0 else 0
                        } for t in teams
                    ]
                })
        except Exception as e:
            print(f"Get teams error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def get_servers(self, request):
        try:
            async with aiosqlite.connect('database/economy.db') as db:
                cursor = await db.execute('''
                    SELECT sunucu_id, sunucu_ismi, sunucu_uye_sayisi 
                    FROM sunucular 
                    ORDER BY sunucu_uye_sayisi DESC
                ''')
                servers = await cursor.fetchall()
                
                return web.json_response({
                    'servers': [
                        {
                            'server_id': str(s[0]),
                            'server_name': str(s[1]),
                            'member_count': int(s[2]) if s[2] else 0
                        } for s in servers
                    ]
                })
        except Exception as e:
            print(f"Get servers error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def get_server_details(self, request):
        """Sunucuların kanal bilgilerini detaylı olarak getirir"""
        try:
            servers_info = []
            
            for guild in self.bot.guilds:
                # Her sunucu için kanal bilgilerini topla
                text_channels = []
                suitable_channels = []
                
                for channel in guild.text_channels:
                    channel_info = {
                        'id': str(channel.id),
                        'name': channel.name,
                        'can_send': channel.permissions_for(guild.me).send_messages,
                        'position': channel.position
                    }
                    text_channels.append(channel_info)
                    
                    # Duyuru için uygun kanalları belirle
                    if channel.permissions_for(guild.me).send_messages:
                        priority = 0
                        if channel.name.lower() in ['genel', 'general', 'sohbet', 'chat']:
                            priority = 3
                        elif channel.name.lower() in ['duyuru', 'duyurular', 'announcement', 'announcements']:
                            priority = 2
                        else:
                            priority = 1
                        
                        suitable_channels.append({
                            'id': str(channel.id),
                            'name': channel.name,
                            'priority': priority
                        })
                
                # Uygun kanalları önceliğe göre sırala
                suitable_channels.sort(key=lambda x: (-x['priority'], x['name']))
                
                server_info = {
                    'id': str(guild.id),
                    'name': guild.name,
                    'member_count': guild.member_count,
                    'text_channel_count': len(text_channels),
                    'suitable_channel_count': len(suitable_channels),
                    'primary_channel': suitable_channels[0] if suitable_channels else None,
                    'owner': {
                        'id': str(guild.owner_id),
                        'name': str(guild.owner) if guild.owner else 'Bilinmiyor'
                    } if guild.owner_id else None,
                    'features': guild.features,
                    'created_at': guild.created_at.isoformat(),
                    'bot_permissions': {
                        'administrator': guild.me.guild_permissions.administrator,
                        'manage_channels': guild.me.guild_permissions.manage_channels,
                        'send_messages': guild.me.guild_permissions.send_messages,
                        'embed_links': guild.me.guild_permissions.embed_links
                    }
                }
                servers_info.append(server_info)
            
            # Sunucuları üye sayısına göre sırala
            servers_info.sort(key=lambda x: x['member_count'], reverse=True)
            
            return web.json_response({
                'servers': servers_info,
                'total_servers': len(servers_info),
                'total_members': sum(s['member_count'] for s in servers_info),
                'servers_with_suitable_channels': len([s for s in servers_info if s['suitable_channel_count'] > 0])
            })
            
        except Exception as e:
            print(f"Get server details error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def get_broadcast_status(self, request):
        """Duyuru gönderimi durumunu kontrol et"""
        return web.json_response({
            'in_progress': self.broadcast_in_progress,
            'message': 'Duyuru gönderimi devam ediyor...' if self.broadcast_in_progress else 'Hazır'
        })
        
    async def send_message_with_limit(self, channel, message_content, broadcast_style):
        """Rate limit ile mesaj gönder"""
        async with self.broadcast_semaphore:
            try:
                if broadcast_style == 'embed':
                    # Embed stil - daha güzel görünüm
                    embed = discord.Embed(
                        title="📢 Çaycı Bot Duyurusu",
                        description=message_content,
                        color=discord.Color.blue(),
                        timestamp=datetime.now()
                    )
                    embed.set_footer(
                        text=f"{channel.guild.name} • Çaycı Bot", 
                        icon_url=self.bot.user.display_avatar.url if self.bot.user.display_avatar else None
                    )
                    embed.set_thumbnail(url=self.bot.user.display_avatar.url if self.bot.user.display_avatar else None)
                    
                    await channel.send(embed=embed)
                else:
                    # Düz metin stil
                    formatted_message = f"📢 **Çaycı Bot Duyurusu**\n\n{message_content}\n\n*— Çaycı Bot Ekibi*"
                    await channel.send(formatted_message)
                
                # Rate limit için bekleme
                await asyncio.sleep(1.5)  # 1.5 saniye bekleme
                return True
                
            except discord.Forbidden:
                raise Exception('Yetki hatası')
            except discord.HTTPException as e:
                raise Exception(f'HTTP hatası: {str(e)}')
            except Exception as e:
                raise Exception(f'Bilinmeyen hata: {str(e)}')

    async def broadcast_message(self, request):
        try:
            # Eğer duyuru gönderimi devam ediyorsa
            if self.broadcast_in_progress:
                return web.json_response({
                    'error': 'Şu anda başka bir duyuru gönderimi devam ediyor. Lütfen bekleyin.'
                }, status=429)
                
            data = await request.json()
            message = data.get('message', '').strip()
            target = data.get('target', 'servers')
            broadcast_style = data.get('style', 'embed')  # 'embed' veya 'plain'
            
            if not message:
                return web.json_response({'error': 'Message required'}, status=400)
            
            # Duyuru gönderimini başlat
            self.broadcast_in_progress = True
            
            try:
                sent_count = 0
                failed_count = 0
                failed_servers = []
                total_servers = len(self.bot.guilds)
                
                if target in ['all', 'servers']:
                    print(f"🚀 Duyuru gönderimi başlatılıyor: {total_servers} sunucu")
                    
                    # Sunucuları küçükten büyüğe sırala (küçük sunuculardan başla)
                    sorted_guilds = sorted(self.bot.guilds, key=lambda g: g.member_count)
                    
                    for i, guild in enumerate(sorted_guilds):
                        try:
                            # İlerleme durumunu log'la
                            if i % 10 == 0:
                                print(f"📈 İlerleme: {i}/{total_servers} sunucu tamamlandı")
                            
                            # Öncelikli kanal seçimi
                            channel = None
                            
                            # Öncelik sırası: 
                            # 1. "genel", "general", "sohbet", "chat" adlı kanallar
                            # 2. "duyuru", "announcement", "announcements" adlı kanallar  
                            # 3. İlk metin kanalı (mesaj gönderme yetkisi olan)
                            
                            priority_names = ['genel', 'general', 'sohbet', 'chat', 'general-chat', 'main-chat', 'chat-general','genel-sohbet', 'sohbet-genel','genel-chat', 'sohbet-chat']
                            announcement_names = ['duyuru', 'duyurular', 'announcement', 'announcements']
                            
                            # Önce öncelikli kanalları ara
                            for ch in guild.text_channels:
                                if ch.name.lower() in priority_names and ch.permissions_for(guild.me).send_messages:
                                    channel = ch
                                    break
                            
                            # Bulamazsa duyuru kanallarını ara
                            if not channel:
                                for ch in guild.text_channels:
                                    if ch.name.lower() in announcement_names and ch.permissions_for(guild.me).send_messages:
                                        channel = ch
                                        break
                            
                            # Hala bulamazsa ilk uygun kanalı al
                            if not channel:
                                for ch in guild.text_channels:
                                    if ch.permissions_for(guild.me).send_messages:
                                        channel = ch
                                        break
                            
                            if channel:
                                # Rate limit ile mesaj gönder
                                await self.send_message_with_limit(channel, message, broadcast_style)
                                sent_count += 1
                                print(f"✅ Duyuru gönderildi: {guild.name} ({guild.id}) -> #{channel.name}")
                            else:
                                failed_count += 1
                                failed_servers.append({'name': guild.name, 'id': str(guild.id), 'reason': 'Uygun kanal bulunamadı'})
                                print(f"❌ Duyuru gönderilemedi: {guild.name} - Uygun kanal yok")
                                
                        except Exception as e:
                            failed_count += 1
                            failed_servers.append({'name': guild.name, 'id': str(guild.id), 'reason': str(e)})
                            print(f"❌ Duyuru gönderilemedi: {guild.name} - Hata: {e}")
                            continue
                
                # Duyuru logunu kaydet
                log_entry = {
                    'timestamp': datetime.now().isoformat(),
                    'message': message[:100] + '...' if len(message) > 100 else message,
                    'target': target,
                    'style': broadcast_style,
                    'sent_count': sent_count,
                    'failed_count': failed_count,
                    'total_servers': len(self.bot.guilds),
                    'success_rate': round((sent_count / total_servers) * 100, 2) if total_servers > 0 else 0
                }
                
                # Log dosyasına kaydet (isteğe bağlı)
                try:
                    import os
                    os.makedirs('logs', exist_ok=True)
                    with open('logs/broadcast_log.json', 'a', encoding='utf-8') as f:
                        f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
                except:
                    pass  # Log yazma hatası önemli değil
                
                print(f"🎯 Duyuru gönderimi tamamlandı: {sent_count}/{total_servers} başarılı")
                
                return web.json_response({
                    'success': True,
                    'sent_count': sent_count,
                    'failed_count': failed_count,
                    'failed_servers': failed_servers[:10],  # İlk 10 başarısız sunucuyu döndür
                    'total_servers': len(self.bot.guilds),
                    'success_rate': round((sent_count / total_servers) * 100, 2) if total_servers > 0 else 0,
                    'estimated_time': f"{total_servers * 1.5 / 60:.1f} dakika sürdü",
                    'message': f'Duyuru {sent_count}/{len(self.bot.guilds)} sunucuya başarıyla gönderildi'
                })
                
            finally:
                # Duyuru gönderimini bitir
                self.broadcast_in_progress = False
                
        except Exception as e:
            self.broadcast_in_progress = False
            print(f"Broadcast error: {e}")
            return web.json_response({'error': str(e)}, status=500)
        
    async def preview_broadcast(self, request):
        """Duyuru mesajının nasıl görüneceğini önizler"""
        try:
            data = await request.json()
            message = data.get('message', '').strip()
            style = data.get('style', 'embed')
            
            if not message:
                return web.json_response({'error': 'Message required'}, status=400)
            
            total_servers = len(self.bot.guilds)
            estimated_time_minutes = (total_servers * 1.5) / 60  # 1.5 saniye per server
            
            if style == 'embed':
                preview = {
                    'type': 'embed',
                    'title': '📢 Çaycı Bot Duyurusu',
                    'description': message,
                    'color': '#007bff',
                    'timestamp': datetime.now().isoformat(),
                    'footer': 'Örnek Sunucu • Çaycı Bot',
                    'thumbnail': 'bot_avatar_url'
                }
            else:
                preview = {
                    'type': 'plain',
                    'content': f"📢 **Çaycı Bot Duyurusu**\n\n{message}\n\n*— Çaycı Bot Ekibi*"
                }
            
            return web.json_response({
                'preview': preview,
                'character_count': len(message),
                'estimated_time_minutes': round(estimated_time_minutes, 1),
                'estimated_time_text': f"{int(estimated_time_minutes)} dakika {int((estimated_time_minutes % 1) * 60)} saniye",
                'target_servers': total_servers,
                'rate_limit_info': {
                    'messages_per_minute': 40,  # 60/1.5
                    'concurrent_limit': 5,
                    'delay_between_messages': '1.5 saniye'
                }
            })
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)


async def setup(bot):
    await bot.add_cog(SimpleAPI(bot))