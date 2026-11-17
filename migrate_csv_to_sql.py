import os
import csv
from config import BASE_DIR
from database import get_connection, init_db

def clean_value(value: str | None, default: float = 0.0) -> float:
    """Clean a value and return it only in float without any other char"""

    # Return the default value if the argument value is empty
    if value is None:
        return default

    value = str(value)
    # Clean the value of the extra chars
    value = value.replace(' ', '').replace('$', '').replace(',', '').replace('%','')

    try:
        value = float(value)
    except ValueError:
        return default
    
    return value

def migrate_all():
    """MIgrate the .csv files to the database SQLite3"""

    # Charge the tables for the database
    init_db()

    # Keep the connection and cursor open
    connection = get_connection()
    db = connection.cursor()

    # Declare the path of .csv files
    inventary = os.path.join(BASE_DIR, 'inventario.csv')
    recipes = os.path.join(BASE_DIR, 'recetas.csv')
    subscriptions = os.path.join(BASE_DIR, 'suscripciones.csv')
    sells = os.path.join(BASE_DIR, 'ventas.csv')
    box = os.path.join(BASE_DIR, 'caja.csv')
    bills = os.path.join(BASE_DIR, 'gastos.csv')

    # Check if the .csv file exist (os.path.exist(path) return True if exist and False if not)
    if os.path.exists(inventary):

        # Open the file in reading mode
        with open(inventary, mode='r', encoding='utf-8-sig') as inventary_file:

            inventary_read = csv.DictReader(inventary_file)

            for product in inventary_read:

                product_name = product['Producto'].strip()

                if not product_name:
                    continue

                db.execute("""INSERT OR IGNORE INTO productos 
                        (producto, Precio, Contenido, Medida, Cantidad, Presentacion, Minimo)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""", (product_name, clean_value(product['Precio']), clean_value(product['Contenido']), product['Medida'].strip(), clean_value(product['Cantidad']), product['Presentación'].strip(), clean_value(product['Minimo']))
                )

        with open(recipes, mode='r', encoding='utf-8-sig') as recipes_file:

            recipes_read = csv.DictReader(recipes_file)

            for receipe in recipes_read:
                print(receipe)
        
if __name__ == '__main__':
    migrate_all()