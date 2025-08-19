#!/usr/bin/env python3
import asyncio
import os
import subprocess
import sys
import platform

class BotOptimizer:
    def __init__(self):
        self.system_info = {}
        self.recommendations = []
    
    async def analyze_system(self):
        """Sistem performansını analiz et"""
        print("🔍 Sistem analizi başlatılıyor...")
        
        # CPU ve RAM bilgilerini al
        if platform.system() == "Linux":
            try:
                # CPU bilgisi
                with open('/proc/cpuinfo', 'r') as f:
                    cpu_info = f.read()
                    cpu_count = cpu_info.count('processor')
                    self.system_info['cpu_cores'] = cpu_count
                
                # RAM bilgisi
                with open('/proc/meminfo', 'r') as f:
                    mem_info = f.read()
                    for line in mem_info.split('\n'):
                        if 'MemTotal:' in line:
                            total_mem = int(line.split()[1]) // 1024  # MB cinsinden
                            self.system_info['total_ram'] = total_mem
                            break
                
                # Network latency test
                latency = await self.test_discord_latency()
                self.system_info['discord_latency'] = latency
                
                print(f"✅ CPU Çekirdekleri: {cpu_count}")
                print(f"✅ Toplam RAM: {total_mem} MB")
                print(f"✅ Discord Latency: {latency}ms")
                
            except Exception as e:
                print(f"❌ Sistem bilgisi alınamadı: {e}")
    
    async def test_discord_latency(self):
        """Discord gateway latency testi"""
        import aiohttp
        import time
        
        try:
            async with aiohttp.ClientSession() as session:
                start_time = time.perf_counter()
                async with session.get('https://discord.com/api/v10/gateway') as response:
                    await response.json()
                end_time = time.perf_counter()
                return round((end_time - start_time) * 1000, 2)
        except:
            return 0
    
    def generate_systemd_config(self):
        """Optimize edilmiş systemd servisi oluştur"""
        cpu_cores = self.system_info.get('cpu_cores', 1)
        
        config = f"""[Unit]
Description=Discord Bot - Çaycı Bot
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=work
WorkingDirectory=/home/work/dc-bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
RestartSec=5
KillMode=mixed
KillSignal=SIGINT
TimeoutStopSec=30

# Performance optimizations
CPUAffinity=0-{cpu_cores-1}
IOSchedulingClass=1
IOSchedulingPriority=4
Nice=-10
OOMScoreAdjust=-900

# Memory management
MemoryMax=2G
MemoryHigh=1.5G

# Environment variables
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1

# Network optimizations
Environment=DISCORD_MAX_CONNECTIONS=10
Environment=DISCORD_GATEWAY_TIMEOUT=60

[Install]
WantedBy=multi-user.target
"""
        
        with open('/tmp/dc-bot.service', 'w') as f:
            f.write(config)
        
        print("✅ Optimize edilmiş systemd servisi oluşturuldu: /tmp/dc-bot.service")
        self.recommendations.append("Systemd servisini güncellemek için: sudo cp /tmp/dc-bot.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart dc-bot")
    
    def generate_sysctl_optimizations(self):
        """Network optimizasyonları için sysctl ayarları"""
        sysctl_config = """# Discord Bot Network Optimizations
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 87380 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728
net.ipv4.tcp_congestion_control = bbr
net.ipv4.tcp_window_scaling = 1
net.ipv4.tcp_timestamps = 1
net.ipv4.tcp_sack = 1
net.ipv4.tcp_fack = 1
net.core.netdev_max_backlog = 5000
net.ipv4.tcp_no_metrics_save = 1
net.ipv4.tcp_moderate_rcvbuf = 1
"""
        
        with open('/tmp/99-discord-bot.conf', 'w') as f:
            f.write(sysctl_config)
        
        print("✅ Network optimizasyon ayarları oluşturuldu: /tmp/99-discord-bot.conf")
        self.recommendations.append("Network optimizasyonları için: sudo cp /tmp/99-discord-bot.conf /etc/sysctl.d/ && sudo sysctl -p /etc/sysctl.d/99-discord-bot.conf")
    
    def generate_dns_config(self):
        """DNS optimizasyonları"""
        dns_config = """# Discord Bot DNS Optimizations
nameserver 1.1.1.1
nameserver 1.0.0.1
nameserver 8.8.8.8
options timeout:1 attempts:2 rotate single-request-reopen
"""
        
        with open('/tmp/resolv.conf.optimized', 'w') as f:
            f.write(dns_config)
        
        print("✅ DNS optimizasyon ayarları oluşturuldu: /tmp/resolv.conf.optimized")
        self.recommendations.append("DNS optimizasyonu için: sudo cp /tmp/resolv.conf.optimized /etc/resolv.conf")
    
    async def run_optimization(self):
        """Tüm optimizasyonları çalıştır"""
        await self.analyze_system()
        
        print("\n🛠️  Optimizasyon dosyaları oluşturuluyor...")
        self.generate_systemd_config()
        self.generate_sysctl_optimizations()
        self.generate_dns_config()
        
        print("\n📋 Önerilen Optimizasyonlar:")
        for i, recommendation in enumerate(self.recommendations, 1):
            print(f"{i}. {recommendation}")
        
        print(f"\n🎯 Discord.py Bot Optimizasyonları Uygulandı:")
        print("• max_messages=1000 (bellek kullanımını azaltır)")
        print("• member_cache_flags=none (üye cache'ini devre dışı bırakır)")
        print("• chunk_guilds_at_startup=False (başlangıçta guild chunk'lama yapmaz)")
        print("• heartbeat_timeout=60.0 (heartbeat timeout'ını optimize eder)")
        
        # İstanbul VDS için özel öneriler
        print(f"\n🌍 İstanbul VDS Optimizasyonları:")
        print("• Discord Frankfurt sunucusuna ~40-50ms temel gecikme var")
        print("• İstanbul-Frankfurt arası ideal ping: 40-60ms")
        print("• Mevcut 150ms gecikmenin 80-100ms'ine düşürebiliriz")
        print("• En iyi alternatif: Frankfurt/Amsterdam VDS (20-30ms gecikme)")
        
        print(f"\n🔧 İstanbul İçin Özel Ayarlar:")
        print("• Turk Telekom/Superonline için DNS: 8.8.8.8, 1.1.1.1")
        print("• Vodafone için DNS: 1.1.1.1, 8.8.4.4") 
        print("• BBR congestion control algoritması kullanın")
        print("• TCP window scaling aktif tutun")

if __name__ == "__main__":
    optimizer = BotOptimizer()
    asyncio.run(optimizer.run_optimization())