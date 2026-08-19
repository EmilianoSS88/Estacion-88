import csv

# Esta es la "caja" grande (una lista) donde guardaremos todos los productos
base_de_datos = []

# Le decimos a Python que abra nuestro archivo y lo lea en español (utf-8)
with open('inventario.csv', mode='r', encoding='utf-8') as archivo:
    lector = csv.DictReader(archivo)
    
    # Esto es un "ciclo": Python va a repetir este bloque por cada fila del Excel
    for fila in lector:
        nombre = fila['Producto']
        precio = fila['Precio']
        presentacion = fila['Presentación']
        medida = fila['Medida']
        
        # 1. EXTRAEMOS LA CANTIDAD CON TU SEGURO ANTI-ERRORES
        try:
            # Intentamos convertir el texto del Excel a un número entero
            cantidad_real = int(fila['Cantidad'])
        except (ValueError, KeyError):
            # Si la celda está vacía, no existe o hay letras, le ponemos 0
            cantidad_real = 0
        
        # 2. ✨ LA SOLUCIÓN: Guardamos como diccionario con las llaves EXACTAS que pide el HTML
        nuevo_producto = {
            'Producto': nombre,
            'Precio': precio,
            'Presentación': presentacion,
            'Medida': medida,
            'Cantidad': cantidad_real
        }
        base_de_datos.append(nuevo_producto)

# --- Comprobación de que todo funcionó ---
print(f"¡Éxito! Se cargaron {len(base_de_datos)} productos a la memoria del sistema.")
print(f"Primer producto registrado: {base_de_datos[0]['Producto']} con {base_de_datos[0]['Cantidad']} en stock.")
print(f"Último producto registrado: {base_de_datos[-1]['Producto']} con {base_de_datos[-1]['Cantidad']} en stock.")