from flask import Flask, render_template, request, jsonify, session
import sqlite3
import bcrypt
import re
import os

app = Flask(__name__)
app.secret_key = 'clave_secreta_tiendas_urbano_rqy1101'
DB_PATH = os.path.join(os.path.dirname(__file__), 'tiendas_urbano.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rut TEXT NOT NULL UNIQUE,
            nombre_completo TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            categoria TEXT NOT NULL,
            talla TEXT NOT NULL,
            color TEXT NOT NULL,
            material TEXT NOT NULL,
            precio INTEGER NOT NULL,
            stock INTEGER NOT NULL,
            imagen TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS favoritos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            producto_id INTEGER NOT NULL,
            UNIQUE(cliente_id, producto_id),
            FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE,
            FOREIGN KEY (producto_id) REFERENCES productos(id) ON DELETE CASCADE
        );
    """)

    cur.execute("SELECT COUNT(*) FROM productos")
    if cur.fetchone()[0] == 0:
        productos_iniciales = [
            ('Blazer Entallado Importado', 'Blazers', 'M', 'Negro', 'Poliéster', 39990, 6, 'blazer_negro.jpg'),
            ('Parka Térmica Urbana', 'Parkas', 'L', 'Verde', 'Nylon', 54990, 4, 'parka_verde.jpg'),
            ('Polera Básica Importada', 'Poleras', 'S', 'Blanco', 'Algodón', 14990, 15, 'polera_blanca.jpg'),
            ('Pantalón Recto Casual', 'Pantalones', 'M', 'Beige', 'Algodón', 29990, 7, 'pantalon_beige.jpg'),
            ('Chaqueta Corta Temporada', 'Chaquetas', 'S', 'Negro', 'Cuero PU', 44990, 5, 'chaqueta_negra.jpg'),
            ('Traje de Baño Dos Piezas', 'Trajes de Baño', 'M', 'Azul', 'Spandex', 22990, 9, 'traje_bano_azul.jpg'),
            ('Conjunto Blusa y Falda Femenina', 'Ropa Femenina', 'S', 'Rojo', 'Viscosa', 34990, 8, 'femenina_rojo.jpg')
        ]
        cur.executemany(
            "INSERT INTO productos (nombre, categoria, talla, color, material, precio, stock, imagen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            productos_iniciales
        )
    conn.commit()
    conn.close()

def validar_rut_chileno(rut_raw):
    rut = re.sub(r'[^0-9kK]', '', rut_raw).upper()
    if len(rut) < 8 or len(rut) > 9:
        return False, None
    cuerpo, dv = rut[:-1], rut[-1]
    if not cuerpo.isdigit():
        return False, None

    suma = 0
    multiplo = 2
    for c in reversed(cuerpo):
        suma += int(c) * multiplo
        multiplo = 2 if multiplo == 7 else multiplo + 1

    resto = 11 - (suma % 11)
    dv_esperado = '0' if resto == 11 else ('K' if resto == 10 else str(resto))

    if dv == dv_esperado:
        rut_formateado = f"{int(cuerpo):,}".replace(",", ".") + f"-{dv}"
        return True, rut_formateado
    return False, None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/registro', methods=['POST'])
def registro():
    data = request.json or {}
    nombre = data.get('nombre', '').strip()
    rut_raw = data.get('rut', '').strip()
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    if not all([nombre, rut_raw, email, password]):
        return jsonify({'ok': False, 'error': 'Todos los campos son obligatorios.'}), 400

    es_valido, rut_limpio = validar_rut_chileno(rut_raw)
    if not es_valido:
        return jsonify({'ok': False, 'error': 'El RUT ingresado no es válido.'}), 400

    if len(password) < 6:
        return jsonify({'ok': False, 'error': 'La contraseña debe tener al menos 6 caracteres.'}), 400

    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM clientes WHERE rut = ? OR email = ?", (rut_limpio, email))
        if cursor.fetchone():
            return jsonify({'ok': False, 'error': 'Ya existe una cuenta registrada con ese RUT o correo.'}), 409

        cursor.execute(
            "INSERT INTO clientes (rut, nombre_completo, email, password_hash) VALUES (?, ?, ?, ?)",
            (rut_limpio, nombre, email, hashed_pw)
        )
        conn.commit()
        user_id = cursor.lastrowid
        session['user'] = {'id': user_id, 'nombre': nombre, 'rut': rut_limpio, 'email': email}
        return jsonify({'ok': True, 'user': session['user'], 'hash_preview': hashed_pw[:25] + '...'})
    finally:
        conn.close()

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json or {}
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM clientes WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()

    if user and bcrypt.checkpw(password.encode('utf-8'), user['password_hash'].encode('utf-8')):
        session['user'] = {'id': user['id'], 'nombre': user['nombre_completo'], 'rut': user['rut'], 'email': user['email']}
        return jsonify({'ok': True, 'user': session['user']})
    return jsonify({'ok': False, 'error': 'Correo o contraseña incorrectos.'}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    session.pop('carrito', None)
    return jsonify({'ok': True})

@app.route('/api/estado')
def estado():
    user = session.get('user')
    carrito = session.get('carrito', {})
    favoritos = []
    if user:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT producto_id FROM favoritos WHERE cliente_id = ?", (user['id'],))
        favoritos = [row['producto_id'] for row in cursor.fetchall()]
        conn.close()
    return jsonify({'user': user, 'carrito': carrito, 'favoritos': favoritos})

@app.route('/api/productos')
def get_productos():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM productos ORDER BY id ASC")
    productos = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return jsonify(productos)

@app.route('/api/favoritos/toggle', methods=['POST'])
def toggle_favorito():
    user = session.get('user')
    if not user:
        return jsonify({'ok': False, 'error': 'Debes iniciar sesión o registrarte para guardar favoritos.'}), 401

    prod_id = int((request.json or {}).get('producto_id'))
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM favoritos WHERE cliente_id = ? AND producto_id = ?", (user['id'], prod_id))
    existe = cursor.fetchone()

    if existe:
        cursor.execute("DELETE FROM favoritos WHERE cliente_id = ? AND producto_id = ?", (user['id'], prod_id))
        agregado = False
    else:
        cursor.execute("INSERT INTO favoritos (cliente_id, producto_id) VALUES (?, ?)", (user['id'], prod_id))
        agregado = True

    conn.commit()
    cursor.execute("SELECT producto_id FROM favoritos WHERE cliente_id = ?", (user['id'],))
    lista_favs = [row['producto_id'] for row in cursor.fetchall()]
    conn.close()
    return jsonify({'ok': True, 'agregado': agregado, 'favoritos': lista_favs})

@app.route('/api/carrito', methods=['POST'])
def gestionar_carrito():
    data = request.json or {}
    prod_id = str(data.get('producto_id'))
    accion = data.get('accion')
    cantidad = int(data.get('cantidad', 1))

    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, nombre, precio, stock FROM productos WHERE id = ?", (prod_id,))
    prod = cursor.fetchone()
    conn.close()

    if not prod:
        return jsonify({'ok': False, 'error': 'Producto no encontrado.'}), 404

    carrito = session.get('carrito', {})

    if accion == 'remove':
        carrito.pop(prod_id, None)
    elif accion == 'add':
        nueva_cant = carrito.get(prod_id, 0) + cantidad
        if nueva_cant > prod['stock']:
            return jsonify({'ok': False, 'error': f"Stock insuficiente. Disponible: {prod['stock']} un."}), 400
        carrito[prod_id] = nueva_cant
    elif accion == 'update':
        if cantidad <= 0:
            carrito.pop(prod_id, None)
        elif cantidad > prod['stock']:
            return jsonify({'ok': False, 'error': f"Stock máximo disponible: {prod['stock']} un."}), 400
        else:
            carrito[prod_id] = cantidad

    session['carrito'] = carrito
    session.modified = True
    return jsonify({'ok': True, 'carrito': carrito})

init_db()

if __name__ == '__main__':
    app.run(debug=True)