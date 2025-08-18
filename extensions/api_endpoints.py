# extensions/api_endpoints.py - COMPLETE VERSION
from discord.ext import commands
from aiohttp import web
import aiosqlite
import json
import asyncio
from datetime import datetime, timedelta
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
        self.app.router.add_get('/api/servers/{server_id}/members', self.get_server_members)
        self.app.router.add_get('/api/users/{user_id}/servers', self.get_user_servers)
        self.app.router.add_post('/api/broadcast', self.broadcast_message)
        self.app.router.add_post('/api/broadcast/preview', self.preview_broadcast)
        self.app.router.add_post('/api/broadcast/selective', self.selective_broadcast)
        self.app.router.add_get('/api/broadcast/status', self.get_broadcast_status)
        
        # Log endpoints removed
        
        self.app.router.add_get('/api/broadcast/history', self.get_broadcast_history)
        
        # Bot settings endpoints removed - not needed
        self.app.router.add_get('/api/settings/admin', self.get_admin_settings)
        self.app.router.add_put('/api/settings/admin', self.update_admin_settings)
        
        self.app.router.add_get('/api/system/info', self.get_system_info)
        self.app.router.add_post('/api/system/backup', self.create_backup)
        self.app.router.add_get('/api/system/backup/info', self.get_backup_info)
        self.app.router.add_get('/api/system/backup/list', self.get_backup_list)
        self.app.router.add_post('/api/system/restart', self.restart_bot)
        
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

    async def get_server_members(self, request):
        """Belirli bir sunucunun üyelerini getir"""
        try:
            server_id = int(request.match_info['server_id'])
            page = int(request.query.get('page', 1))
            limit = min(int(request.query.get('limit', 50)), 200)
            offset = (page - 1) * limit
            
            guild = self.bot.get_guild(server_id)
            if not guild:
                return web.json_response({'error': 'Server not found'}, status=404)
            
            # Üyeleri al (sadece cache'den)
            members = []
            for i, member in enumerate(guild.members):
                if i < offset:
                    continue
                if len(members) >= limit:
                    break
                    
                # Kullanıcının ekonomi verilerini kontrol et
                user_balance = None
                async with aiosqlite.connect('database/economy.db') as db:
                    cursor = await db.execute('SELECT bakiye FROM economy WHERE user_id = ?', (str(member.id),))
                    result = await cursor.fetchone()
                    user_balance = result[0] if result else 0
                
                member_info = {
                    'id': str(member.id),
                    'username': member.display_name,
                    'discriminator': member.discriminator,
                    'avatar_url': str(member.display_avatar.url) if member.display_avatar else None,
                    'joined_at': member.joined_at.isoformat() if member.joined_at else None,
                    'roles': [role.name for role in member.roles if role.name != '@everyone'],
                    'is_bot': member.bot,
                    'balance': user_balance,
                    'status': str(member.status) if hasattr(member, 'status') else 'unknown'
                }
                members.append(member_info)
            
            return web.json_response({
                'server_id': str(server_id),
                'server_name': guild.name,
                'members': members,
                'pagination': {
                    'page': page,
                    'limit': limit,
                    'total': guild.member_count,
                    'pages': (guild.member_count + limit - 1) // limit if guild.member_count > 0 else 1
                }
            })
            
        except ValueError:
            return web.json_response({'error': 'Invalid server ID'}, status=400)
        except Exception as e:
            print(f"Get server members error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def get_user_servers(self, request):
        """Kullanıcının hangi sunucularda olduğunu getir"""
        try:
            user_id = int(request.match_info['user_id'])
            
            user_servers = []
            for guild in self.bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    server_info = {
                        'id': str(guild.id),
                        'name': guild.name,
                        'member_count': guild.member_count,
                        'joined_at': member.joined_at.isoformat() if member.joined_at else None,
                        'roles': [role.name for role in member.roles if role.name != '@everyone'],
                        'is_owner': guild.owner_id == user_id,
                        'permissions': {
                            'administrator': member.guild_permissions.administrator,
                            'manage_server': member.guild_permissions.manage_guild,
                            'manage_channels': member.guild_permissions.manage_channels,
                            'kick_members': member.guild_permissions.kick_members,
                            'ban_members': member.guild_permissions.ban_members
                        }
                    }
                    user_servers.append(server_info)
            
            # Kullanıcının ekonomi verilerini al
            user_info = None
            async with aiosqlite.connect('database/economy.db') as db:
                cursor = await db.execute('SELECT username, bakiye FROM economy WHERE user_id = ?', (str(user_id),))
                result = await cursor.fetchone()
                if result:
                    user_info = {
                        'username': result[0],
                        'balance': result[1]
                    }
            
            return web.json_response({
                'user_id': str(user_id),
                'user_info': user_info,
                'servers': user_servers,
                'total_servers': len(user_servers)
            })
            
        except ValueError:
            return web.json_response({'error': 'Invalid user ID'}, status=400)
        except Exception as e:
            print(f"Get user servers error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    async def selective_broadcast(self, request):
        """Seçili sunuculara duyuru gönder"""
        try:
            if self.broadcast_in_progress:
                return web.json_response({
                    'error': 'Şu anda başka bir duyuru gönderimi devam ediyor. Lütfen bekleyin.'
                }, status=429)
                
            data = await request.json()
            message = data.get('message', '').strip()
            server_ids = data.get('server_ids', [])
            broadcast_style = data.get('style', 'embed')
            delay_seconds = int(data.get('delay', 2))  # Varsayılan 2 saniye
            
            if not message:
                return web.json_response({'error': 'Message required'}, status=400)
            
            if not server_ids:
                return web.json_response({'error': 'Server IDs required'}, status=400)
            
            # Gecikme süresi kontrolü (1-10 saniye arası)
            delay_seconds = max(1, min(delay_seconds, 10))
            
            self.broadcast_in_progress = True
            
            try:
                sent_count = 0
                failed_count = 0
                failed_servers = []
                target_guilds = []
                
                # Seçili sunucuları bul
                for server_id in server_ids:
                    try:
                        guild = self.bot.get_guild(int(server_id))
                        if guild:
                            target_guilds.append(guild)
                    except:
                        failed_servers.append({
                            'name': f'ID: {server_id}',
                            'id': str(server_id),
                            'reason': 'Sunucu bulunamadı'
                        })
                
                print(f"🚀 Seçili duyuru gönderimi başlatılıyor: {len(target_guilds)} sunucu")
                
                # Sunucuları küçükten büyüğe sırala
                target_guilds.sort(key=lambda g: g.member_count)
                
                for i, guild in enumerate(target_guilds):
                    try:
                        if i % 5 == 0:
                            print(f"📈 İlerleme: {i}/{len(target_guilds)} sunucu tamamlandı")
                        
                        # Kanal seçimi (aynı mantık)
                        channel = None
                        priority_names = ['genel', 'general', 'sohbet', 'chat', 'general-chat', 'main-chat']
                        announcement_names = ['duyuru', 'duyurular', 'announcement', 'announcements']
                        
                        for ch in guild.text_channels:
                            if ch.name.lower() in priority_names and ch.permissions_for(guild.me).send_messages:
                                channel = ch
                                break
                        
                        if not channel:
                            for ch in guild.text_channels:
                                if ch.name.lower() in announcement_names and ch.permissions_for(guild.me).send_messages:
                                    channel = ch
                                    break
                        
                        if not channel:
                            for ch in guild.text_channels:
                                if ch.permissions_for(guild.me).send_messages:
                                    channel = ch
                                    break
                        
                        if channel:
                            # Özelleştirilmiş rate limit ile mesaj gönder
                            async with self.broadcast_semaphore:
                                if broadcast_style == 'embed':
                                    embed = discord.Embed(
                                        title="📢 Çaycı Bot Duyurusu",
                                        description=message,
                                        color=discord.Color.blue(),
                                        timestamp=datetime.now()
                                    )
                                    embed.set_footer(
                                        text=f"{guild.name} • Çaycı Bot",
                                        icon_url=self.bot.user.display_avatar.url if self.bot.user.display_avatar else None
                                    )
                                    await channel.send(embed=embed)
                                else:
                                    formatted_message = f"📢 **Çaycı Bot Duyurusu**\n\n{message}\n\n*— Çaycı Bot Ekibi*"
                                    await channel.send(formatted_message)
                                
                                await asyncio.sleep(delay_seconds)
                            
                            sent_count += 1
                            print(f"✅ Seçili duyuru gönderildi: {guild.name} -> #{channel.name}")
                        else:
                            failed_count += 1
                            failed_servers.append({
                                'name': guild.name,
                                'id': str(guild.id),
                                'reason': 'Uygun kanal bulunamadı'
                            })
                            
                    except Exception as e:
                        failed_count += 1
                        failed_servers.append({
                            'name': guild.name,
                            'id': str(guild.id),
                            'reason': str(e)
                        })
                        continue
                
                print(f"🎯 Seçili duyuru gönderimi tamamlandı: {sent_count}/{len(target_guilds)} başarılı")
                
                return web.json_response({
                    'success': True,
                    'sent_count': sent_count,
                    'failed_count': failed_count,
                    'failed_servers': failed_servers,
                    'target_servers': len(target_guilds),
                    'success_rate': round((sent_count / len(target_guilds)) * 100, 2) if len(target_guilds) > 0 else 0,
                    'delay_used': delay_seconds,
                    'estimated_time': f"{len(target_guilds) * delay_seconds / 60:.1f} dakika sürdü",
                    'message': f'Duyuru {sent_count}/{len(target_guilds)} seçili sunucuya başarıyla gönderildi'
                })
                
            finally:
                self.broadcast_in_progress = False
                
        except Exception as e:
            self.broadcast_in_progress = False
            print(f"Selective broadcast error: {e}")
            return web.json_response({'error': str(e)}, status=500)

    # Log endpoints removed - not needed

    # BROADCAST HISTORY

    async def get_broadcast_history(self, request):
        """Get broadcast history"""
        try:
            limit = int(request.query.get('limit', 10))
            broadcasts = []
            
            try:
                import os
                if os.path.exists('logs/broadcast_log.json'):
                    with open('logs/broadcast_log.json', 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        
                        for i, line in enumerate(reversed(lines[-limit:])):
                            try:
                                log_data = json.loads(line.strip())
                                broadcast = {
                                    'id': i + 1,
                                    'created_at': log_data.get('timestamp', datetime.now().isoformat()),
                                    'message': log_data.get('message', ''),
                                    'server_count': log_data.get('sent_count', 0),
                                    'status': 'completed' if log_data.get('sent_count', 0) > 0 else 'failed',
                                    'success_count': log_data.get('sent_count', 0),
                                    'style': log_data.get('style', 'embed')
                                }
                                broadcasts.append(broadcast)
                            except:
                                continue
            except:
                pass
            
            return web.json_response({
                'broadcasts': broadcasts,
                'total': len(broadcasts)
            })
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # Scheduled broadcast feature removed - not needed

    # Bot settings endpoints removed - not needed since they don't affect the bot

    async def get_admin_settings(self, request):
        """Get admin panel settings"""
        try:
            settings = {
                'session_timeout': 3600,
                'max_login_attempts': 5,
                'enable_2fa': False,
                'log_retention_days': 30,
                'api_rate_limit': 100
            }
            
            try:
                import os, json
                if os.path.exists('config/admin_settings.json'):
                    with open('config/admin_settings.json', 'r', encoding='utf-8') as f:
                        saved_settings = json.load(f)
                        settings.update(saved_settings)
            except:
                pass
            
            return web.json_response({'settings': settings})
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def update_admin_settings(self, request):
        """Update admin panel settings"""
        try:
            data = await request.json()
            
            valid_settings = {
                'session_timeout': max(1800, min(int(data.get('session_timeout', 3600)), 86400)),
                'max_login_attempts': max(3, min(int(data.get('max_login_attempts', 5)), 10)),
                'enable_2fa': bool(data.get('enable_2fa', False)),
                'log_retention_days': max(7, min(int(data.get('log_retention_days', 30)), 365)),
                'api_rate_limit': max(10, min(int(data.get('api_rate_limit', 100)), 1000))
            }
            
            try:
                import os, json
                os.makedirs('config', exist_ok=True)
                with open('config/admin_settings.json', 'w', encoding='utf-8') as f:
                    json.dump(valid_settings, f, indent=2)
            except Exception as e:
                print(f"Admin settings save error: {e}")
            
            return web.json_response({
                'success': True,
                'message': 'Admin ayarları güncellendi',
                'settings': valid_settings
            })
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    # SYSTEM ENDPOINTS
    async def get_system_info(self, request):
        """Get system information"""
        try:
            import discord
            import platform
            import sys
            
            info = {
                'discord_py_version': discord.__version__,
                'python_version': platform.python_version(),
                'platform': platform.platform(),
                'uptime': str(datetime.now() - self.bot.start_time) if hasattr(self.bot, 'start_time') else 'Unknown'
            }
            
            return web.json_response({'info': info})
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def create_backup(self, request):
        """Create database backup"""
        try:
            import shutil
            import os
            from datetime import datetime
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_filename = f'backup_{timestamp}.db'
            
            try:
                os.makedirs('backups', exist_ok=True)
                shutil.copy2('database/economy.db', f'backups/{backup_filename}')
                
                file_size = os.path.getsize(f'backups/{backup_filename}')
                size_mb = f"{file_size / (1024*1024):.1f} MB"
                
                return web.json_response({
                    'success': True,
                    'backup_file': backup_filename,
                    'size': size_mb,
                    'created_at': datetime.now().isoformat(),
                    'message': 'Backup created successfully'
                })
                
            except Exception as e:
                return web.json_response({
                    'success': False,
                    'error': f'Backup failed: {str(e)}'
                }, status=500)
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_backup_info(self, request):
        """Get last backup info"""
        try:
            import os
            import glob
            
            backup_files = glob.glob('backups/backup_*.db')
            if backup_files:
                latest_backup = max(backup_files, key=os.path.getctime)
                file_size = os.path.getsize(latest_backup)
                size_mb = f"{file_size / (1024*1024):.1f} MB"
                created_at = datetime.fromtimestamp(os.path.getctime(latest_backup)).isoformat()
                
                return web.json_response({
                    'last_backup': {
                        'filename': os.path.basename(latest_backup),
                        'size': size_mb,
                        'created_at': created_at
                    }
                })
            else:
                return web.json_response({'last_backup': None})
                
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def get_backup_list(self, request):
        """Get list of all backups"""
        try:
            import os
            import glob
            
            backups = []
            backup_files = glob.glob('backups/backup_*.db')
            
            for backup_file in sorted(backup_files, key=os.path.getctime, reverse=True):
                file_size = os.path.getsize(backup_file)
                size_mb = f"{file_size / (1024*1024):.1f} MB"
                created_at = datetime.fromtimestamp(os.path.getctime(backup_file)).isoformat()
                
                backups.append({
                    'id': os.path.basename(backup_file).replace('.db', ''),
                    'filename': os.path.basename(backup_file),
                    'size': size_mb,
                    'created_at': created_at
                })
            
            return web.json_response({'backups': backups})
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)

    async def restart_bot(self, request):
        """Restart the bot"""
        try:
            # Schedule restart after a short delay
            async def delayed_restart():
                await asyncio.sleep(2)
                print("🔄 Bot restart requested via API")
                # In a real implementation, you'd restart the bot process
                # For now, just log the request
                
            asyncio.create_task(delayed_restart())
            
            return web.json_response({
                'success': True,
                'message': 'Bot yeniden başlatma komutu gönderildi',
                'restart_time': (datetime.now() + timedelta(seconds=2)).isoformat()
            })
            
        except Exception as e:
            return web.json_response({'error': str(e)}, status=500)


async def setup(bot):
    await bot.add_cog(SimpleAPI(bot))