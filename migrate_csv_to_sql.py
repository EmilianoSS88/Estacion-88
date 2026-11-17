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

        # Open the inventary file in reading mode
        with open(inventary, mode='r', encoding='utf-8-sig') as inventary_file:

            # Read the .csv file
            inventary_read = csv.DictReader(inventary_file)

            # Iterates over every product (row) in inventary
            for product in inventary_read:

                # Clean spaces on product name 
                product_name = product['Producto'].strip()

                # Verify if product name isn't empty and if it is continue to the next iteration
                if not product_name:
                    continue

                # Insert the product in the table and if it exist ignore it
                db.execute("""INSERT OR IGNORE INTO productos 
                        (producto, Precio, Contenido, Medida, Cantidad, Presentacion, Minimo)
                        VALUES (?, ?, ?, ?, ?, ?, ?)""", (product_name, clean_value(product['Precio']), clean_value(product['Contenido']), product['Medida'].strip(), clean_value(product['Cantidad']), product['Presentación'].strip(), clean_value(product['Minimo']))
                )

        # Open the receipes file in reading mode
        with open(recipes, mode='r', encoding='utf-8-sig') as recipes_file:

            # Reads the .csv file
            recipes_read = csv.DictReader(recipes_file)

            # Iterates over every recipe in the file
            for recipe in recipes_read:

                # Clean recipe name
                recipe_name = recipe['Platillo'].strip()

                if not recipe_name:
                    continue

                db.execute('INSERT INTO recetas (platillo, insumo, cantidad_utilizar, margen)')
        
if __name__ == '__main__':
    migrate_all()