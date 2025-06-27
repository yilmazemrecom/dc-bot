# /home/work/dc-bot/extensions/simple_api.py
from discord.ext import commands
from aiohttp import web
import aiosqlite
import json
import asyncio
from datetime import datetime
import traceback

# Config'den import et
try:
    from config import API_SECRET, API_PORT, API_HOST
except ImportError:
    # Eğer config'de yoksa default değerler
    API_SECRET = 'default-secret-change-this'
    API_PORT = 8080
    API_HOST = '0.0.0.0'

class SimpleAPI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.api_secret = API_SECRET
        self.app = None
        self.runner = None
        
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

    async def cors_and_auth(self, request, handler):
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
            print(f"Auth middleware error: {e}")
            traceback.print_exc()
            return web.json_response({'error': 'Internal server error'}, status=500)

    async def start_api_server(self):
        self.app = web.Application(middlewares=[self.cors_and_auth])
        
        # Routes
        self.app.router.add_get('/api/health', self.health_check)
        self.app.router.add_get('/api/stats', self.get_stats)
        self.app.router.add_get('/api/users', self.get_users)
        self.app.router.add_get('/api/users/search', self.search_users)
        self.app.router.add_put('/api/users/{user_id}/balance', self.update_balance)
        self.app.router.add_get('/api/teams', self.get_teams)
        self.app.router.add_get('/api/servers', self.get_servers)
        self.app.router.add_post('/api/broadcast', self.broadcast_message)
        
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, API_HOST, API_PORT)
        await site.start()

    async def health_check(self, request):
        try:
            return web.json_response({
                'status': 'healthy',
                'bot_online': self.bot.is_ready(),
                'guilds': len(self.bot.guilds),
                'timestamp': datetime.now().isoformat()
            })
        except Exception as e:
            print(f"Health check error: {e}")
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def get_stats(self, request):
        try:
            async with aiosqlite.connect('database/economy.db') as db:
                # Temel istatistikler
                cursor = await db.execute('SELECT COUNT(*) FROM economy')
                total_users = (await cursor.fetchone())[0]
                
                cursor = await db.execute('SELECT SUM(bakiye) FROM economy')
                total_coins = (await cursor.fetchone())[0] or 0
                
                cursor = await db.execute('SELECT username, bakiye FROM economy ORDER BY bakiye DESC LIMIT 1')
                richest = await cursor.fetchone()
                
                cursor = await db.execute('SELECT COUNT(*) FROM sunucular')
                total_servers = (await cursor.fetchone())[0]
                
                cursor = await db.execute('SELECT COUNT(*) FROM takimlar')
                total_teams = (await cursor.fetchone())[0]
                
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
                    'bot_guilds': len(self.bot.guilds),
                    'bot_status': 'online' if self.bot.is_ready() else 'offline'
                })
        except Exception as e:
            print(f"Get stats error: {e}")
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def get_users(self, request):
        try:
            page = int(request.query.get('page', 1))
            limit = min(int(request.query.get('limit', 20)), 100)  # Max 100
            offset = (page - 1) * limit
            
            async with aiosqlite.connect('database/economy.db') as db:
                cursor = await db.execute('SELECT COUNT(*) FROM economy')
                total = (await cursor.fetchone())[0]
                
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
                            'user_id': u[0],
                            'username': u[1],
                            'balance': u[2]
                        } for u in users
                    ],
                    'pagination': {
                        'page': page,
                        'limit': limit,
                        'total': total,
                        'pages': (total + limit - 1) // limit
                    }
                })
        except Exception as e:
            print(f"Get users error: {e}")
            traceback.print_exc()
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
                            'user_id': u[0],
                            'username': u[1], 
                            'balance': u[2]
                        } for u in users
                    ]
                })
        except Exception as e:
            print(f"Search users error: {e}")
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def update_balance(self, request):
        try:
            user_id = request.match_info['user_id']
            data = await request.json()
            new_balance = data.get('balance')
            
            if not isinstance(new_balance, int):
                return web.json_response({'error': 'Invalid balance'}, status=400)
            
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
            traceback.print_exc()
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
                            'user_id': t[0],
                            'team_name': t[1],
                            'captain': t[2],
                            'balance': t[3],
                            'wins': t[4],
                            'losses': t[5],
                            'win_rate': round(t[4] / (t[4] + t[5]) * 100, 1) if (t[4] + t[5]) > 0 else 0
                        } for t in teams
                    ]
                })
        except Exception as e:
            print(f"Get teams error: {e}")
            traceback.print_exc()
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
                            'server_id': s[0],
                            'server_name': s[1],
                            'member_count': s[2]
                        } for s in servers
                    ]
                })
        except Exception as e:
            print(f"Get servers error: {e}")
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

    async def broadcast_message(self, request):
        try:
            data = await request.json()
            message = data.get('message', '').strip()
            target = data.get('target', 'servers')
            
            if not message:
                return web.json_response({'error': 'Message required'}, status=400)
            
            sent_count = 0
            
            if target in ['all', 'servers']:
                for guild in self.bot.guilds:
                    try:
                        # İlk metin kanalını bul
                        channel = None
                        for ch in guild.text_channels:
                            if ch.permissions_for(guild.me).send_messages:
                                channel = ch
                                break
                        
                        if channel:
                            import discord
                            embed = discord.Embed(
                                title="📢 Çaycı Bot Duyurusu",
                                description=message,
                                color=discord.Color.blue(),
                                timestamp=datetime.now()
                            )
                            await channel.send(embed=embed)
                            sent_count += 1
                    except Exception as e:
                        print(f"Broadcast error for guild {guild.id}: {e}")
                        continue
            
            return web.json_response({
                'success': True,
                'sent_count': sent_count,
                'message': f'Duyuru {sent_count} sunucuya gönderildi'
            })
            
        except Exception as e:
            print(f"Broadcast error: {e}")
            traceback.print_exc()
            return web.json_response({'error': str(e)}, status=500)

async def setup(bot):
    await bot.add_cog(SimpleAPI(bot))