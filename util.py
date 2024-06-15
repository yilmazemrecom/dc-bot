import json
import aiosqlite
import aiofiles

DATABASE = 'database/economy.db'

async def init_db():
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS economy (
                user_id TEXT PRIMARY KEY,
                username TEXT,
                bakiye INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS sunucular (
                sunucu_id TEXT PRIMARY KEY,
                sunucu_ismi TEXT,
                sunucu_uye_sayisi INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS takimlar (
                user_id TEXT PRIMARY KEY,
                takim_adi TEXT,
                kaptan TEXT,
                miktari INTEGER,
                kazanilan_mac INTEGER,
                kaybedilen_mac INTEGER
            )
        ''')
        await db.commit()

async def load_economy(user_id):
    async with aiosqlite.connect(DATABASE) as db:
        cursor = await db.execute('SELECT * FROM economy WHERE user_id = ?', (user_id,))
        row = await cursor.fetchone()
        return row

async def save_economy(user_id, username, bakiye):
    async with aiosqlite.connect(DATABASE) as db:
        await db.execute('REPLACE INTO economy (user_id, username, bakiye) VALUES (?, ?, ?)', (user_id, username, bakiye))
        await db.commit()

async def add_user_to_economy(user_id, username):
    economy = await load_economy(user_id)
    if not economy:
        await save_economy(user_id, username, 100)
        economy = (user_id, username, 100)
    return economy

async def load_bilmeceler():
    try:
        async with aiofiles.open('json/bilmeceler.json', mode='r', encoding='utf-8') as f:
            bilmeceler = json.loads(await f.read())
        return bilmeceler
    except FileNotFoundError:
        print("bilmeceler.json bulunamadı!")
        return []
    except json.JSONDecodeError:
        print("bilmeceler.json dosyası düzgün yüklenemedi!")
        return []

async def load_quiz_questions():
    try:
        async with aiofiles.open('json/quiz_sorulari.json', mode='r', encoding='utf-8') as f:
            quiz_sorulari = json.loads(await f.read())
        return quiz_sorulari
    except FileNotFoundError:
        print("quiz_sorulari.json bulunamadı!")
        return []
    except json.JSONDecodeError:
        print("quiz_sorulari.json dosyası düzgün yüklenemedi!")
        return []

async def load_kelime_listesi():
    async with aiofiles.open('json/kelimeler.json', mode='r', encoding='utf-8') as f:
        data = await f.read()
        kelimeler = json.loads(data)['kelimeler']
    return kelimeler