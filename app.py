import os
import uuid
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from models import store, Lagu, UserSession

app = Flask(__name__)
app.secret_key = 'kunci_rahasia_sqlite_remusic'

app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def get_current_user():
    if 'email' in session:
        email = session['email']
        if email not in store.active_sessions:
            conn = store.get_connection()
            c = conn.cursor()
            try:
                c.execute("SELECT username, role, profile_pic FROM users WHERE email=?", (email,))
            except:
                 c.execute("SELECT username, role FROM users WHERE email=?", (email,))
            data = c.fetchone()
            conn.close()
            if data:
                p_pic = data['profile_pic'] if 'profile_pic' in data.keys() else None
                store.active_sessions[email] = UserSession(data['username'], email, data['role'], p_pic)
            else:
                return None
        return store.active_sessions[email]
    return None

@app.route('/')
def index():
    if 'email' in session:
        return redirect(url_for('main'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user_data = store.check_user(email, password)
        if user_data:
            session['email'] = user_data['email']
            session['role'] = user_data['role']
            if email not in store.active_sessions:
                store.active_sessions[email] = UserSession(user_data['username'], email, user_data['role'])
            if user_data['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('main'))
        else:
            flash('Email atau Password salah!')
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        success = store.add_user(username, email, password)
        if success:
            flash('Akun berhasil dibuat! Silakan login.')
            return redirect(url_for('login'))
        else:
            flash('Email sudah terdaftar! Gunakan email lain.')
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/main')
def main():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    all_songs = store.library.get_all()
    search_query = request.args.get('q')
    if search_query:
        search_query = search_query.lower()
        all_songs = [s for s in all_songs if search_query in s.judul.lower() or search_query in s.artis.lower()]
    playlists = store.get_user_playlists(user.email)
    return render_template('main.html', user=user, songs=all_songs, playlists=playlists)

@app.route('/profile')
def profile():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    return render_template('profile.html', user=user)

@app.route('/profile/update_avatar', methods=['POST'])
def update_avatar():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    if 'avatar_file' in request.files and request.files['avatar_file'].filename != '':
        file = request.files['avatar_file']
        if file and allowed_file(file.filename):
            filename = secure_filename(f"avatar_{user.username}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            store.update_user_avatar(user.email, filename)
            flash("Foto profil berhasil diupload!")
    elif 'avatar_preset' in request.form:
        preset_url = request.form['avatar_preset']
        store.update_user_avatar(user.email, preset_url)
        flash("Avatar berhasil diganti!")
    return redirect(url_for('profile'))

# --- LOGIKA PLAY DIPERBARUI ---
@app.route('/play/<song_id>')
def play_song(song_id):
    user = get_current_user()
    if not user: return redirect(url_for('login'))

    node = store.library.cari(song_id)
    if node:
        # Masukkan lagu saat ini ke history sebelum diganti
        if user.current_song:
            user.history.push(user.current_song)
        
        user.current_song = node.lagu
        
        # CEK CONTEXT: Apakah play dari playlist atau halaman utama?
        playlist_id = request.args.get('playlist_id')
        if playlist_id:
            user.active_playlist_id = int(playlist_id) # Set context Playlist
        else:
            user.active_playlist_id = None # Set context Umum (Library)
    
    return redirect(request.referrer or url_for('main'))

# --- LOGIKA NEXT DIPERBARUI (QUEUE -> PLAYLIST -> GENRE) ---
@app.route('/next')
def next_song():
    user = get_current_user()
    if not user: return redirect(url_for('login'))

    # 1. PRIORITAS UTAMA: Cek Queue Manual
    next_song_obj = user.queue.dequeue()
    if next_song_obj:
        if user.current_song:
            user.history.push(user.current_song)
        user.current_song = next_song_obj
        return redirect(request.referrer or url_for('main'))

    # Jika Queue Kosong, Cek Context
    if user.current_song:
        
        # 2. KONTEKS PLAYLIST: Cari lagu berikutnya di playlist
        if user.active_playlist_id:
            playlist_songs = store.get_playlist_songs(user.active_playlist_id)
            # Cari index lagu saat ini di playlist
            current_index = -1
            for i, s in enumerate(playlist_songs):
                if s.id == user.current_song.id:
                    current_index = i
                    break
            
            # Jika ketemu dan bukan lagu terakhir
            if current_index != -1 and current_index < len(playlist_songs) - 1:
                user.history.push(user.current_song)
                user.current_song = playlist_songs[current_index + 1]
            else:
                # Jika sudah lagu terakhir di playlist, bisa stop atau loop (disini kita stop/tetap)
                pass 

        # 3. KONTEKS UMUM/LIBRARY: Cari lagu MIRIP (Genre sama)
        else:
            similar_song = store.get_random_song_by_genre(user.current_song.genre, user.current_song.id)
            if similar_song:
                user.history.push(user.current_song)
                user.current_song = similar_song
            else:
                # Jika tidak ada lagu genre sama, fallback ke urutan library biasa (linked list)
                current_node = store.library.cari(user.current_song.id)
                if current_node and current_node.next:
                    user.history.push(user.current_song)
                    user.current_song = current_node.next.lagu

    return redirect(request.referrer or url_for('main'))

# --- LOGIKA PREV DIPERBARUI ---
@app.route('/prev')
def prev_song():
    user = get_current_user()
    if not user: return redirect(url_for('login'))

    # 1. PRIORITAS: Cek History (Lagu yang baru saja diputar)
    prev_song_obj = user.history.pop()
    if prev_song_obj:
        user.current_song = prev_song_obj
    
    # 2. Jika History Kosong tapi sedang di Playlist
    elif user.current_song and user.active_playlist_id:
         playlist_songs = store.get_playlist_songs(user.active_playlist_id)
         current_index = -1
         for i, s in enumerate(playlist_songs):
            if s.id == user.current_song.id:
                current_index = i
                break
         
         if current_index > 0:
             user.current_song = playlist_songs[current_index - 1]

    return redirect(request.referrer or url_for('main'))
# ------------------------------------------------

@app.route('/queue')
def queue_view():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    return render_template('queue.html', user=user, queue=user.queue.get_all())

@app.route('/add_to_queue/<song_id>')
def add_to_queue(song_id):
    user = get_current_user()
    node = store.library.cari(song_id)
    if node:
        user.queue.enqueue(node.lagu)
    return redirect(request.referrer or url_for('main'))

@app.route('/history')
def history_view():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    return render_template('history.html', user=user, history=user.history.get_all())

@app.route('/playlists')
def my_playlists():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    search_query = request.args.get('q')
    playlists = store.get_user_playlists(user.email, search_query)
    return render_template('playlists.html', user=user, playlists=playlists)

@app.route('/playlist/<int:playlist_id>')
def playlist_detail(playlist_id):
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    playlist = store.get_playlist_by_id(playlist_id)
    if not playlist:
        flash("Playlist tidak ditemukan!")
        return redirect(url_for('my_playlists'))
    songs = store.get_playlist_songs(playlist_id)
    return render_template('playlist_detail.html', user=user, playlist=playlist, songs=songs)

@app.route('/playlists/create', methods=['POST'])
def create_playlist():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    name = request.form['name']
    if name:
        store.create_playlist(user.email, name)
        flash(f"Playlist '{name}' dibuat!")
    return redirect(url_for('my_playlists'))

@app.route('/add_to_playlist/<song_id>/<int:playlist_id>')
def add_to_playlist_action(song_id, playlist_id):
    success = store.add_song_to_playlist(playlist_id, song_id)
    if success:
        flash("Lagu ditambahkan ke playlist!")
    else:
        flash("Lagu sudah ada di playlist ini.")
    return redirect(request.referrer or url_for('main'))

@app.route('/remove_from_playlist/<song_id>/<int:playlist_id>')
def remove_from_playlist(song_id, playlist_id):
    store.remove_song_from_playlist(playlist_id, song_id)
    flash("Lagu dihapus dari playlist.")
    return redirect(url_for('playlist_detail', playlist_id=playlist_id))

@app.route('/admin')
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    all_songs = store.library.get_all()
    return render_template('admin_dashboard.html', songs=all_songs)

@app.route('/admin/add', methods=['GET', 'POST'])
def add_song():
    if 'role' not in session or session['role'] != 'admin': 
        return redirect(url_for('login'))
    user = get_current_user()
    if request.method == 'POST':
        try:
            id = str(uuid.uuid4())[:8]
            judul = request.form['judul']
            artis = request.form['artis']
            album = "Single" 
            durasi = request.form['durasi']
            genre = request.form['genre']
            image_filename = None 
            if 'cover' in request.files:
                file = request.files['cover']
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    unique_filename = f"{id}_{filename}"
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                    image_filename = unique_filename
            new_song = Lagu(id, judul, artis, album, durasi, genre)
            new_song.image = image_filename 
            store.add_song_db(new_song)
            flash("Lagu berhasil ditambahkan!")
            return redirect(url_for('admin_dashboard'))
        except Exception as e:
            flash(f"Gagal menambah lagu: {str(e)}")
            return redirect(url_for('add_song'))
    return render_template('add_song.html', user=user)

@app.route('/admin/delete/<song_id>')
def delete_song(song_id):
    if 'role' not in session or session['role'] != 'admin': return redirect(url_for('login'))
    store.delete_song_db(song_id)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit/<song_id>', methods=['GET', 'POST'])
def edit_song(song_id):
    if 'role' not in session or session['role'] != 'admin': 
        return redirect(url_for('login'))
    node = store.library.cari(song_id)
    if not node:
        flash("Lagu tidak ditemukan.")
        return redirect(url_for('admin_dashboard'))
    song = node.lagu
    if request.method == 'POST':
        judul = request.form['judul']
        artis = request.form['artis']
        genre = request.form['genre']
        durasi = request.form['durasi']
        image_filename = None
        if 'cover' in request.files:
            file = request.files['cover']
            if file and file.filename != '' and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                unique_filename = f"{song_id}_{filename}"
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
                image_filename = unique_filename
        store.update_song_db(song_id, judul, artis, genre, durasi, image_filename)
        flash("Lagu berhasil diperbarui!")
        return redirect(url_for('admin_dashboard'))
    return render_template('edit_song.html', song=song)

if __name__ == '__main__':
    app.run(debug=True)