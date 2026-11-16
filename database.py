import sqlite3
from config import DB_PATH

def get_connection() -> sqlite3.Connection:
    """Open a conection to the database"""

    # Create the connection with the database
    connection = sqlite3.connect(DB_PATH)

    # Bring exit format (can reach the datbase values with his actual names)
    connection.row_factory = sqlite3.Row
    return connection

def init_db() -> None:

    connection = get_connection()

    # Establish the cursor to make inquires in SQLite3
    db = connection.cursor()

    # Inquires to create db tables
    db.execute("""CREATE TABLE IF NOT EXISTS productos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, 
                producto TEXT UNIQUE NOT NULL, 
                precio REAL NOT NULL DEFAULT 0,
                contenido REAL NOT NULL DEFAULT 1,
                medida TEXT,
                cantidad REAL NOT NULL DEFAULT 0,
                presentacion TEXT,
                minimo REAL NOT NULL DEFAULT 0
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS recetas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platillo TEXT NOT NULL,
        insumo TEXT NOT NULL,
        cantidad_utilizar REAL NOT NULL DEFAULT 0,
        margen REAL NOT NULL DEFAULT 40.0
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT UNIQUE NOT NULL,
        plan TEXT DEFAULT 'Cliente Regular',
        fecha_inicio TEXT,
        fecha_fin TEXT,
        estado TEXT DEFAULT 'Regular',
        telefono TEXT,
        cumpleanos TEXT,
        puntos REAL NOT NULL DEFAULT 0
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS ventas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        platillo TEXT NOT NULL,
        fecha TEXT NOT NULL,
        monto REAL NOT NULL,
        cliente TEXT DEFAULT 'General',
        metodo_pago TEXT DEFAULT 'Efectivo',
        num_recibo TEXT
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS caja (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT UNIQUE NOT NULL,
        fondo_inicial REAL NOT NULL DEFAULT 0,
        fondo_final_real REAL DEFAULT 0,
        diferencia REAL DEFAULT 0,
        estado TEXT NOT NULL DEFAULT 'Abierto'
    )""")

    db.execute("""CREATE TABLE IF NOT EXISTS gastos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        fecha TEXT NOT NULL,
        concepto TEXT NOT NULL,
        monto REAL NOT NULL DEFAULT 0
    )""")

    # Save the changes in the permanent memory
    connection.commit()
    # Close the connection withh the database file
    connection.close()

if __name__ == '__main__':
    init_db()
