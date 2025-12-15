import sqlite3
import os

DB_NAME = "remusic.db"

class Lagu:
    def __init__(self, id, judul, artis, album, durasi, genre, image=None):
        self.id = id
        self.judul = judul
        self.artis = artis
        self.album = album
        self.durasi = durasi
        self.genre = genre
        self.image = image 

class Node:
    def __init__(self, lagu):
        self.lagu = lagu
        self.prev = None
        self.next = None

class DoublyLinkedList:
    def __init__(self):
        self.head = None
        self.tail = None

    def tambah_last(self, lagu):
        n = Node(lagu)
        if not self.head:
            self.head = self.tail = n
        else:
            self.tail.next = n
            n.prev = self.tail
            self.tail = n

    def hapus(self, id):
        p = self.head
        while p:
            if p.lagu.id == id:
                if p.prev: p.prev.next = p.next
                else: self.head = p.next
                if p.next: p.next.prev = p.prev
                else: self.tail = p.prev
                return True
            p = p.next
        return False

    def cari(self, id):
        p = self.head
        while p:
            if p.lagu.id == id: return p
            p = p.next
        return None

    def get_all(self):
        songs = []
        p = self.head
        while p:
            songs.append(p.lagu)
            p = p.next
        return songs

class Queue:
    def __init__(self):
        self.q = []
    def enqueue(self, item): self.q.append(item)
    def dequeue(self): return self.q.pop(0) if self.q else None
    def get_all(self): return self.q

class Stack:
    def __init__(self):
        self.s = []
    def push(self, item): self.s.append(item)
    def pop(self): return self.s.pop() if self.s else None
    def get_all(self): return self.s[::-1]

class UserSession:
    def __init__(self, username, email, role="user", profile_pic=None):
        self.username = username
        self.email = email
        self.role = role
        self.profile_pic = profile_pic
        self.history = Stack()
        self.queue = Queue()
        self.current_song = None
        # TAMBAHAN: Menyimpan ID playlist yang sedang aktif diputar
        self.active_playlist_id = None 

class DatabaseManager:
    def __init__(self):
        self.init_db()
        self.library = DoublyLinkedList()
        self.reload_library()
        self.active_sessions = {}

    def get_connection(self):
        conn = sqlite3.connect(DB_NAME)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        conn = self.get_connection()
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS users 
                     (email TEXT PRIMARY KEY, username TEXT, password TEXT, role TEXT)''')
        
        c.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in c.fetchall()]
        if 'profile_pic' not in columns:
            c.execute("ALTER TABLE users ADD COLUMN profile_pic TEXT")

        c.execute('''CREATE TABLE IF NOT EXISTS songs 
                     (id TEXT PRIMARY KEY, judul TEXT, artis TEXT, album TEXT, durasi TEXT, genre TEXT, image TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS playlists 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, name TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS playlist_songs 
                     (playlist_id INTEGER, song_id TEXT)''')

        try:
            c.execute("SELECT image FROM songs LIMIT 1")
        except sqlite3.OperationalError:
            c.execute("ALTER TABLE songs ADD COLUMN image TEXT")

        c.execute("SELECT * FROM users WHERE email='admin@remusic.com'")
        if not c.fetchone():
            c.execute("INSERT INTO users (email, username, password, role) VALUES (?, ?, ?, ?)", 
                      ('admin@remusic.com', 'Admin Ganteng', 'admin123', 'admin'))
            
        conn.commit()
        conn.close()

    def reload_library(self):
        self.library = DoublyLinkedList()
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM songs")
        rows = c.fetchall()
        for row in rows:
            img = row['image'] if 'image' in row.keys() else None
            lagu = Lagu(row['id'], row['judul'], row['artis'], row['album'], row['durasi'], row['genre'], img)
            self.library.tambah_last(lagu)
        conn.close()

    def add_user(self, username, email, password, role='user'):
        try:
            conn = self.get_connection()
            c = conn.cursor()
            c.execute("INSERT INTO users (email, username, password, role) VALUES (?, ?, ?, ?)", (email, username, password, role))
            conn.commit()
            conn.close()
            return True
        except sqlite3.IntegrityError:
            return False

    def check_user(self, email, password):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email=? AND password=?", (email, password))
        user_data = c.fetchone()
        conn.close()
        return user_data

    def add_song_db(self, lagu):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO songs VALUES (?, ?, ?, ?, ?, ?, ?)", 
                  (lagu.id, lagu.judul, lagu.artis, lagu.album, lagu.durasi, lagu.genre, lagu.image))
        conn.commit()
        conn.close()
        self.reload_library()

    def delete_song_db(self, id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM songs WHERE id=?", (id,))
        conn.commit()
        conn.close()
        self.reload_library()
    
    def update_song_db(self, id, judul, artis, genre, durasi, image=None):
        conn = self.get_connection()
        c = conn.cursor()
        if image:
            c.execute('''UPDATE songs SET judul=?, artis=?, genre=?, durasi=?, image=? WHERE id=?''',
                      (judul, artis, genre, durasi, image, id))
        else:
            c.execute('''UPDATE songs SET judul=?, artis=?, genre=?, durasi=? WHERE id=?''',
                      (judul, artis, genre, durasi, id))
        conn.commit()
        conn.close()
        self.reload_library()

    def update_user_avatar(self, email, filename):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("UPDATE users SET profile_pic=? WHERE email=?", (filename, email))
        conn.commit()
        conn.close()
        if email in self.active_sessions:
            self.active_sessions[email].profile_pic = filename

    def create_playlist(self, user_email, name):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("INSERT INTO playlists (user_email, name) VALUES (?, ?)", (user_email, name))
        conn.commit()
        conn.close()

    def get_user_playlists(self, user_email, search_query=None):
        conn = self.get_connection()
        c = conn.cursor()
        if search_query:
            query = "SELECT * FROM playlists WHERE user_email=? AND name LIKE ?"
            c.execute(query, (user_email, f'%{search_query}%'))
        else:
            c.execute("SELECT * FROM playlists WHERE user_email=?", (user_email,))
        playlists = c.fetchall()
        conn.close()
        return playlists
    
    def add_song_to_playlist(self, playlist_id, song_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM playlist_songs WHERE playlist_id=? AND song_id=?", (playlist_id, song_id))
        if not c.fetchone():
            c.execute("INSERT INTO playlist_songs VALUES (?, ?)", (playlist_id, song_id))
            conn.commit()
            conn.close()
            return True
        conn.close()
        return False

    def remove_song_from_playlist(self, playlist_id, song_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("DELETE FROM playlist_songs WHERE playlist_id=? AND song_id=?", (playlist_id, song_id))
        conn.commit()
        conn.close()

    def get_playlist_by_id(self, playlist_id):
        conn = self.get_connection()
        c = conn.cursor()
        c.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,))
        playlist = c.fetchone()
        conn.close()
        return playlist

    def get_playlist_songs(self, playlist_id):
        conn = self.get_connection()
        c = conn.cursor()
        query = """
            SELECT s.* FROM songs s
            JOIN playlist_songs ps ON s.id = ps.song_id
            WHERE ps.playlist_id = ?
        """
        c.execute(query, (playlist_id,))
        rows = c.fetchall()
        conn.close()
        
        songs = []
        for row in rows:
            img = row['image'] if 'image' in row.keys() else None
            lagu = Lagu(row['id'], row['judul'], row['artis'], row['album'], row['durasi'], row['genre'], img)
            songs.append(lagu)
        return songs

    # --- FITUR SMART SHUFFLE (GENRE) ---
    def get_random_song_by_genre(self, genre, exclude_id):
        conn = self.get_connection()
        c = conn.cursor()
        # Ambil lagu acak dengan genre sama, tapi bukan lagu yang sedang diputar
        query = "SELECT * FROM songs WHERE genre LIKE ? AND id != ? ORDER BY RANDOM() LIMIT 1"
        c.execute(query, (f'%{genre}%', exclude_id))
        row = c.fetchone()
        conn.close()
        
        if row:
            img = row['image'] if 'image' in row.keys() else None
            return Lagu(row['id'], row['judul'], row['artis'], row['album'], row['durasi'], row['genre'], img)
        return None

store = DatabaseManager()