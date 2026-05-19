import sqlite3
import string
import random
from flask import Flask, g, render_template, request, jsonify, redirect, url_for

DB = 'game.db'
app = Flask(__name__)
app.secret_key = 'change-this-secret'

THEMES = {
    'Football': ["FC Barcelona","Real Madrid","Manchester United","Liverpool FC","Etoile du Sahel","Esperance de Tunis","Club Africain","CSS"],
    'Food': ["Pizza","Spagetti","CousCous","Burger","Ojja","Salad"]
}

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB, check_same_thread=False)
        db.row_factory = sqlite3.Row
    return db

def init_db():
    db = get_db()
    c = db.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE,
                    host_name TEXT,
                    theme TEXT,
                    state TEXT,
                    host_item TEXT,
                    guest_item TEXT,
                    turn INTEGER
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS players (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_code TEXT,
                    name TEXT,
                    role TEXT
                )''')
    c.execute('''CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_code TEXT,
                    sender TEXT,
                    text TEXT,
                    type TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )''')
    db.commit()

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def gen_code(n=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=n))

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_room', methods=['POST'])
def create_room():
    data = request.json
    name = data.get('name','').strip()
    theme = data.get('theme')
    if not name or theme not in THEMES:
        return jsonify({'ok': False, 'error': 'Invalid input'}), 400
    db = get_db()
    code = gen_code(5)
    # ensure uniqueness
    c = db.cursor()
    while c.execute('SELECT 1 FROM rooms WHERE code=?', (code,)).fetchone():
        code = gen_code(5)
    c.execute('INSERT INTO rooms (code, host_name, theme, state, turn) VALUES (?,?,?,?,?)',
              (code, name, theme, 'lobby', 1))
    c.execute('INSERT INTO players (room_code, name, role) VALUES (?,?,?)', (code, name, 'host'))
    db.commit()
    return jsonify({'ok': True, 'code': code})

@app.route('/join_room', methods=['POST'])
def join_room():
    data = request.json
    name = data.get('name','').strip()
    code = data.get('code','').strip().upper()
    if not name or not code:
        return jsonify({'ok': False, 'error': 'Invalid input'}), 400
    db = get_db()
    c = db.cursor()
    room = c.execute('SELECT * FROM rooms WHERE code=?', (code,)).fetchone()
    if not room:
        return jsonify({'ok': False, 'error': 'Room not found'}), 404
    players = c.execute('SELECT * FROM players WHERE room_code=?', (code,)).fetchall()
    if len(players) >= 2:
        return jsonify({'ok': False, 'error': 'Room full'}), 403
    role = 'guest'
    c.execute('INSERT INTO players (room_code, name, role) VALUES (?,?,?)', (code, name, role))
    db.commit()
    return jsonify({'ok': True, 'code': code})

@app.route('/room/<code>')
def room_page(code):
    return render_template('lobby.html', code=code.upper())

@app.route('/state/<code>', methods=['GET'])
def state(code):
    code = code.upper()
    db = get_db()
    c = db.cursor()
    room = c.execute('SELECT * FROM rooms WHERE code=?', (code,)).fetchone()
    if not room:
        return jsonify({'ok': False, 'error': 'No room'}), 404
    players = [dict(x) for x in c.execute('SELECT name, role FROM players WHERE room_code=?', (code,)).fetchall()]
    msgs = [dict(x) for x in c.execute('SELECT sender,text,type,timestamp FROM messages WHERE room_code=? ORDER BY id DESC LIMIT 50', (code,)).fetchall()][::-1]
    return jsonify({
        'ok': True,
        'room': dict(room),
        'players': players,
        'messages': msgs
    })

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    code = data.get('code','').upper()
    sender = data.get('sender','').strip()
    text = data.get('text','').strip()
    mtype = data.get('type','chat')  # chat, guess, system, response
    if not code or not sender:
        return jsonify({'ok': False}), 400
    db = get_db()
    c = db.cursor()
    c.execute('INSERT INTO messages (room_code, sender, text, type) VALUES (?,?,?,?)', (code, sender, text, mtype))
    db.commit()
    return jsonify({'ok': True})

@app.route('/start_game', methods=['POST'])
def start_game():
    data = request.json
    code = data.get('code','').upper()
    starter = data.get('starter','').strip()
    db = get_db()
    c = db.cursor()
    room = c.execute('SELECT * FROM rooms WHERE code=?', (code,)).fetchone()
    if not room:
        return jsonify({'ok': False, 'error': 'No room'}), 404
    players = c.execute('SELECT name, role FROM players WHERE room_code=?', (code,)).fetchall()
    if len(players) < 2:
        return jsonify({'ok': False, 'error': 'Need 2 players'}), 403
    theme = room['theme']
    items = THEMES.get(theme, [])
    # assign random items
    shuffled = random.sample(items, 2 if len(items)>=2 else len(items))
    host_item = shuffled[0]
    guest_item = shuffled[1] if len(shuffled) > 1 else shuffled[0]
    # store items and set state to playing; turn uses 1 for host, 2 for guest
    c.execute('UPDATE rooms SET state=?, host_item=?, guest_item=?, turn=? WHERE code=?', ('playing', host_item, guest_item, 1 if room['host_name'] else 1, code))
    # save system message indicating game started (without revealing items)
    c.execute('INSERT INTO messages (room_code, sender, text, type) VALUES (?,?,?,?)', (code, 'system', f'Game started. Theme: {theme}', 'system'))
    db.commit()
    return jsonify({'ok': True})

@app.route('/get_items/<code>', methods=['GET'])
def get_items(code):
    code = code.upper()
    name = request.args.get('name','').strip()
    if not name:
        return jsonify({'ok': False}), 400
    db = get_db()
    c = db.cursor()
    room = c.execute('SELECT * FROM rooms WHERE code=?', (code,)).fetchone()
    if not room:
        return jsonify({'ok': False}), 404
    # return the specific player's own item only
    host_name = room['host_name']
    if name == host_name:
        return jsonify({'ok': True, 'your_item': room['host_item']})
    else:
        return jsonify({'ok': True, 'your_item': room['guest_item']})

@app.route('/turn_action', methods=['POST'])
def turn_action():
    data = request.json
    code = data.get('code','').upper()
    actor = data.get('actor','').strip()
    action = data.get('action')  # 'ask' or 'respond' or 'guess'
    text = data.get('text','')
    db = get_db()
    c = db.cursor()
    room = c.execute('SELECT * FROM rooms WHERE code=?', (code,)).fetchone()
    if not room:
        return jsonify({'ok': False,'error':'no room'}), 404
    # determine roles
    players = c.execute('SELECT name, role FROM players WHERE room_code=?', (code,)).fetchall()
    if len(players) < 1:
        return jsonify({'ok': False}), 403
    host = room['host_name']
    guest_row = c.execute('SELECT name FROM players WHERE room_code=? AND role=?', (code,'guest')).fetchone()
    guest = guest_row['name'] if guest_row else None
    # determine whose turn (1 host, 2 guest)
    turn = room['turn']
    actor_role = 'host' if actor == host else ('guest' if actor == guest else None)
    if not actor_role:
        return jsonify({'ok': False}), 403
    # check turn validity
    if (turn == 1 and actor_role != 'host') or (turn == 2 and actor_role != 'guest'):
        return jsonify({'ok': False, 'error':'Not your turn'}), 403
    # enforce response types
    if action == 'ask':
        # asking is free text: add chat message by actor
        c.execute('INSERT INTO messages (room_code, sender, text, type) VALUES (?,?,?,?)', (code, actor, text, 'ask'))
        # switch turn
        new_turn = 2 if turn==1 else 1
        c.execute('UPDATE rooms SET turn=? WHERE code=?', (new_turn,code))
        db.commit()
        return jsonify({'ok': True})
    elif action == 'respond':
        # response must be yes/no - we don't strictly enforce content but expect "yes" or "no"
        resp = text.strip().lower()
        if resp not in ('yes','no'):
            return jsonify({'ok': False, 'error':'Responses must be yes or no'}), 400
        c.execute('INSERT INTO messages (room_code, sender, text, type) VALUES (?,?,?,?)', (code, actor, resp, 'response'))
        new_turn = 2 if turn==1 else 1
        c.execute('UPDATE rooms SET turn=? WHERE code=?', (new_turn,code))
        db.commit()
        return jsonify({'ok': True})
    elif action == 'guess':
        guess = text.strip()
        # determine the target's item
        target_item = None
        correct = False
        if actor_role == 'host':
            target_item = room['guest_item']
        else:
            target_item = room['host_item']
        if guess.lower() == (target_item or '').lower():
            # correct guess -> round over
            c.execute('INSERT INTO messages (room_code, sender, text, type) VALUES (?,?,?,?)', (code, actor, f'GUESS: {guess} (CORRECT)', 'guess'))
            c.execute('UPDATE rooms SET state=? WHERE code=?', ('finished', code))
            c.execute('INSERT INTO messages (room_code, sender, text, type) VALUES (?,?,?,?)', (code, 'system', f'{actor} guessed correctly! Item: {target_item}', 'system'))
            db.commit()
            return jsonify({'ok': True, 'result': 'correct', 'item': target_item})
        else:
            c.execute('INSERT INTO messages (room_code, sender, text, type) VALUES (?,?,?,?)', (code, actor, f'GUESS: {guess} (WRONG)', 'guess'))
            # give turn to other player
            new_turn = 2 if turn==1 else 1
            c.execute('UPDATE rooms SET turn=? WHERE code=?', (new_turn,code))
            db.commit()
            return jsonify({'ok': True, 'result': 'wrong'})
    else:
        return jsonify({'ok': False}), 400

@app.route('/reset_round', methods=['POST'])
def reset_round():
    data = request.json
    code = data.get('code','').upper()
    action = data.get('action')  # 'new' or 'end'
    db = get_db()
    c = db.cursor()
    room = c.execute('SELECT * FROM rooms WHERE code=?', (code,)).fetchone()
    if not room:
        return jsonify({'ok': False}), 404
    if action == 'new':
        theme = room['theme']
        items = THEMES.get(theme, [])
        shuffled = random.sample(items, 2 if len(items)>=2 else len(items))
        host_item = shuffled[0]
        guest_item = shuffled[1] if len(shuffled) > 1 else shuffled[0]
        c.execute('UPDATE rooms SET state=?, host_item=?, guest_item=?, turn=? WHERE code=?', ('playing', host_item, guest_item, 1, code))
        c.execute('INSERT INTO messages (room_code, sender, text, type) VALUES (?,?,?,?)', (code, 'system', 'New round started', 'system'))
        db.commit()
        return jsonify({'ok': True})
    else:
        # end lobby: delete room and players, keep history if you want; here just set state to closed
        c.execute('UPDATE rooms SET state=? WHERE code=?', ('closed', code))
        c.execute('INSERT INTO messages (room_code, sender, text, type) VALUES (?,?,?,?)', (code, 'system', 'Lobby closed by host', 'system'))
        db.commit()
        return jsonify({'ok': True})

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
