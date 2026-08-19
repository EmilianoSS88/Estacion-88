import os
import csv
import requests
import pytz
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, session
from functools import wraps
from dotenv import load_dotenv

# Cargar variables de entorno del archivo .env relativo a la carpeta del proyecto
basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, '.env'))

# Zona horaria de la Ciudad de México (Gustavo A. Madero / UTC-6)
ZONA_CDMX = pytz.timezone('America/Mexico_City')

def obtener_ahora():
    """Retorna datetime con zona horaria de la Ciudad de México."""
    return datetime.now(ZONA_CDMX)

def obtener_fecha_hoy():
    """Retorna fecha de hoy en formato YYYY-MM-DD en hora de CDMX."""
    return obtener_ahora().strftime('%Y-%m-%d')

app = Flask(__name__)
# 👇 Esta llave secreta es obligatoria para usar sesiones. ¡No la borres!
app.secret_key = os.getenv('FLASK_SECRET', 'estacion88_llave_super_secreta')

# Creamos las listas globales en la memoria
base_de_datos = []
recetas_bd = []
clientes_bd = []

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Si el usuario no tiene su "pulsera VIP", lo mandamos a la pantalla de login
        if 'usuario' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- RUTA: PANTALLA DE LOGIN ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario')
        password = request.form.get('password')

        admin_user = os.getenv('ADMIN_USER', 'admin')
        admin_pass = os.getenv('ADMIN_PASSWORD', '171018')

        if usuario == admin_user and password == admin_pass:
            session['usuario'] = usuario
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error="Usuario o contraseña incorrectos ❌")

    return render_template('login.html', error=None)



# --- RUTA: CERRAR SESIÓN ---
@app.route('/logout')
def logout():
    session.pop('usuario', None) # Le quitamos la pulsera VIP
    return redirect(url_for('login'))

def cargar_datos_iniciales():
    global base_de_datos, recetas_bd

    base_de_datos = []
    if os.path.exists('inventario.csv'):
        with open('inventario.csv', mode='r', encoding='utf-8') as archivo:
            lector = csv.DictReader(archivo)
            if lector.fieldnames:
                lector.fieldnames = [field.strip() for field in lector.fieldnames]

            for fila in lector:
                try:
                    val_cantidad = fila.get('Cantidad') or fila.get('cantidad') or 0
                    cantidad_real = float(val_cantidad)
                except ValueError:
                    cantidad_real = 0.0

                # Extraemos el contenido real para guardarlo en la memoria
                try:
                    val_contenido = fila.get('Contenido') or fila.get('contenido') or 1
                    contenido_real = float(val_contenido)
                    if contenido_real <= 0: contenido_real = 1.0
                except ValueError:
                    contenido_real = 1.0

                try:
                    val_minimo = fila.get('Minimo') or fila.get('minimo') or 5
                    minimo_real = float(val_minimo)
                except ValueError:
                    minimo_real = 5.0

                nuevo_producto = {
                    'Producto': fila.get('Producto', 'Sin Nombre'),
                    'Medida': fila.get('Medida', ''),
                    'Presentación': fila.get('Presentación', ''),
                    'Precio': fila.get('Precio', '$0.00'),
                    'Cantidad': cantidad_real,
                    'Contenido': contenido_real,
                    'Minimo': minimo_real  # <-- Guardado en memoria
                }
                base_de_datos.append(nuevo_producto)

    # 2. CARGAMOS LAS RECETAS
    recetas_bd = []
    if os.path.exists('recetas.csv'):
        with open('recetas.csv', mode='r', encoding='utf-8') as archivo:
            lector = csv.DictReader(archivo)
            for fila in lector:
                try:
                    cantidad_uso = float(fila.get('Cantidad a utilizar', 0))
                except (ValueError, TypeError):
                    cantidad_uso = 0.0

                # 👇 NUEVO: Atrapamos el margen de ganancia (40% por defecto)
                try:
                    margen_str = str(fila.get('Margen', 40)).replace('%', '').strip()
                    margen_val = float(margen_str) if margen_str else 40.0
                except (ValueError, TypeError):
                    margen_val = 40.0

                recetas_bd.append({
                    'Platillo': fila.get('Platillo', ''),
                    'Insumo': fila.get('Insumo', ''),
                    'Cantidad a utilizar': cantidad_uso,
                    'Margen': margen_val # Lo guardamos en la memoria
                })

    # 3. CARGAMOS EL CATÁLOGO GLOBAL DE CLIENTES PARA EL PUNTO DE VENTA
    global clientes_bd
    clientes_bd = []
    if os.path.exists('suscripciones.csv'):
        with open('suscripciones.csv', mode='r', encoding='utf-8') as archivo:
            lector = csv.DictReader(archivo)
            for fila in lector:
                try:
                    puntos_real = float(fila.get('Puntos', 0) or 0)
                except ValueError:
                    puntos_real = 0
                clientes_bd.append({
                    'Nombre': fila.get('Cliente', 'Sin Nombre'), # Leemos 'Cliente'
                    'Estado': fila.get('Estado', 'Regular'),
                    'Telefono': fila.get('Telefono', ''),
                    'Cumpleanos': fila.get('Cumpleanos', ''),
                    'Puntos': puntos_real
                })

# --- 1. NUEVA PANTALLA PRINCIPAL (DASHBOARD) ---
@app.route('/')
@login_required
def dashboard():
    # Cargamos los datos por si es la primera vez que se abre el programa
    cargar_datos_iniciales()

    # Extraemos la lista de platillos para la barra de ventas
    lista_de_platillos = list(set([receta['Platillo'] for receta in recetas_bd if receta.get('Platillo')]))

    # ✨ Conectamos el cable aquí mandando 'clientes' a dashboard.html
    return render_template('dashboard.html',
                           platillos_disponibles=lista_de_platillos,
                           clientes=clientes_bd)

# --- RUTA: ASISTENTE VIRTUAL DE TELEGRAM (WEBHOOK) ---
@app.route('/webhook_telegram', methods=['POST'])
def webhook_telegram():
    print("🤖 [TELEGRAM] ¡Webhook disparado por Telegram!")
    datos = request.get_json(silent=True, force=True)

    if not datos:
        return "OK", 200

    if 'message' in datos and 'text' in datos['message']:
        texto_recibido = datos['message']['text'].lower()
        chat_id = datos['message']['chat']['id']

        if 'faltante' in texto_recibido or 'insumo' in texto_recibido:
            print("🤖 [TELEGRAM] Comando de faltantes reconocido. Cargando base de datos...")

            try:
                cargar_datos_iniciales()
            except Exception as e:
                print("🤖 [TELEGRAM] ERROR AL CARGAR DATOS:", e)

            insumos_faltantes = []
            costo_total = 0.0

            for p in base_de_datos:
                # 🛡️ PROTECCIÓN MARKDOWN: Quitamos guiones bajos o asteriscos que rompen Telegram
                nombre_bruto = p.get('Producto') or p.get('\ufeffProducto') or 'Insumo sin nombre'
                nombre_producto = nombre_bruto.replace('_', ' ').replace('*', '')

                try:
                    raw_cantidad = p.get('Cantidad') or 0
                    cantidad = float(raw_cantidad)

                    raw_minimo = p.get('Minimo') or 5
                    minimo = float(raw_minimo)

                    raw_contenido = p.get('Contenido') or 1
                    contenido = float(raw_contenido)
                    if contenido <= 0: contenido = 1.0

                    precio_str = str(p.get('Precio') or '0').replace('$', '').replace(',', '').strip()
                    precio = float(precio_str)
                except (ValueError, TypeError):
                    continue

                if cantidad < minimo:
                    a_comprar = minimo - cantidad
                    costo = (precio / contenido) * a_comprar
                    medida = p.get('Medida', '')

                    insumos_faltantes.append(f"• {nombre_producto}: Faltan {a_comprar} {medida} (aprox ${round(costo, 2)})")
                    costo_total += costo

            # ✂️ EL TRUCO DEL INGENIERO: Cortar el mensaje si es muy largo
            if insumos_faltantes:
                mensajes_a_enviar = []
                mensaje_actual = "📋 *Lista de Insumos Faltantes de Estación 88*\n\n"

                for linea in insumos_faltantes:
                    # El límite de Telegram es 4096. Cortamos a los 3800 para estar seguros.
                    if len(mensaje_actual) + len(linea) > 3800:
                        mensajes_a_enviar.append(mensaje_actual)
                        mensaje_actual = "📋 *Continuación...*\n\n"

                    mensaje_actual += linea + "\n"

                # Al final del último bloque de texto, agregamos el total de dinero
                mensaje_actual += f"\n💰 *Inversión aproximada: ${round(costo_total, 2)}*"
                mensajes_a_enviar.append(mensaje_actual)
            else:
                mensajes_a_enviar = ["✅ Todo el inventario está al corriente. No hay insumos en números rojos."]

            print(f"🤖 [TELEGRAM] Todo calculado. Enviando en {len(mensajes_a_enviar)} partes...")
            TOKEN = os.getenv('TELEGRAM_TOKEN')
            if not TOKEN:
                return "OK", 200
            url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

            proxies_pa = {
                "http": "http://proxy.server:3128",
                "https": "http://proxy.server:3128",
            }

            # Enviamos todos los pedazos de mensaje uno por uno
            for msg in mensajes_a_enviar:
                try:
                    respuesta = requests.post(
                        url,
                        json={'chat_id': chat_id, 'text': msg, 'parse_mode': 'Markdown'},
                        proxies=proxies_pa,
                        timeout=10
                    )
                    print("🤖 [TELEGRAM] Respuesta de Telegram:", respuesta.status_code)
                    if respuesta.status_code == 400:
                        # Si vuelve a salir 400, esto nos dirá EXACTAMENTE por qué
                        print("🤖 [TELEGRAM] Detalle del error 400:", respuesta.text)
                except Exception as e:
                    print("🤖 [TELEGRAM] ERROR AL ENVIAR:", e)

    # Le respondemos 200 a Telegram para que deje de reintentar como loco
    return "OK", 200

def redondear_comercial(precio):
    # Separamos los pesos de los centavos
    parte_entera = int(precio)
    centavos = precio - parte_entera

    # Aplicamos la regla de tu mamá ☕
    if centavos >= 0.50:
        return parte_entera + 1
    else:
        return parte_entera

# --- SISTEMA DE ALERTAS TELEGRAM ---
def enviar_alerta_telegram(mensaje):
    TOKEN = os.getenv('TELEGRAM_TOKEN')
    CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

    if not TOKEN or not CHAT_ID:
        return # Si no están configuradas las variables, no intenta enviar alerta

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    datos = {'chat_id': CHAT_ID, 'text': mensaje}
    try:
        requests.post(url, data=datos, timeout=5)
    except:
        pass # Si falla el internet, que no rompa la página

def auto_cerrar_turnos_vencidos():
    """
    Cierra automáticamente cualquier turno de días anteriores que haya quedado en estado 'Abierto' (a las 11:59 PM/cambio de fecha).
    Calcula el balance exacto de ventas en efectivo y gastos de esa fecha y actualiza caja.csv.
    """
    archivo_caja = 'caja.csv'
    if not os.path.exists(archivo_caja):
        return

    fecha_hoy = obtener_fecha_hoy()
    encabezados = ['Fecha', 'Fondo_Inicial', 'Fondo_Final_Real', 'Diferencia', 'Estado']
    lineas = []
    turnos_cerrados_auto = []

    with open(archivo_caja, mode='r', encoding='utf-8') as f:
        lector = csv.DictReader(f)
        for fila in lector:
            fecha_turno = fila.get('Fecha', '')
            estado = fila.get('Estado', '')

            # Si el turno es de una fecha anterior a hoy y sigue 'Abierto':
            if fecha_turno and fecha_turno < fecha_hoy and estado == 'Abierto':
                try:
                    fondo_inicial = float(fila.get('Fondo_Inicial', 0))
                except:
                    fondo_inicial = 0.0

                ventas_efectivo = 0.0
                if os.path.exists('ventas.csv'):
                    with open('ventas.csv', mode='r', encoding='utf-8') as f_v:
                        for row in csv.reader(f_v):
                            if len(row) >= 5 and row[1] == fecha_turno and row[4] == 'Efectivo':
                                try:
                                    ventas_efectivo += float(row[2])
                                except:
                                    pass

                total_gastos = 0.0
                if os.path.exists('gastos.csv'):
                    with open('gastos.csv', mode='r', encoding='utf-8') as f_g:
                        for row in csv.DictReader(f_g):
                            if row.get('Fecha') == fecha_turno:
                                try:
                                    total_gastos += float(row.get('Monto', 0))
                                except:
                                    pass

                efectivo_esperado = fondo_inicial + ventas_efectivo - total_gastos
                fila['Fondo_Final_Real'] = efectivo_esperado
                fila['Diferencia'] = 0.0
                fila['Estado'] = 'Cerrado'
                turnos_cerrados_auto.append((fecha_turno, fondo_inicial, ventas_efectivo, total_gastos, efectivo_esperado))

            lineas.append(fila)

    if turnos_cerrados_auto:
        with open(archivo_caja, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados)
            escritor.writeheader()
            escritor.writerows(lineas)

        for fecha_t, fi, ve, tg, ee in turnos_cerrados_auto:
            try:
                enviar_alerta_telegram(
                    f"⏰ CIERRE AUTOMÁTICO DE TURNO (23:59 PM)\n\n"
                    f"📅 Fecha: {fecha_t}\n"
                    f"🏁 Fondo Inicial: ${int(fi)}\n"
                    f"📥 Ventas Efectivo: ${int(ve)}\n"
                    f"💸 Gastos Registrados: -${int(tg)}\n"
                    f"💰 Balance Final Registrado: ${int(ee)}\n"
                    f"ℹ️ El turno de la jornada anterior se cerró automáticamente."
                )
            except:
                pass

# --- 2. EL INVENTARIO AHORA TIENE SU PROPIA RUTA ---
@app.route('/inventario')
@login_required
def inventario():
    cargar_datos_iniciales()
    palabra_buscada = request.args.get('busqueda', '')

    if palabra_buscada:
        resultados = [p for p in base_de_datos if palabra_buscada.lower() in p['Producto'].lower()]
    else:
        resultados = base_de_datos

    # Ordenamos alfabéticamente
    resultados = sorted(resultados, key=lambda x: x['Producto'].lower())
    lista_de_platillos = list(set([receta['Platillo'] for receta in recetas_bd if receta.get('Platillo')]))

    # Limpiamos esta ruta (ya no necesita el print ni la variable clientes)
    return render_template('index.html',
                           total_productos=len(resultados),
                           inventario=resultados,
                           inventario_completo=base_de_datos,
                           palabra_buscada=palabra_buscada,
                           platillos_disponibles=lista_de_platillos)

# --- 3. MÓDULO PREDICTIVO: PLANES, SUSCRIPCIONES Y FIDELIDAD ---
@app.route('/suscripciones', methods=['GET', 'POST'])
@login_required
def suscripciones():
    from datetime import datetime, timedelta
    archivo_subs = 'suscripciones.csv'
    encabezados = ['Cliente', 'Plan', 'Fecha_Inicio', 'Fecha_Fin', 'Estado', 'Telefono', 'Cumpleanos', 'Puntos']

    # 1. AUTOCREACIÓN
    if not os.path.exists(archivo_subs):
        with open(archivo_subs, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.writer(f)
            escritor.writerow(encabezados)

    # 2. GUARDAR NUEVO CLIENTE O SUSCRIPTOR
    if request.method == 'POST':
        cliente = request.form.get('cliente')
        plan = request.form.get('plan')
        telefono = request.form.get('telefono', '')
        cumpleanos = request.form.get('cumpleanos', '')

        # Si es un plan semanal, hacemos tu matemática de 7 días
        if plan in ['Desayunos', 'Comidas', 'Plan Completo']:
            fecha_inicio = request.form.get('fecha_inicio')
            if not fecha_inicio: fecha_inicio = obtener_fecha_hoy()
            fecha_obj = datetime.strptime(fecha_inicio, '%Y-%m-%d')
            fecha_fin = (fecha_obj + timedelta(days=7)).strftime('%Y-%m-%d')
            estado = 'Activo'
        else:
            # Si solo es cliente regular, no tiene fechas de vencimiento
            fecha_inicio = ''
            fecha_fin = ''
            estado = 'Regular'

        lineas_actualizadas = []
        existe = False

        with open(archivo_subs, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if fila.get('Cliente', '').lower().strip() == cliente.lower().strip():
                    existe = True
                    fila['Plan'] = plan
                    fila['Fecha_Inicio'] = fecha_inicio
                    fila['Fecha_Fin'] = fecha_fin
                    fila['Estado'] = estado
                    fila['Telefono'] = telefono
                    fila['Cumpleanos'] = cumpleanos
                    # No tocamos sus Puntos si ya existía
                lineas_actualizadas.append(fila)

        if not existe:
            lineas_actualizadas.append({
                'Cliente': cliente, 'Plan': plan, 'Fecha_Inicio': fecha_inicio,
                'Fecha_Fin': fecha_fin, 'Estado': estado,
                'Telefono': telefono, 'Cumpleanos': cumpleanos, 'Puntos': 0
            })

        with open(archivo_subs, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(lineas_actualizadas)

        cargar_datos_iniciales()
        return redirect(url_for('suscripciones'))

    # 3. MODO LECTURA (GET): Calcular cupos, AUTO-EXPIRAR y contar
    else:
        lista_subs = []
        activas = 0
        hubo_cambios = False
        hoy = obtener_fecha_hoy()
        conteo_planes = {'Desayunos': 0, 'Comidas': 0, 'Plan Completo': 0}

        with open(archivo_subs, mode='r', encoding='utf-8') as f:
            lector = list(csv.DictReader(f))
            for fila in lector:
                # Llenar huecos por si el archivo era el viejito
                if 'Telefono' not in fila: fila['Telefono'] = ''
                if 'Cumpleanos' not in fila: fila['Cumpleanos'] = ''
                if 'Puntos' not in fila: fila['Puntos'] = 0

                # Tu lógica de AUTO-EXPIRACIÓN
                if fila.get('Estado') == 'Activo' and hoy > fila.get('Fecha_Fin', '9999-99-99'):
                    fila['Estado'] = 'Expirado'
                    hubo_cambios = True

                lista_subs.append(fila)

                # Tu CONTADOR DE ANALÍTICA LOCAL
                if fila.get('Estado') == 'Activo':
                    activas += 1
                    plan_actual = fila.get('Plan')
                    if plan_actual in conteo_planes:
                        conteo_planes[plan_actual] += 1

        if hubo_cambios:
            with open(archivo_subs, mode='w', encoding='utf-8', newline='') as f:
                escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
                escritor.writeheader()
                escritor.writerows(lista_subs)

        cupos_disponibles = max(0, 10 - activas)
        porcentaje_ocupacion = min(100, (activas / 10) * 100)

        return render_template('suscripciones.html',
                               suscripciones=lista_subs,
                               activas=activas,
                               disponibles=cupos_disponibles,
                               porcentaje=porcentaje_ocupacion,
                               conteo_planes=conteo_planes)

# --- RUTA: CAMBIAR ESTADO DEL PLAN MANUALMENTE (CON AUTO-RENOVACIÓN DE FECHAS) ---
@app.route('/editar_status_cliente', methods=['POST'])
@login_required
def editar_status_cliente():
    from datetime import datetime, timedelta
    cliente_nombre = request.form.get('cliente_nombre')
    nuevo_estado = request.form.get('nuevo_estado')
    archivo_subs = 'suscripciones.csv'
    encabezados = ['Cliente', 'Plan', 'Fecha_Inicio', 'Fecha_Fin', 'Estado', 'Telefono', 'Cumpleanos', 'Puntos']

    if os.path.exists(archivo_subs):
        lineas_actualizadas = []
        with open(archivo_subs, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if fila.get('Cliente', '').lower().strip() == cliente_nombre.lower().strip():
                    fila['Estado'] = nuevo_estado

                    # 🔄 SI SE REACTIVA UN PLAN SEMANAL, LE DAMOS 7 DÍAS NUEVOS DESDE HOY
                    # Esto actualiza las fechas para que el auto-expirador no lo vuelva a bloquear
                    if nuevo_estado == 'Activo' and fila.get('Plan') not in ['Cliente Regular', '']:
                        hoy_obj = obtener_ahora()
                        fila['Fecha_Inicio'] = hoy_obj.strftime('%Y-%m-%d')
                        fila['Fecha_Fin'] = (hoy_obj + timedelta(days=7)).strftime('%Y-%m-%d')

                lineas_actualizadas.append(fila)

        with open(archivo_subs, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(lineas_actualizadas)

    cargar_datos_iniciales()
    return redirect(url_for('suscripciones'))

# --- RUTA: ELIMINAR CLIENTE DEL CATÁLOGO ---
@app.route('/eliminar_cliente', methods=['POST'])
@login_required
def eliminar_cliente():
    cliente_a_borrar = request.form.get('cliente_eliminar')
    archivo_subs = 'suscripciones.csv'
    encabezados = ['Cliente', 'Plan', 'Fecha_Inicio', 'Fecha_Fin', 'Estado', 'Telefono', 'Cumpleanos', 'Puntos']

    if os.path.exists(archivo_subs):
        lineas_restantes = []
        with open(archivo_subs, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                # Si el cliente no es el que queremos borrar, lo conservamos
                if fila.get('Cliente', '').lower().strip() != cliente_a_borrar.lower().strip():
                    lineas_restantes.append(fila)

        # Volvemos a escribir el archivo sin el cliente eliminado
        with open(archivo_subs, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(lineas_restantes)

    cargar_datos_iniciales()
    return redirect(url_for('suscripciones'))

# --- RUTA: EDITAR O RESTAR PUNTOS MANUALMENTE DESDE LA TABLA ---
@app.route('/editar_puntos_cliente', methods=['POST'])
@login_required
def editar_puntos_cliente():
    cliente_nombre = request.form.get('cliente_nombre')
    try:
        nuevos_puntos = float(request.form.get('nuevos_puntos', 0.0))
    except ValueError:
        nuevos_puntos = 0.0

    archivo_subs = 'suscripciones.csv'
    encabezados = ['Cliente', 'Plan', 'Fecha_Inicio', 'Fecha_Fin', 'Estado', 'Telefono', 'Cumpleanos', 'Puntos']

    if os.path.exists(archivo_subs):
        lineas_actualizadas = []
        with open(archivo_subs, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if fila.get('Cliente', '').lower().strip() == cliente_nombre.lower().strip():
                    fila['Puntos'] = round(nuevos_puntos, 2) # Guardamos el nuevo saldo
                lineas_actualizadas.append(fila)

        with open(archivo_subs, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(lineas_actualizadas)

    cargar_datos_iniciales()
    return redirect(url_for('suscripciones'))

# --- RUTA: CARRITO DE COMPRAS, INVENTARIO Y GENERACIÓN DE TICKET ---
@app.route('/vender_platillo', methods=['POST'])
@login_required
def vender_platillo():
    global base_de_datos, recetas_bd
    cargar_datos_iniciales()

    cliente_elegido = request.form.get('cliente_venta', 'General').strip()
    if not cliente_elegido:
        cliente_elegido = 'General'

    # DETECTOR DE MESAS ABIERTAS
    recibo_existente = request.form.get('recibo_existente', '').strip()

    if recibo_existente:
        num_recibo = recibo_existente
        metodo_pago = 'Credito'
    else:
        import random
        num_recibo = f"1-{random.randint(1000, 9999)}"
        metodo_pago = request.form.get('metodo_pago', 'Efectivo')

    # ✨ ATRAPAMOS EL PORCENTAJE DE DESCUENTO Y LOS PUNTOS ✨
    try: descuento_pct = float(request.form.get('descuento_pct', 0))
    except: descuento_pct = 0.0
    motivo_descuento = request.form.get('motivo_descuento', '').strip() or "General"

    try: puntos_descontar = float(request.form.get('puntos_descontar', 0))
    except: puntos_descontar = 0.0

    lista_platillos = request.form.getlist('platillos[]')
    lista_cantidades = request.form.getlist('cantidades_venta[]')

    total_compra_bruto = 0.0
    elementos_ticket = []
    resumen_telegram = []

    fecha_venta_str = obtener_fecha_hoy()
    fecha_ticket = obtener_ahora().strftime('%d/%m/%y %H:%M')

    # 1. Guardamos los platillos normales
    with open('ventas.csv', mode='a', encoding='utf-8', newline='') as f_ventas:
        escritor_ventas = csv.writer(f_ventas)

        for i in range(len(lista_platillos)):
            platillo_actual = lista_platillos[i].strip()
            if not platillo_actual:
                continue

            try: cant_actual = int(lista_cantidades[i])
            except: cant_actual = 1

            costo_receta = 0.0
            margen_ganancia = 40.0
            insumos_a_descontar = []

            for receta in recetas_bd:
                if receta.get('Platillo') == platillo_actual:
                    insumos_a_descontar.append(receta)
                    margen_ganancia = float(receta.get('Margen', 40.0))

                    for p in base_de_datos:
                        if receta['Insumo'].lower().strip() == p['Producto'].lower().strip():
                            try:
                                precio_str = str(p.get('Precio', '0')).replace('$', '').strip()
                                precio_str = precio_str.replace('.', '').replace(',', '.') if precio_str.rfind(',') > precio_str.rfind('.') else precio_str.replace(',', '')
                                costo_receta += (float(precio_str) / max(float(p.get('Contenido', 1)), 1.0)) * float(receta['Cantidad a utilizar'])
                            except: pass

            divisor = max(1 - (margen_ganancia / 100), 0.01)
            precio_unitario = redondear_comercial(costo_receta / divisor)
            subtotal = precio_unitario * cant_actual
            total_compra_bruto += subtotal

            elementos_ticket.append({'nombre': platillo_actual, 'cantidad': cant_actual, 'precio_unitario': int(precio_unitario), 'subtotal': int(subtotal)})
            resumen_telegram.append(f"🟢 {cant_actual}x {platillo_actual} (${int(subtotal)})")

            for _ in range(cant_actual):
                escritor_ventas.writerow([platillo_actual, fecha_venta_str, int(precio_unitario), cliente_elegido, metodo_pago, num_recibo])

            for ingrediente in insumos_a_descontar:
                for producto in base_de_datos:
                    if ingrediente['Insumo'].lower().strip() == producto['Producto'].lower().strip():
                        try: producto['Cantidad'] = max(0.0, float(producto['Cantidad']) - (float(ingrediente['Cantidad a utilizar']) * cant_actual))
                        except: pass

        # ✨ MATEMÁTICA DEL DESCUENTO Y LOS PUNTOS ✨
        monto_descuento = round(total_compra_bruto * (descuento_pct / 100), 2)
        total_neto = total_compra_bruto - monto_descuento - puntos_descontar
        total_neto = max(0.0, total_neto) # Evitar saldos negativos

        # Insertar los registros negativos en ventas.csv para que el historial cuadre perfecto
        if monto_descuento > 0:
            escritor_ventas.writerow([f"Desc {int(descuento_pct)}%: {motivo_descuento}", fecha_venta_str, -int(monto_descuento), cliente_elegido, metodo_pago, num_recibo])

        if puntos_descontar > 0:
            escritor_ventas.writerow(["Pago con Puntos", fecha_venta_str, -int(puntos_descontar), cliente_elegido, metodo_pago, num_recibo])

    # 3. Guardar Inventario
    archivo_inv = 'inventario.csv'
    if os.path.exists(archivo_inv):
        with open(archivo_inv, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            encabezados = [field.strip() for field in lector.fieldnames] if lector.fieldnames else []
        if 'Minimo' not in encabezados: encabezados.append('Minimo')
        with open(archivo_inv, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
            escritor.writeheader()
            for p in base_de_datos: escritor.writerow(p)

    # 4. 🔥 SISTEMA DE PUNTOS: RESTAR USADOS Y SUMAR NUEVOS 🔥
    puntos_ganados = 0.0
    puntos_totales = 0.0

    if cliente_elegido != 'General' and os.path.exists('suscripciones.csv'):
        lineas_clientes = []
        encabezados_c = ['Cliente', 'Plan', 'Fecha_Inicio', 'Fecha_Fin', 'Estado', 'Telefono', 'Cumpleanos', 'Puntos']
        # Los puntos se ganan sobre el total NETO (después de descuentos)
        puntos_ganados = round(total_neto * 0.05, 2)

        with open('suscripciones.csv', mode='r', encoding='utf-8') as f:
            for fila in csv.DictReader(f):
                if fila.get('Cliente', '').lower().strip() == cliente_elegido.lower():
                    try: pts_actuales = float(fila.get('Puntos', 0) or 0)
                    except: pts_actuales = 0.0

                    # Matemática de la tarjeta de puntos: Saldo - Gastados + Ganados
                    puntos_totales = round(max(0.0, pts_actuales - puntos_descontar + puntos_ganados), 2)
                    fila['Puntos'] = puntos_totales
                lineas_clientes.append(fila)

        with open('suscripciones.csv', mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados_c, extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(lineas_clientes)

    # 5. ALERTAS Y RUTEO
    if monto_descuento > 0: resumen_telegram.append(f"🔴 Descuento {int(descuento_pct)}%: -${int(monto_descuento)} ({motivo_descuento})")
    if puntos_descontar > 0: resumen_telegram.append(f"🔮 Puntos Usados: -${int(puntos_descontar)}")

    lista_texto_telegram = "\n".join(resumen_telegram)

    if recibo_existente:
        texto_alerta = f"📝 ¡Cuenta {num_recibo} Modificada!\n\n{lista_texto_telegram}\n\n💰 Total Cuenta: ${int(total_neto)}\n👤 Cliente: {cliente_elegido}\n⏳ Sigue Pendiente"
        enviar_alerta_telegram(texto_alerta)
        return redirect(url_for('editar_cuenta', recibo=num_recibo))
    else:
        icono_pago = "💵" if metodo_pago == "Efectivo" else "💳" if metodo_pago == "Tarjeta" else "📱" if metodo_pago == "Transferencia" else "⏳"
        texto_alerta = f"☕ ¡Nueva Venta!\n\n{lista_texto_telegram}\n\n💰 Total Final: ${int(total_neto)}\n👤 Cliente: {cliente_elegido}\n{icono_pago} Pago vía: {metodo_pago}"
        enviar_alerta_telegram(texto_alerta)

        # Le enviamos todo el desglose al ticket
        return render_template('ticket.html',
                               num_recibo=num_recibo,
                               fecha_ticket=fecha_ticket,
                               cliente=cliente_elegido,
                               elementos=elementos_ticket,
                               total=int(total_neto),
                               puntos_ganados=puntos_ganados,
                               puntos_totales=puntos_totales,
                               metodo_pago=metodo_pago,
                               monto_descuento=int(monto_descuento),
                               descuento_pct=int(descuento_pct),
                               motivo_descuento=motivo_descuento,
                               puntos_descontar=int(puntos_descontar))

# --- NUEVAS RUTAS DE APOYO: ABRIR LA CUENTA Y BORRAR PLATILLOS ---
@app.route('/editar_cuenta/<recibo>')
@login_required
def editar_cuenta(recibo):
    cargar_datos_iniciales()
    items_cuenta = []
    total = 0.0
    cliente = 'General'

    if os.path.exists('ventas.csv'):
        with open('ventas.csv', mode='r', encoding='utf-8') as f:
            for index, fila in enumerate(list(csv.reader(f))):
                # Buscamos en todo el historial los platillos que tengan este número de recibo
                if len(fila) >= 6 and fila[5] == recibo:
                    try: precio = float(fila[2])
                    except: precio = 0.0
                    cliente = fila[3]
                    items_cuenta.append({'id_fila': index, 'platillo': fila[0], 'precio': precio})
                    total += precio

    lista_de_platillos = list(set([r['Platillo'] for r in recetas_bd if r.get('Platillo')]))
    return render_template('editar_cuenta.html', recibo=recibo, cliente=cliente, items=items_cuenta, total=total, platillos_disponibles=lista_de_platillos)

@app.route('/eliminar_de_cuenta', methods=['POST'])
@login_required
def eliminar_de_cuenta():
    global base_de_datos, recetas_bd
    cargar_datos_iniciales()

    try: id_fila = int(request.form.get('id_fila'))
    except: return redirect(url_for('historial'))
    recibo = request.form.get('recibo')

    if os.path.exists('ventas.csv'):
        with open('ventas.csv', mode='r', encoding='utf-8') as f:
            lineas = list(csv.reader(f))

        if 0 <= id_fila < len(lineas):
            fila_eliminada = lineas.pop(id_fila)
            platillo_eliminado = fila_eliminada[0]
            try: precio_eliminado = float(fila_eliminada[2])
            except: precio_eliminado = 0.0
            cliente = fila_eliminada[3]

            # 1. Regresar insumos al almacén (Cancelación limpia)
            insumos_a_regresar = [r for r in recetas_bd if r.get('Platillo') == platillo_eliminado]
            archivo_inv = 'inventario.csv'
            if os.path.exists(archivo_inv):
                with open(archivo_inv, mode='r', encoding='utf-8') as f_inv:
                    lector_inv = list(csv.DictReader(f_inv))
                for p in lector_inv:
                    for ing in insumos_a_regresar:
                        if p['Producto'].lower().strip() == ing['Insumo'].lower().strip():
                            try: p['Cantidad'] = float(p['Cantidad']) + float(ing['Cantidad a utilizar'])
                            except: pass
                with open(archivo_inv, mode='w', encoding='utf-8', newline='') as f_inv:
                    if lector_inv:
                        escritor_inv = csv.DictWriter(f_inv, fieldnames=lector_inv[0].keys(), extrasaction='ignore')
                        escritor_inv.writeheader()
                        escritor_inv.writerows(lector_inv)

            # 2. Restar puntos de fidelidad que se habían ganado
            if cliente != 'General' and os.path.exists('suscripciones.csv'):
                lineas_clientes = []
                puntos_a_restar = round(precio_eliminado * 0.05, 2)
                with open('suscripciones.csv', mode='r', encoding='utf-8') as f_subs:
                    for fila_c in csv.DictReader(f_subs):
                        if fila_c.get('Cliente', '').lower().strip() == cliente.lower().strip():
                            try: pts = float(fila_c.get('Puntos', 0))
                            except: pts = 0.0
                            fila_c['Puntos'] = max(0.0, round(pts - puntos_a_restar, 2))
                        lineas_clientes.append(fila_c)
                with open('suscripciones.csv', mode='w', encoding='utf-8', newline='') as f_subs:
                    if lineas_clientes:
                        esc_subs = csv.DictWriter(f_subs, fieldnames=lineas_clientes[0].keys(), extrasaction='ignore')
                        esc_subs.writeheader()
                        esc_subs.writerows(lineas_clientes)

            # 3. Guardar cambios en el archivo de ventas (ya sin el platillo)
            with open('ventas.csv', mode='w', encoding='utf-8', newline='') as f_ventas:
                esc_ventas = csv.writer(f_ventas)
                esc_ventas.writerows(lineas)

    return redirect(url_for('editar_cuenta', recibo=recibo))

# --- RUTA: NUEVA RECETA (CORREGIDA SIN COMAS FANTASMA) ---
@app.route('/nueva_receta', methods=['GET', 'POST'])
@login_required
def nueva_receta():
    global recetas_bd
    if request.method == 'POST':
        nuevo_platillo = request.form.get('platillo', '').strip()

        # Atrapamos el margen si lo tienes en el HTML, si no, le ponemos 40 por defecto
        try:
            margen_ganancia = float(request.form.get('margen_ganancia', 40.0))
        except ValueError:
            margen_ganancia = 40.0

        # EL TRUCO: .getlist() atrapa todas las cajas de texto de un jalón
        lista_insumos = request.form.getlist('insumos[]')
        lista_cantidades = request.form.getlist('cantidades[]')

        # ✨ NUESTRO CANDADO: Solo 4 columnas, cero fantasmas ✨
        encabezados_oficiales = ['Platillo', 'Insumo', 'Cantidad a utilizar', 'Margen']

        with open('recetas.csv', mode='a', encoding='utf-8', newline='') as archivo:
            # Usamos DictWriter para ser súper estrictos con las columnas
            escritor = csv.DictWriter(archivo, fieldnames=encabezados_oficiales, extrasaction='ignore')

            # Recorremos la lista de todos los ingredientes que escribió
            for i in range(len(lista_insumos)):
                insumo_actual = lista_insumos[i].strip()

                # Si no dejó la cajita vacía Y no es un número fantasma suelto
                if insumo_actual != '' and not insumo_actual.isdigit():
                    cantidad_texto = lista_cantidades[i]
                    try:
                        cantidad_num = float(cantidad_texto.replace(',', '.'))
                    except ValueError:
                        cantidad_num = 0.0

                    if cantidad_num > 0:
                        # 1. Guardamos en la memoria RAM (Actualizado a 4 columnas)
                        recetas_bd.append({
                            'Platillo': nuevo_platillo,
                            'Insumo': insumo_actual,
                            'Cantidad a utilizar': cantidad_num,
                            'Margen': margen_ganancia
                        })

                        # 2. Guardamos en el Excel estrictamente (Adiós '', '', '', '')
                        escritor.writerow({
                            'Platillo': nuevo_platillo,
                            'Insumo': insumo_actual,
                            'Cantidad a utilizar': cantidad_num,
                            'Margen': margen_ganancia
                        })

        cargar_datos_iniciales() # Refrescamos por seguridad
        return redirect(url_for('recetas'))

    else:
        # Esto se ejecuta cuando abres la página por primera vez
        lista_de_platillos = list(set([receta['Platillo'] for receta in recetas_bd if receta.get('Platillo')]))
        return render_template('nueva_receta.html', platillos_disponibles=lista_de_platillos, inventario=base_de_datos)

# --- NUEVA RUTA: ELIMINAR RECETA COMPLETA ---
@app.route('/eliminar_receta', methods=['POST'])
@login_required
def eliminar_receta():
    global recetas_bd
    platillo_a_borrar = request.form.get('platillo_eliminar')

    # 1. Borramos de la memoria rápida (RAM)
    recetas_bd = [receta for receta in recetas_bd if receta.get('Platillo') != platillo_a_borrar]

    # 2. Borramos del archivo físico
    # Primero leemos absolutamente todas las líneas del CSV
    with open('recetas.csv', mode='r', encoding='utf-8') as f:
        lineas = f.readlines()

    # Ahora volvemos a abrir en modo 'w' (Write = Sobreescribir)
    with open('recetas.csv', mode='w', encoding='utf-8') as f:
        for linea in lineas:
            # Separamos la línea por comas para saber cuál es la primera columna (el nombre)
            columnas = linea.split(',')
            # Si el nombre del platillo NO es el que queremos borrar, lo escribimos de vuelta
            if columnas[0] != platillo_a_borrar:
                f.write(linea)

    return redirect(url_for('recetas'))

# --- RUTA: MOSTRAR FORMULARIO Y AGREGAR NUEVO INSUMO ---
@app.route('/nuevo_insumo', methods=['GET', 'POST'])
@login_required
def nuevo_insumo():
    global base_de_datos
    if request.method == 'POST':
        nuevo_nombre = request.form.get('producto')
        nueva_medida = request.form.get('medida')
        nueva_presentacion = request.form.get('presentacion')
        precio_limpio = request.form.get('precio', '0')
        nuevo_precio = f"${precio_limpio}"
        nuevo_contenido = request.form.get('contenido', 1)
        nueva_cantidad = request.form.get('cantidad', 0)
        nuevo_minimo = request.form.get('minimo', 5) # 👇 Atrapamos el mínimo

        archivo_inv = 'inventario.csv'
        # Añadimos Minimo a los encabezados obligatorios
        encabezados = ['Producto', 'Precio', 'Contenido', 'Medida', 'Cantidad', 'Presentación', 'Minimo']

        if os.path.exists(archivo_inv):
            with open(archivo_inv, mode='r', encoding='utf-8') as f:
                lector = csv.DictReader(f)
                if lector.fieldnames:
                    encabezados = [field.strip() for field in lector.fieldnames]
                if 'Minimo' not in encabezados:
                    encabezados.append('Minimo')

        with open(archivo_inv, mode='a', encoding='utf-8', newline='') as archivo:
            escritor = csv.DictWriter(archivo, fieldnames=encabezados, extrasaction='ignore')
            escritor.writerow({
                'Producto': nuevo_nombre,
                'Precio': nuevo_precio,
                'Contenido': nuevo_contenido,
                'Medida': nueva_medida,
                'Cantidad': nueva_cantidad,
                'Presentación': nueva_presentacion,
                'Minimo': nuevo_minimo
            })

        cargar_datos_iniciales()
        return redirect(url_for('inventario'))

    cargar_datos_iniciales()
    return render_template('nuevo_insumo.html', inventario=base_de_datos)

# --- RUTA: ELIMINAR INSUMO DEL INVENTARIO ---
@app.route('/eliminar_insumo', methods=['POST'])
@login_required
def eliminar_insumo():
    # Atrapamos el nombre del producto que seleccionaste en la cajita
    producto_a_borrar = request.form.get('producto_eliminar')
    archivo_inv = 'inventario.csv'

    if os.path.exists(archivo_inv):
        lineas_restantes = []
        encabezados = []

        # 1. Leemos el archivo y guardamos todo, EXCEPTO el producto a borrar
        with open(archivo_inv, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            if lector.fieldnames:
                encabezados = [field.strip() for field in lector.fieldnames]

            for fila in lector:
                if fila.get('Producto') != producto_a_borrar:
                    lineas_restantes.append(fila)

        # 2. Volvemos a escribir el archivo limpio (ya sin el insumo)
        if encabezados:
            with open(archivo_inv, mode='w', encoding='utf-8', newline='') as f:
                escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
                escritor.writeheader()
                escritor.writerows(lineas_restantes)

    # 3. Recargamos la memoria y actualizamos la pantalla
    cargar_datos_iniciales()
    return redirect(url_for('nuevo_insumo'))

# --- 4. CENTRO DE ANALÍTICA GLOBAL Y PREDICCIONES ---
@app.route('/analiticas')
@login_required
def analiticas():
    cargar_datos_iniciales()

    valor_total = 0.0
    dinero_reinvertir = 0.0
    productos_bajos = []

    for p in base_de_datos:
        try:
            cantidad_num = float(p.get('Cantidad', 0))
        except: cantidad_num = 0.0
        try:
            contenido_num = float(p.get('Contenido', 1))
            if contenido_num <= 0: contenido_num = 1.0
        except: contenido_num = 1.0
        try:
            val_minimo = float(p.get('Minimo', 5.0))
        except: val_minimo = 5.0
        try:
            precio_str = str(p.get('Precio', '0')).replace('$', '').strip()
            if ',' in precio_str and '.' in precio_str:
                precio_str = precio_str.replace('.', '').replace(',', '.') if precio_str.rfind(',') > precio_str.rfind('.') else precio_str.replace(',', '')
            else:
                precio_str = precio_str.replace(',', '.')
            precio_num = float(precio_str)
        except: precio_num = 0.0

        precio_unitario = precio_num / contenido_num
        valor_total += precio_unitario * cantidad_num

        if cantidad_num < val_minimo:
            productos_bajos.append({
                'Producto': p.get('Producto', 'Sin Nombre'),
                'Cantidad': cantidad_num,
                'Medida': p.get('Medida', ''),
                'Minimo': val_minimo
            })
            faltante = val_minimo - cantidad_num
            dinero_reinvertir += faltante * precio_unitario

    conteo_ventas = {}
    ingresos_hoy, ingresos_semana, ingresos_mes = 0.0, 0.0, 0.0
    hoy = obtener_ahora()
    inicio_semana = hoy - timedelta(days=hoy.weekday())

    if os.path.exists('ventas.csv'):
        with open('ventas.csv', mode='r', encoding='utf-8') as f:
            lector = csv.reader(f)
            for fila in lector:
                if fila:
                    platillo = fila[0]
                    fecha_str = fila[1] if len(fila) > 1 else hoy.strftime('%Y-%m-%d')
                    try: precio_venta = float(fila[2]) if len(fila) > 2 else 0.0
                    except: precio_venta = 0.0
                    conteo_ventas[platillo] = conteo_ventas.get(platillo, 0) + 1
                    try:
                        fecha_venta = datetime.strptime(fecha_str, '%Y-%m-%d')
                        if fecha_venta.date() == hoy.date(): ingresos_hoy += precio_venta
                        if fecha_venta.date() >= inicio_semana.date(): ingresos_semana += precio_venta
                        if fecha_venta.year == hoy.year and fecha_venta.month == hoy.month: ingresos_mes += precio_venta
                    except ValueError: pass

    top_ventas = sorted(conteo_ventas.items(), key=lambda x: x[1], reverse=True)[:5]
    nombres_v = [v[0] for v in top_ventas]
    cantidades_v = [v[1] for v in top_ventas]

    activas = 0
    if os.path.exists('suscripciones.csv'):
        with open('suscripciones.csv', mode='r', encoding='utf-8') as f:
            for fila in csv.DictReader(f):
                if fila.get('Estado') == 'Activo': activas += 1

    # ✨ APLICAMOS REDONDEO SOLO A LAS VENTAS, EL INVENTARIO CONSERVA SUS DECIMALES ✨
    return render_template('analiticas.html',
                           valor_inventario=f"${valor_total:,.2f}",          # 👈 Decimales exactos restaurados
                           dinero_reinversion=f"${dinero_reinvertir:,.2f}",  # 👈 Decimales exactos restaurados
                           alertas_stock=productos_bajos,
                           desayunos_proyectados=activas * 5,
                           comidas_proyectadas=activas * 5,
                           nombres_platillos=nombres_v,
                           cantidades_platillos=cantidades_v,
                           hoy_str=f"${int(redondear_comercial(ingresos_hoy)):,}",
                           semana_str=f"${int(redondear_comercial(ingresos_semana)):,}",
                           mes_str=f"${int(redondear_comercial(ingresos_mes)):,}")

# --- RUTA: EDITAR CANTIDAD, PRECIO Y MÍNIMO DESDE LA TABLA ---
@app.route('/editar_stock', methods=['POST'])
@login_required
def editar_stock():
    global base_de_datos

    # 1. Atrapamos el nombre original con el que viene del HTML (ahora sí usamos la llave correcta)
    producto_busqueda = (request.form.get('producto_original') or request.form.get('producto_nombre') or '').strip()

    # Atrapamos si se decidió editar también el nombre del producto
    nuevo_nombre = (request.form.get('nuevo_nombre') or '').strip()

    # 2. Atrapamos los demás campos
    nueva_presentacion = (request.form.get('nueva_presentacion') or '').strip()
    nueva_medida = (request.form.get('nueva_medida') or '').strip()

    raw_cantidad = request.form.get('nueva_cantidad') or request.form.get('cantidad') or request.form.get('nuevo_stock') or '0'
    try:
        nueva_cantidad = float(raw_cantidad)
    except (ValueError, TypeError):
        nueva_cantidad = 0.0

    nuevo_precio = (request.form.get('nuevo_precio') or request.form.get('precio') or '$0.00').strip()
    if not nuevo_precio.startswith('$'):
        nuevo_precio = f"${nuevo_precio}"

    raw_minimo = request.form.get('nuevo_minimo') or request.form.get('minimo') or '5'
    try:
        nuevo_minimo = float(raw_minimo)
    except (ValueError, TypeError):
        nuevo_minimo = 5.0

    archivo_inv = 'inventario.csv'
    lineas_actualizadas = []
    encabezados = ['Producto', 'Precio', 'Contenido', 'Medida', 'Cantidad', 'Presentación', 'Minimo']
    hubo_cambio = False

    # Validamos usando producto_busqueda
    if os.path.exists(archivo_inv) and producto_busqueda:
        # LEER con utf-8-sig (para limpiar la lectura)
        with open(archivo_inv, mode='r', encoding='utf-8-sig') as f:
            lector = csv.DictReader(f)
            if lector.fieldnames:
                encabezados = [field.strip() for field in lector.fieldnames if field]
            if 'Minimo' not in encabezados:
                encabezados.append('Minimo')

            for fila in lector:
                prod_en_csv = (fila.get('Producto') or '').strip()

                if prod_en_csv.lower() == producto_busqueda.lower():
                    if nuevo_nombre:
                        fila['Producto'] = nuevo_nombre
                    fila['Cantidad'] = nueva_cantidad
                    fila['Precio'] = nuevo_precio
                    fila['Minimo'] = nuevo_minimo
                    if nueva_presentacion:
                        fila['Presentación'] = nueva_presentacion
                    if nueva_medida:
                        fila['Medida'] = nueva_medida

                    hubo_cambio = True

                lineas_actualizadas.append(fila)

        if hubo_cambio:
            # 👇 AQUI ESTABA EL ERROR: GUARDAR con utf-8 normal para curar el archivo
            with open(archivo_inv, mode='w', encoding='utf-8', newline='') as f:
                escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
                escritor.writeheader()
                escritor.writerows(lineas_actualizadas)
            print(f"ÉXITO: Se actualizó {producto_busqueda}")

    cargar_datos_iniciales()
    return redirect(url_for('inventario'))

# --- RUTA: LIBRO DE RECETAS Y CÁLCULO DE COSTOS ---
@app.route('/recetas')
@login_required
def recetas():
    cargar_datos_iniciales()

    recetas_agrupadas = {}
    for r in recetas_bd:
        platillo = r.get('Platillo')
        insumo_nombre = r.get('Insumo', '')
        cantidad_uso = r.get('Cantidad a utilizar', 0)
        margen_platillo = r.get('Margen', 40.0)

        # Cruzamos con el inventario para calcular el costo en pesos
        medida_insumo = ""
        costo_insumo = 0.0

        for p in base_de_datos:
            if p['Producto'].lower().strip() == insumo_nombre.lower().strip():
                medida_insumo = p['Medida']
                try:
                    precio_str = str(p.get('Precio', '0')).replace('$', '').strip()
                    # Lector a prueba de comas
                    if ',' in precio_str and '.' in precio_str:
                        precio_str = precio_str.replace('.', '').replace(',', '.') if precio_str.rfind(',') > precio_str.rfind('.') else precio_str.replace(',', '')
                    else:
                        precio_str = precio_str.replace(',', '.')

                    precio_num = float(precio_str)
                    contenido_num = float(p.get('Contenido', 1))
                    if contenido_num <= 0: contenido_num = 1.0

                    # Regla de 3: (Precio / Contenido) * Lo que pide la receta
                    costo_insumo = (precio_num / contenido_num) * float(cantidad_uso)
                except:
                    costo_insumo = 0.0
                break

        if platillo:
            if platillo not in recetas_agrupadas:
                recetas_agrupadas[platillo] = {
                    'insumos': [],
                    'costo_total': 0.0,
                    'margen': float(margen_platillo), # Aseguramos que el margen sea un número
                    'precio_sugerido': 0.0
                }

            recetas_agrupadas[platillo]['insumos'].append({
                'Insumo': insumo_nombre,
                'Cantidad': cantidad_uso,
                'Medida': medida_insumo,
                'Costo_str': f"${costo_insumo:,.2f}"
            })
            recetas_agrupadas[platillo]['costo_total'] += costo_insumo

    # Matemáticas de Finanzas: Aplicamos la Fórmula 2 a todos los platillos
    for platillo, data in recetas_agrupadas.items():
        divisor = 1 - (data['margen'] / 100)
        if divisor <= 0: divisor = 0.01 # Evita errores si le ponen 100% de margen

        precio_sugerido_bruto = data['costo_total'] / divisor

        # ✨ AQUÍ APLICAMOS LA FUNCIÓN DE REDONDEO COMERCIAL ✨
        data['precio_sugerido'] = redondear_comercial(precio_sugerido_bruto)

        # Formateamos bonito con signos de pesos para que el HTML no sufra
        data['costo_total_str'] = f"${data['costo_total']:,.2f}"

        # Formateamos el precio sugerido como un número entero limpio (sin decimales)
        data['precio_sugerido_str'] = f"${int(data['precio_sugerido']):,}"

    lista_platillos = list(recetas_agrupadas.keys())
    return render_template('recetas.html', recetas=recetas_agrupadas, platillos_disponibles=lista_platillos)

# ====================================================================
# --- RUTA TODO TERRENO: ABRIR Y GUARDAR EDICIÓN DE RECETAS ---
# ====================================================================
@app.route('/editar_receta', methods=['GET', 'POST'])
@app.route('/editar_receta/<platillo>', methods=['GET', 'POST'])
@login_required
def manejar_edicion_receta(platillo=None):
    global recetas_bd

    # 1. ¿ES LA ORDEN DE GUARDAR?
    if request.method == 'POST' and 'nombre_platillo' in request.form:
        platillo_original = request.form.get('platillo_original', '').strip()
        nombre_platillo = request.form.get('nombre_platillo', '').strip()

        try:
            margen_ganancia = float(request.form.get('margen_ganancia', 40.0))
        except ValueError:
            margen_ganancia = 40.0

        lista_insumos = request.form.getlist('insumos[]')
        lista_cantidades = request.form.getlist('cantidades[]')

        archivo_recetas = 'recetas.csv'
        lineas_restantes = []

        # ✨ LA SOLUCIÓN: Candado de 4 columnas oficiales. Cero comas fantasma. ✨
        encabezados_oficiales = ['Platillo', 'Insumo', 'Cantidad a utilizar', 'Margen']

        if os.path.exists(archivo_recetas):
            with open(archivo_recetas, mode='r', encoding='utf-8') as f:
                lector = csv.DictReader(f)

                for fila in lector:
                    if fila.get('Platillo', '').strip() != platillo_original:
                        # Aspiradora: Limpiamos las recetas viejas que tenían comas de más o sin margen
                        margen_limpio = fila.get('Margen', '')
                        if not margen_limpio: # Si por error está vacío (como en el Glow cheese)
                            margen_limpio = 40.0

                        fila_limpia = {
                            'Platillo': fila.get('Platillo', ''),
                            'Insumo': fila.get('Insumo', ''),
                            'Cantidad a utilizar': fila.get('Cantidad a utilizar', ''),
                            'Margen': margen_limpio
                        }
                        lineas_restantes.append(fila_limpia)

        # 4. Reconstruimos la receta editada
        for i in range(len(lista_insumos)):
            insumo_nom = lista_insumos[i].strip()
            if not insumo_nom or insumo_nom.isdigit():
                continue
            try:
                cant = float(lista_cantidades[i])
            except (ValueError, IndexError):
                cant = 0.0
            if cant > 0:
                nueva_fila = {
                    'Platillo': nombre_platillo,
                    'Insumo': insumo_nom,
                    'Cantidad a utilizar': cant,
                    'Margen': margen_ganancia
                }
                lineas_restantes.append(nueva_fila)

        # 5. Guardamos estrictamente usando los encabezados oficiales
        with open(archivo_recetas, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados_oficiales, extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(lineas_restantes)

        cargar_datos_iniciales()
        return redirect(url_for('recetas'))

    # ------------------------------------------------------------------
    # 2. ¿ES LA ORDEN DE ABRIR LA PANTALLA?
    cargar_datos_iniciales()

    if not platillo:
        if request.method == 'POST':
            platillo = request.form.get('platillo') or request.form.get('platillo_original')
        else:
            platillo = request.args.get('platillo')

    ingredientes_actuales = []
    margen_actual = 40.0

    if platillo:
        for r in recetas_bd:
            if r.get('Platillo') == platillo:
                ingredientes_actuales.append(r)
                try:
                    margen_actual = float(r.get('Margen', 40.0))
                except ValueError:
                    pass

    return render_template('editar_receta.html',
                           platillo=platillo,
                           margen=margen_actual,
                           ingredientes=ingredientes_actuales,
                           inventario_completo=base_de_datos)

# --- RUTA: HISTORIAL DE VENTAS Y CUENTAS PENDIENTES ---
@app.route('/historial')
@login_required
def historial():
    ventas_agrupadas = {}
    totales = {'Efectivo': 0.0, 'Tarjeta': 0.0, 'Transferencia': 0.0, 'Credito': 0.0}

    if os.path.exists('ventas.csv'):
        with open('ventas.csv', mode='r', encoding='utf-8') as f:
            lector = list(csv.reader(f))
            for index, fila in enumerate(lector):
                if len(fila) >= 4:
                    platillo = fila[0]
                    fecha = fila[1]
                    try:
                        precio = float(fila[2])
                    except ValueError:
                        precio = 0.0
                    cliente = fila[3]
                    metodo = fila[4] if len(fila) >= 5 else 'Efectivo'

                    # ✨ EL TRUCO: Usamos el Número de Recibo (6ta columna) para agrupar.
                    # Si la venta es vieja y no tiene recibo, usamos fecha+cliente para que no se borre.
                    recibo = fila[5] if len(fila) >= 6 else f"Antiguo-{fecha}-{cliente}"

                    if metodo in totales:
                        totales[metodo] += precio
                    else:
                        totales['Efectivo'] += precio

                    # Si el recibo no existe en nuestra lista agrupada, lo creamos
                    if recibo not in ventas_agrupadas:
                        ventas_agrupadas[recibo] = {
                            'id_fila': index,
                            'fecha': fecha,
                            'cliente': cliente,
                            'platillos': [platillo],
                            'precio_total': precio,
                            'metodo': metodo,
                            'es_antiguo': len(fila) < 6
                        }
                    # Si ya existe, le sumamos el platillo y el dinero
                    else:
                        ventas_agrupadas[recibo]['platillos'].append(platillo)
                        ventas_agrupadas[recibo]['precio_total'] += precio

    ventas_lista = []
    for recibo, data in ventas_agrupadas.items():
        # Hacemos un resumen bonito de platillos (ej: "2x Café, 1x Chapata")
        from collections import Counter
        conteo = Counter(data['platillos'])
        resumen_platillos = ", ".join([f"{cant}x {nombre}" for nombre, cant in conteo.items()])

        ventas_lista.append({
            'id': data['id_fila'],
            'recibo': recibo if not data['es_antiguo'] else 'S/N',
            'fecha': data['fecha'],
            'cliente': data['cliente'],
            'platillo': resumen_platillos,
            'precio': data['precio_total'],
            'metodo': data['metodo'],
            'agrupador': recibo
        })

    ventas_lista.reverse()
    return render_template('historial.html', ventas=ventas_lista, totales=totales)

# --- NUEVA RUTA: LIQUIDAR UNA CUENTA PENDIENTE MASIVA ---
@app.route('/pagar_credito', methods=['POST'])
@login_required
def pagar_credito():
    agrupador = request.form.get('agrupador', '')
    nuevo_metodo = request.form.get('nuevo_metodo', 'Efectivo')

    if os.path.exists('ventas.csv'):
        with open('ventas.csv', mode='r', encoding='utf-8') as f:
            lineas = list(csv.reader(f))

        # Modificamos TODOS los platillos que tengan ese mismo número de recibo
        for fila in lineas:
            if len(fila) >= 4:
                fecha = fila[1]
                cliente = fila[3]
                recibo_actual = fila[5] if len(fila) >= 6 else f"Antiguo-{fecha}-{cliente}"

                if recibo_actual == agrupador:
                    if len(fila) >= 5:
                        fila[4] = nuevo_metodo
                    else:
                        fila.append(nuevo_metodo)

        with open('ventas.csv', mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.writer(f)
            escritor.writerows(lineas)

    return redirect(url_for('historial'))

# --- NUEVA RUTA: REIMPRIMIR UN TICKET EXACTO ---
@app.route('/reimprimir_ticket/<int:id_fila>')
@login_required
def reimprimir_ticket(id_fila):
    if not os.path.exists('ventas.csv'):
        return redirect(url_for('historial'))

    with open('ventas.csv', mode='r', encoding='utf-8') as f:
        lineas = list(csv.reader(f))

    if id_fila < 0 or id_fila >= len(lineas):
        return redirect(url_for('historial'))

    fila_referencia = lineas[id_fila]
    if len(fila_referencia) < 4:
        return redirect(url_for('historial'))

    fecha_ref = fila_referencia[1]
    cliente_ref = fila_referencia[3]
    metodo_ref = fila_referencia[4] if len(fila_referencia) >= 5 else 'Efectivo'
    recibo_ref = fila_referencia[5] if len(fila_referencia) >= 6 else None

    elementos_agrupados = {}
    total_compra = 0.0

    for fila in lineas:
        pertenece_al_ticket = False
        # Si es un ticket nuevo, lo agrupamos por el número de recibo exacto
        if recibo_ref and len(fila) >= 6:
            if fila[5] == recibo_ref:
                pertenece_al_ticket = True
        # Si es un ticket viejo, intentamos rescatarlo por fecha y cliente
        else:
            if len(fila) >= 4 and fila[1] == fecha_ref and fila[3] == cliente_ref and (len(fila) < 6):
                pertenece_al_ticket = True

        if pertenece_al_ticket:
            platillo = fila[0]
            try:
                precio = float(fila[2])
            except ValueError:
                precio = 0.0

            if platillo in elementos_agrupados:
                elementos_agrupados[platillo]['cantidad'] += 1
                elementos_agrupados[platillo]['subtotal'] += int(precio)
            else:
                elementos_agrupados[platillo] = {
                    'nombre': platillo,
                    'cantidad': 1,
                    'precio_unitario': int(precio),
                    'subtotal': int(precio)
                }
            total_compra += precio

    elementos_ticket = list(elementos_agrupados.values())
    num_recibo_final = recibo_ref if recibo_ref else f"R-{id_fila}"

    return render_template('ticket.html',
                           num_recibo=num_recibo_final,
                           fecha_ticket=fecha_ref,
                           cliente=cliente_ref,
                           elementos=elementos_ticket,
                           total=int(total_compra),
                           puntos_ganados=0,
                           puntos_totales="N/A",
                           metodo_pago=metodo_ref)

# =====================================================================
# --- RUTAS DE FASE 1: CORTE DE CAJA, GASTOS Y TURNOS (COMPLETAS) ---
# =====================================================================

@app.route('/caja')
@login_required
def modulo_caja():
    auto_cerrar_turnos_vencidos()
    archivo_caja = 'caja.csv'
    fecha_hoy = obtener_fecha_hoy()

    # 1. Verificar el turno de hoy
    turno_hoy = None
    if os.path.exists(archivo_caja):
        with open(archivo_caja, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if fila.get('Fecha') == fecha_hoy:
                    turno_hoy = fila
                    break

    estado_turno = turno_hoy.get('Estado', 'Sin_Abrir') if turno_hoy else 'Sin_Abrir'
    fondo_inicial = float(turno_hoy.get('Fondo_Inicial', 0)) if turno_hoy else 0.0

    # 2. Desglose en caliente de las ventas
    desglose_ventas = {'Efectivo': 0.0, 'Tarjeta': 0.0, 'Transferencia': 0.0, 'Credito': 0.0}
    if os.path.exists('ventas.csv'):
        with open('ventas.csv', mode='r', encoding='utf-8') as f:
            lector = csv.reader(f)
            for fila in lector:
                if len(fila) >= 5 and fila[1] == fecha_hoy:
                    metodo = fila[4]
                    try: monto = float(fila[2])
                    except: monto = 0.0
                    if metodo in desglose_ventas:
                        desglose_ventas[metodo] += monto

    # 3. Leer la bitácora de gastos y RASTREAR SU ID (Esto causaba el 404)
    gastos_hoy = []
    total_gastos = 0.0
    if os.path.exists('gastos.csv'):
        with open('gastos.csv', mode='r', encoding='utf-8') as f:
            lineas = list(csv.reader(f))
            for index, fila in enumerate(lineas):
                if index == 0: continue # Saltamos encabezados
                if len(fila) >= 3 and fila[0] == fecha_hoy:
                    gastos_hoy.append({
                        'id_fila': index,  # <-- Aquí está la magia para que no dé 404
                        'Concepto': fila[1],
                        'Monto': fila[2]
                    })
                    try: total_gastos += float(fila[2])
                    except: pass

    # 4. Matemáticas de Auditoría
    total_ventas = sum(desglose_ventas.values())
    efectivo_esperado = fondo_inicial + desglose_ventas['Efectivo'] - total_gastos

    fondo_final_real = 0.0
    diferencia = 0.0
    if estado_turno == 'Cerrado':
        try: fondo_final_real = float(turno_hoy.get('Fondo_Final_Real', 0))
        except: fondo_final_real = 0.0
        try: diferencia = float(turno_hoy.get('Diferencia', 0))
        except: diferencia = 0.0

    return render_template('caja.html', estado_turno=estado_turno, fondo_inicial=fondo_inicial, desglose_ventas=desglose_ventas, total_ventas=total_ventas, gastos=gastos_hoy, total_gastos=total_gastos, efectivo_esperado=efectivo_esperado, fondo_final_real=fondo_final_real, diferencia=diferencia, fecha=fecha_hoy)

@app.route('/eliminar_gasto/<int:id_fila>', methods=['POST'])
@login_required
def eliminar_gasto(id_fila):
    archivo_gastos = 'gastos.csv'
    if os.path.exists(archivo_gastos):
        with open(archivo_gastos, mode='r', encoding='utf-8') as f:
            lineas = list(csv.reader(f))

        # Validamos que el ID exista para no romper el archivo
        if 0 < id_fila < len(lineas):
            gasto_eliminado = lineas.pop(id_fila)
            concepto = gasto_eliminado[1] if len(gasto_eliminado) > 1 else 'Desconocido'
            monto = gasto_eliminado[2] if len(gasto_eliminado) > 2 else '0'

            with open(archivo_gastos, mode='w', encoding='utf-8', newline='') as f:
                escritor = csv.writer(f)
                escritor.writerows(lineas)

            enviar_alerta_telegram(f"❌ Retiro Cancelado\n\nSe eliminó el gasto de: {concepto}\nEl monto de +${monto} ha regresado a la caja.")

    return redirect(url_for('modulo_caja'))

@app.route('/abrir_turno', methods=['POST'])
@login_required
def abrir_turno():
    try: fondo = float(request.form.get('fondo_inicial', 0))
    except: fondo = 0.0
    fecha_hoy = obtener_fecha_hoy()
    archivo_caja = 'caja.csv'
    encabezados = ['Fecha', 'Fondo_Inicial', 'Fondo_Final_Real', 'Diferencia', 'Estado']

    lineas = []
    existe = False
    if os.path.exists(archivo_caja):
        with open(archivo_caja, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if fila.get('Fecha') == fecha_hoy:
                    fila['Fondo_Inicial'] = fondo
                    fila['Estado'] = 'Abierto'
                    existe = True
                lineas.append(fila)
    if not existe:
        lineas.append({'Fecha': fecha_hoy, 'Fondo_Inicial': fondo, 'Fondo_Final_Real': 0.0, 'Diferencia': 0.0, 'Estado': 'Abierto'})

    with open(archivo_caja, mode='w', encoding='utf-8', newline='') as f:
        escritor = csv.DictWriter(f, fieldnames=encabezados)
        escritor.writeheader()
        escritor.writerows(lineas)

    enviar_alerta_telegram(f"🏪 ¡Turno Abierto!\n\n📅 Fecha: {fecha_hoy}\n💵 Fondo base inicial: ${int(fondo)}")
    return redirect(url_for('modulo_caja'))

@app.route('/registrar_gasto', methods=['POST'])
@login_required
def registrar_gasto():
    concepto = request.form.get('concepto', 'Gasto General').strip()
    try: monto = float(request.form.get('monto', 0))
    except: monto = 0.0
    fecha_hoy = obtener_fecha_hoy()
    archivo_gastos = 'gastos.csv'

    encabezados = ['Fecha', 'Concepto', 'Monto']
    if not os.path.exists(archivo_gastos):
        with open(archivo_gastos, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados)
            escritor.writeheader()

    with open(archivo_gastos, mode='a', encoding='utf-8', newline='') as f:
        escritor = csv.DictWriter(f, fieldnames=encabezados)
        escritor.writerow({'Fecha': fecha_hoy, 'Concepto': concepto, 'Monto': monto})

    enviar_alerta_telegram(f"💸 Retiro de Caja (Gasto)\n\nConcepto: {concepto}\nMonto: -${int(monto)}")
    return redirect(url_for('modulo_caja'))

@app.route('/cerrar_turno', methods=['POST'])
@login_required
def cerrar_turno():
    try: efectivo_real = float(request.form.get('efectivo_real', 0))
    except: efectivo_real = 0.0
    fecha_hoy = obtener_fecha_hoy()
    archivo_caja = 'caja.csv'
    encabezados = ['Fecha', 'Fondo_Inicial', 'Fondo_Final_Real', 'Diferencia', 'Estado']

    lineas = []
    turno_hoy = None
    if os.path.exists(archivo_caja):
        with open(archivo_caja, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if fila.get('Fecha') == fecha_hoy: turno_hoy = fila
                else: lineas.append(fila)

    fondo_inicial = float(turno_hoy.get('Fondo_Inicial', 0)) if turno_hoy else 0.0
    ventas_efectivo = 0.0
    if os.path.exists('ventas.csv'):
        with open('ventas.csv', mode='r', encoding='utf-8') as f:
            lector = csv.reader(f)
            for fila in lector:
                if len(fila) >= 5 and fila[1] == fecha_hoy and fila[4] == 'Efectivo':
                    try: ventas_efectivo += float(fila[2])
                    except: pass

    total_gastos = 0.0
    if os.path.exists('gastos.csv'):
        with open('gastos.csv', mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if fila.get('Fecha') == fecha_hoy:
                    try: total_gastos += float(fila.get('Monto', 0))
                    except: pass

    efectivo_esperado = fondo_inicial + ventas_efectivo - total_gastos
    diferencia = efectivo_real - efectivo_esperado

    lineas.append({'Fecha': fecha_hoy, 'Fondo_Inicial': fondo_inicial, 'Fondo_Final_Real': efectivo_real, 'Diferencia': diferencia, 'Estado': 'Cerrado'})
    with open(archivo_caja, mode='w', encoding='utf-8', newline='') as f:
        escritor = csv.DictWriter(f, fieldnames=encabezados)
        escritor.writeheader()
        escritor.writerows(lineas)

    status_msg = "✅ Todo Cuadrado" if diferencia == 0 else f"⚠️ Faltante: -${abs(diferencia)}" if diferencia < 0 else f"⚠️ Sobrante: +${diferencia}"
    enviar_alerta_telegram(f"🔒 ¡TURNO CERRADO TRAS COMPROBACIÓN!\n\n🏁 Fondo Inicial: ${int(fondo_inicial)}\n📥 Ventas Efectivo: ${int(ventas_efectivo)}\n💸 Gastos Caja: -${int(total_gastos)}\n💰 Balance Esperado: ${int(efectivo_esperado)}\n💵 Contado en Mano: ${int(efectivo_real)}\n📊 Auditoría: {status_msg}")
    return redirect(url_for('modulo_caja'))

@app.route('/reabrir_turno', methods=['POST'])
@login_required
def reabrir_turno():
    fecha_hoy = obtener_fecha_hoy()
    archivo_caja = 'caja.csv'
    encabezados = ['Fecha', 'Fondo_Inicial', 'Fondo_Final_Real', 'Diferencia', 'Estado']

    if os.path.exists(archivo_caja):
        lineas = []
        with open(archivo_caja, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if fila.get('Fecha') == fecha_hoy and fila.get('Estado') == 'Cerrado':
                    fila['Estado'] = 'Abierto'
                    fila['Fondo_Final_Real'] = 0.0
                    fila['Diferencia'] = 0.0
                lineas.append(fila)

        with open(archivo_caja, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados)
            escritor.writeheader()
            escritor.writerows(lineas)

        enviar_alerta_telegram(f"🔓 ¡Turno Reabierto!\n\nSe ha reabierto la caja del día {fecha_hoy} para continuar operaciones.")

    return redirect(url_for('modulo_caja'))

if __name__ == '__main__':
    app.run(debug=True)