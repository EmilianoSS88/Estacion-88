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
# No borrar
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

# DASHBOARD
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

# ASISTENTE VIRTUAL DE TELEGRAM
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

# INVENTARIO 
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

# ELIMINAR CLIENTE DEL CATÁLOGO 
@app.route('/eliminar_cliente', methods=['POST'])
@app.route('/eliminar_cliente/<path:cliente_nombre>', methods=['POST'])
@login_required
def eliminar_cliente(cliente_nombre=None):
    cliente_a_borrar = cliente_nombre or request.form.get('cliente_eliminar') or request.form.get('cliente_nombre')
    if not cliente_a_borrar:
        return redirect(url_for('suscripciones'))

    cliente_a_borrar = cliente_a_borrar.strip()
    archivo_subs = 'suscripciones.csv'
    encabezados = ['Cliente', 'Plan', 'Fecha_Inicio', 'Fecha_Fin', 'Estado', 'Telefono', 'Cumpleanos', 'Puntos']

    if os.path.exists(archivo_subs):
        lineas_restantes = []
        with open(archivo_subs, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                # Si el cliente no es el que queremos borrar, lo conservamos
                if fila.get('Cliente', '').lower().strip() != cliente_a_borrar.lower():
                    lineas_restantes.append(fila)

        # Volvemos a escribir el archivo sin el cliente eliminado
        with open(archivo_subs, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(lineas_restantes)

    cargar_datos_iniciales()
    return redirect(url_for('suscripciones'))

# --- RUTA: EDITAR DATOS DEL CLIENTE (NOMBRE, TELÉFONO, CUMPLEAÑOS, PLAN, PUNTOS) ---
@app.route('/editar_cliente', methods=['POST'])
@login_required
def editar_cliente():
    cliente_original = request.form.get('cliente_original', '').strip()
    nuevo_nombre = request.form.get('nuevo_nombre', '').strip()
    nuevo_telefono = request.form.get('nuevo_telefono', '').strip()
    nuevo_cumpleanos = request.form.get('nuevo_cumpleanos', '').strip()
    nuevo_plan = request.form.get('nuevo_plan', '').strip()
    try:
        nuevos_puntos = float(request.form.get('nuevos_puntos', 0.0))
    except (ValueError, TypeError):
        nuevos_puntos = 0.0

    if not cliente_original or not nuevo_nombre:
        return redirect(url_for('suscripciones'))

    archivo_subs = 'suscripciones.csv'
    encabezados = ['Cliente', 'Plan', 'Fecha_Inicio', 'Fecha_Fin', 'Estado', 'Telefono', 'Cumpleanos', 'Puntos']

    if os.path.exists(archivo_subs):
        lineas_actualizadas = []
        with open(archivo_subs, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if fila.get('Cliente', '').lower().strip() == cliente_original.lower():
                    plan_anterior = fila.get('Plan', 'Cliente Regular')
                    fila['Cliente'] = nuevo_nombre
                    fila['Telefono'] = nuevo_telefono
                    fila['Cumpleanos'] = nuevo_cumpleanos
                    fila['Puntos'] = round(nuevos_puntos, 2)
                    if nuevo_plan:
                        fila['Plan'] = nuevo_plan
                        if nuevo_plan in ['Desayunos', 'Comidas', 'Plan Completo']:
                            if plan_anterior not in ['Desayunos', 'Comidas', 'Plan Completo'] or fila.get('Estado') == 'Regular' or not fila.get('Fecha_Fin'):
                                hoy_obj = obtener_ahora()
                                fila['Fecha_Inicio'] = hoy_obj.strftime('%Y-%m-%d')
                                fila['Fecha_Fin'] = (hoy_obj + timedelta(days=7)).strftime('%Y-%m-%d')
                                fila['Estado'] = 'Activo'
                        elif nuevo_plan == 'Cliente Regular':
                            fila['Fecha_Inicio'] = ''
                            fila['Fecha_Fin'] = ''
                            fila['Estado'] = 'Regular'
                lineas_actualizadas.append(fila)

        with open(archivo_subs, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados, extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(lineas_actualizadas)

    # Si cambió el nombre del cliente, actualizar también en ventas.csv para mantener su historial
    if cliente_original.lower() != nuevo_nombre.lower() and os.path.exists('ventas.csv'):
        ventas_actualizadas = []
        with open('ventas.csv', mode='r', encoding='utf-8') as f_v:
            for row in csv.reader(f_v):
                if len(row) >= 4 and row[3].lower().strip() == cliente_original.lower():
                    row[3] = nuevo_nombre
                ventas_actualizadas.append(row)
        with open('ventas.csv', mode='w', encoding='utf-8', newline='') as f_v:
            writer = csv.writer(f_v)
            writer.writerows(ventas_actualizadas)

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
        recibos_usados = set()
        if os.path.exists('ventas.csv'):
            with open('ventas.csv', mode='r', encoding='utf-8') as f_rec:
                for fila_r in csv.reader(f_rec):
                    if len(fila_r) >= 6:
                        recibos_usados.add(fila_r[5].strip())
        num_recibo = f"1-{random.randint(1000, 9999)}"
        while num_recibo in recibos_usados:
            num_recibo = f"1-{random.randint(1000, 9999)}"
        metodo_pago = request.form.get('metodo_pago', 'Efectivo')

    # ✨ ATRAPAMOS EL PORCENTAJE DE DESCUENTO Y LOS PUNTOS ✨
    try: descuento_pct = max(0.0, min(100.0, float(request.form.get('descuento_pct', 0))))
    except: descuento_pct = 0.0
    motivo_descuento = request.form.get('motivo_descuento', '').strip() or "General"

    try: puntos_descontar = max(0.0, float(request.form.get('puntos_descontar', 0)))
    except: puntos_descontar = 0.0

    # Validamos cuántos puntos tiene realmente el cliente para no descontar de más
    puntos_disponibles_cliente = 0.0
    if cliente_elegido != 'General':
        for c in clientes_bd:
            if c.get('Nombre', '').lower().strip() == cliente_elegido.lower():
                try:
                    puntos_disponibles_cliente = max(0.0, float(c.get('Puntos', 0)))
                except (ValueError, TypeError):
                    puntos_disponibles_cliente = 0.0
                break
    puntos_descontar = min(puntos_descontar, puntos_disponibles_cliente)

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

        # ✨ MATEMÁTICA DEL DESCUENTO Y LOS PUNTOS (TOPADO AL SUBTOTAL RESTANTE) ✨
        monto_descuento = round(total_compra_bruto * (descuento_pct / 100), 2)
        subtotal_tras_descuento = max(0.0, total_compra_bruto - monto_descuento)
        puntos_descontar = round(min(puntos_descontar, subtotal_tras_descuento), 2)
        total_neto = max(0.0, subtotal_tras_descuento - puntos_descontar)

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
    puntos_ganados = "N/A"
    puntos_totales = "N/A"

    if cliente_elegido != 'General' and os.path.exists('suscripciones.csv'):
        lineas_clientes = []
        encabezados_c = ['Cliente', 'Plan', 'Fecha_Inicio', 'Fecha_Fin', 'Estado', 'Telefono', 'Cumpleanos', 'Puntos']
        cliente_encontrado = False

        with open('suscripciones.csv', mode='r', encoding='utf-8') as f:
            for fila in csv.DictReader(f):
                if fila.get('Cliente', '').lower().strip() == cliente_elegido.lower():
                    cliente_encontrado = True
                    try: pts_actuales = float(fila.get('Puntos', 0) or 0)
                    except: pts_actuales = 0.0

                    # Los puntos se ganan sobre el total NETO (después de descuentos)
                    puntos_ganados = round(total_neto * 0.05, 2)
                    # Matemática de la tarjeta de puntos: Saldo - Gastados + Ganados
                    puntos_totales = round(max(0.0, pts_actuales - puntos_descontar + puntos_ganados), 2)
                    fila['Puntos'] = puntos_totales
                lineas_clientes.append(fila)

        if cliente_encontrado:
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

# --- RUTA: NUEVA RECETA (CORREGIDA SIN COMAS FANTASMA Y CON COPIA DE RECETA BASE) ---
@app.route('/nueva_receta', methods=['GET', 'POST'])
@login_required
def nueva_receta():
    global recetas_bd
    cargar_datos_iniciales()

    # Agrupamos las recetas existentes para poder usarlas como plantilla/base
    recetas_plantilla = {}
    for r in recetas_bd:
        platillo_nom = (r.get('Platillo') or '').strip()
        if not platillo_nom:
            continue
        if platillo_nom not in recetas_plantilla:
            try:
                m_val = float(r.get('Margen', 40.0))
            except (ValueError, TypeError):
                m_val = 40.0
            recetas_plantilla[platillo_nom] = {
                'margen': m_val,
                'insumos': []
            }
        insumo_nom = (r.get('Insumo') or '').strip()
        if insumo_nom and not insumo_nom.isdigit():
            recetas_plantilla[platillo_nom]['insumos'].append({
                'Insumo': insumo_nom,
                'Cantidad': r.get('Cantidad a utilizar', 0)
            })

    lista_de_platillos = sorted(list(recetas_plantilla.keys()), key=lambda x: x.lower())

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

        # 🛡️ PROTECCIÓN CONTRA NOMBRES DUPLICADOS
        nombres_existentes_lower = [p.lower().strip() for p in lista_de_platillos]
        if nuevo_platillo.lower() in nombres_existentes_lower:
            ingredientes_enviados = []
            for i in range(len(lista_insumos)):
                ins_str = lista_insumos[i].strip()
                cant_str = lista_cantidades[i] if i < len(lista_cantidades) else ''
                if ins_str:
                    ingredientes_enviados.append({'Insumo': ins_str, 'Cantidad': cant_str})

            return render_template('nueva_receta.html',
                                   platillos_disponibles=lista_de_platillos,
                                   inventario=base_de_datos,
                                   recetas_plantilla=recetas_plantilla,
                                   receta_base=request.form.get('receta_base_seleccionada', ''),
                                   nombre_sugerido=nuevo_platillo,
                                   margen_inicial=margen_ganancia,
                                   ingredientes_iniciales=ingredientes_enviados,
                                   error=f"⚠️ Ya existe una receta llamada '{nuevo_platillo}'. Por favor cámbiale el nombre para no encimar sus ingredientes.")

        # ✨ NUESTRO CANDADO: Solo 4 columnas, cero fantasmas ✨
        encabezados_oficiales = ['Platillo', 'Insumo', 'Cantidad a utilizar', 'Margen']
        archivo_existe = os.path.exists('recetas.csv')

        with open('recetas.csv', mode='a', encoding='utf-8', newline='') as archivo:
            # Usamos DictWriter para ser súper estrictos con las columnas
            escritor = csv.DictWriter(archivo, fieldnames=encabezados_oficiales, extrasaction='ignore')
            if not archivo_existe:
                escritor.writeheader()

            # Recorremos la lista de todos los ingredientes que escribió
            for i in range(len(lista_insumos)):
                insumo_actual = lista_insumos[i].strip()

                # Si no dejó la cajita vacía Y no es un número fantasma suelto
                if insumo_actual != '' and not insumo_actual.isdigit():
                    cantidad_texto = lista_cantidades[i]
                    try:
                        cantidad_num = float(str(cantidad_texto).replace(',', '.'))
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
        # Esto se ejecuta cuando abres la página por primera vez o al darle en "Copiar"
        receta_base = request.args.get('base', '').strip()
        nombre_sugerido = ''
        margen_inicial = 40.0
        ingredientes_iniciales = []

        if receta_base and receta_base in recetas_plantilla:
            nombre_sugerido = f"{receta_base} Copia"
            margen_inicial = recetas_plantilla[receta_base]['margen']
            ingredientes_iniciales = recetas_plantilla[receta_base]['insumos']

        return render_template('nueva_receta.html',
                               platillos_disponibles=lista_de_platillos,
                               inventario=base_de_datos,
                               recetas_plantilla=recetas_plantilla,
                               receta_base=receta_base,
                               nombre_sugerido=nombre_sugerido,
                               margen_inicial=margen_inicial,
                               ingredientes_iniciales=ingredientes_iniciales,
                               error=None)

# --- NUEVA RUTA: ELIMINAR RECETA COMPLETA ---
@app.route('/eliminar_receta', methods=['POST'])
@login_required
def eliminar_receta():
    global recetas_bd
    platillo_a_borrar = (request.form.get('platillo_eliminar') or '').strip()
    if not platillo_a_borrar:
        return redirect(url_for('recetas'))

    archivo_recetas = 'recetas.csv'
    encabezados_oficiales = ['Platillo', 'Insumo', 'Cantidad a utilizar', 'Margen']

    if os.path.exists(archivo_recetas):
        lineas_restantes = []
        with open(archivo_recetas, mode='r', encoding='utf-8') as f:
            lector = csv.DictReader(f)
            for fila in lector:
                if (fila.get('Platillo') or '').strip().lower() != platillo_a_borrar.lower():
                    lineas_restantes.append({
                        'Platillo': fila.get('Platillo', ''),
                        'Insumo': fila.get('Insumo', ''),
                        'Cantidad a utilizar': fila.get('Cantidad a utilizar', 0),
                        'Margen': fila.get('Margen', 40.0) or 40.0
                    })

        with open(archivo_recetas, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados_oficiales, extrasaction='ignore')
            escritor.writeheader()
            escritor.writerows(lineas_restantes)

    cargar_datos_iniciales()
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
            faltante = round(val_minimo - cantidad_num, 2)
            costo_estimado = round(faltante * precio_unitario, 2)
            porcentaje_stock = int(min(100, max(0, (cantidad_num / max(val_minimo, 1.0)) * 100)))
            productos_bajos.append({
                'Producto': p.get('Producto', 'Sin Nombre'),
                'Cantidad': round(cantidad_num, 2),
                'Medida': p.get('Medida', ''),
                'Minimo': round(val_minimo, 2),
                'Faltante': faltante,
                'Costo_Estimado': costo_estimado,
                'Costo_Estimado_Str': f"${costo_estimado:,.2f}",
                'Porcentaje': porcentaje_stock
            })
            dinero_reinvertir += costo_estimado

    # Ordenamos la lista del súper empezando por los más urgentes (menor % de stock)
    productos_bajos.sort(key=lambda x: x['Porcentaje'])

    conteo_ventas = {}
    ingresos_por_platillo = {}
    consumo_clientes = {}
    metodos_pago_mes = {'Efectivo': 0.0, 'Tarjeta': 0.0, 'Transferencia': 0.0, 'Credito': 0.0}
    total_credito_pendiente = 0.0

    ingresos_hoy, ingresos_semana, ingresos_mes = 0.0, 0.0, 0.0
    gastos_hoy, gastos_semana, gastos_mes = 0.0, 0.0, 0.0

    hoy = obtener_ahora()
    inicio_semana = hoy - timedelta(days=hoy.weekday())

    # Estructura para los últimos 7 días (Ventas vs Gastos vs Utilidad)
    nombres_dias_es = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
    fechas_7_dias = [(hoy.date() - timedelta(days=i)) for i in range(6, -1, -1)]
    mapa_ventas_7d = {f.strftime('%Y-%m-%d'): 0.0 for f in fechas_7_dias}
    mapa_gastos_7d = {f.strftime('%Y-%m-%d'): 0.0 for f in fechas_7_dias}

    if os.path.exists('ventas.csv'):
        with open('ventas.csv', mode='r', encoding='utf-8') as f:
            lector = csv.reader(f)
            for fila in lector:
                if fila:
                    platillo = fila[0].strip()
                    fecha_str = fila[1].strip() if len(fila) > 1 else hoy.strftime('%Y-%m-%d')
                    try: precio_venta = float(fila[2]) if len(fila) > 2 else 0.0
                    except: precio_venta = 0.0
                    cliente_v = fila[3].strip() if len(fila) > 3 else 'General'
                    metodo_v = fila[4].strip() if len(fila) > 4 else 'Efectivo'

                    # Solo contamos platillos reales (ignoramos filas negativas de descuentos o pagos con puntos)
                    if precio_venta >= 0 and not platillo.startswith('Desc ') and platillo != 'Pago con Puntos':
                        conteo_ventas[platillo] = conteo_ventas.get(platillo, 0) + 1
                        ingresos_por_platillo[platillo] = ingresos_por_platillo.get(platillo, 0.0) + precio_venta

                    if cliente_v and cliente_v.lower() != 'general':
                        consumo_clientes[cliente_v] = consumo_clientes.get(cliente_v, 0.0) + precio_venta

                    if metodo_v == 'Credito':
                        total_credito_pendiente += precio_venta

                    if fecha_str in mapa_ventas_7d:
                        mapa_ventas_7d[fecha_str] += precio_venta

                    try:
                        fecha_venta = datetime.strptime(fecha_str, '%Y-%m-%d')
                        if fecha_venta.date() == hoy.date():
                            ingresos_hoy += precio_venta
                        if fecha_venta.date() >= inicio_semana.date():
                            ingresos_semana += precio_venta
                        if fecha_venta.year == hoy.year and fecha_venta.month == hoy.month:
                            ingresos_mes += precio_venta
                            if metodo_v in metodos_pago_mes:
                                metodos_pago_mes[metodo_v] += precio_venta
                            else:
                                metodos_pago_mes['Efectivo'] += precio_venta
                    except ValueError:
                        pass

    if os.path.exists('gastos.csv'):
        with open('gastos.csv', mode='r', encoding='utf-8') as f_g:
            for fila_g in csv.DictReader(f_g):
                fecha_g_str = (fila_g.get('Fecha') or '').strip()
                try:
                    monto_g = float(fila_g.get('Monto') or 0.0)
                except (ValueError, TypeError):
                    monto_g = 0.0

                if fecha_g_str in mapa_gastos_7d:
                    mapa_gastos_7d[fecha_g_str] += monto_g

                try:
                    fecha_g_dt = datetime.strptime(fecha_g_str, '%Y-%m-%d')
                    if fecha_g_dt.date() == hoy.date():
                        gastos_hoy += monto_g
                    if fecha_g_dt.date() >= inicio_semana.date():
                        gastos_semana += monto_g
                    if fecha_g_dt.year == hoy.year and fecha_g_dt.month == hoy.month:
                        gastos_mes += monto_g
                except ValueError:
                    pass

    dias_7_labels = [f"{nombres_dias_es[f.weekday()]} {f.strftime('%d/%m')}" for f in fechas_7_dias]
    dias_7_ventas = [round(mapa_ventas_7d[f.strftime('%Y-%m-%d')], 2) for f in fechas_7_dias]
    dias_7_gastos = [round(mapa_gastos_7d[f.strftime('%Y-%m-%d')], 2) for f in fechas_7_dias]
    dias_7_utilidad = [round(dias_7_ventas[i] - dias_7_gastos[i], 2) for i in range(len(fechas_7_dias))]

    # Top 5 por Unidades Vendidas y Top 5 por Dinero Generado ($)
    top_ventas = sorted(conteo_ventas.items(), key=lambda x: x[1], reverse=True)[:5]
    nombres_v = [v[0] for v in top_ventas]
    cantidades_v = [v[1] for v in top_ventas]

    top_dinero = sorted(ingresos_por_platillo.items(), key=lambda x: x[1], reverse=True)[:5]
    nombres_dinero = [v[0] for v in top_dinero]
    montos_dinero = [round(v[1], 2) for v in top_dinero]

    desayunos_proyectados = 0
    comidas_proyectadas = 0
    info_clientes_subs = {}
    cumpleaneros = []

    if os.path.exists('suscripciones.csv'):
        with open('suscripciones.csv', mode='r', encoding='utf-8') as f:
            for fila in csv.DictReader(f):
                nom_c = (fila.get('Cliente') or '').strip()
                plan_cliente = (fila.get('Plan') or 'Cliente Regular').strip()
                estado_c = (fila.get('Estado') or 'Regular').strip()
                cumple_c = (fila.get('Cumpleanos') or '').strip()
                try:
                    pts_c = round(float(fila.get('Puntos') or 0), 2)
                except (ValueError, TypeError):
                    pts_c = 0.0

                if nom_c:
                    info_clientes_subs[nom_c.lower()] = {
                        'Nombre': nom_c,
                        'Plan': plan_cliente,
                        'Puntos': pts_c,
                        'Cumpleanos': cumple_c
                    }
                    if cumple_c and cumple_c != '-':
                        cumpleaneros.append({'Nombre': nom_c, 'Cumpleanos': cumple_c, 'Puntos': pts_c})

                if estado_c == 'Activo':
                    if plan_cliente == 'Desayunos':
                        desayunos_proyectados += 5
                    elif plan_cliente == 'Comidas':
                        comidas_proyectadas += 5
                    elif plan_cliente == 'Plan Completo':
                        desayunos_proyectados += 5
                        comidas_proyectadas += 5

    # Construimos el Top 5 de Mejores Clientes
    top_clientes_raw = sorted(consumo_clientes.items(), key=lambda x: x[1], reverse=True)[:5]
    top_clientes = []
    for nom_cli, total_gastado in top_clientes_raw:
        datos_extra = info_clientes_subs.get(nom_cli.lower(), {})
        top_clientes.append({
            'Nombre': datos_extra.get('Nombre', nom_cli),
            'Total': round(total_gastado, 2),
            'Total_Str': f"${int(redondear_comercial(total_gastado)):,}",
            'Puntos': datos_extra.get('Puntos', 0),
            'Plan': datos_extra.get('Plan', 'Cliente Regular')
        })

    utilidad_hoy = ingresos_hoy - gastos_hoy
    utilidad_semana = ingresos_semana - gastos_semana
    utilidad_mes = ingresos_mes - gastos_mes

    # Si en el mes actual aún no hay ventas, mostramos el acumulado general en la dona de métodos
    metodos_dona = [
        round(max(0.0, metodos_pago_mes['Efectivo']), 2),
        round(max(0.0, metodos_pago_mes['Tarjeta']), 2),
        round(max(0.0, metodos_pago_mes['Transferencia']), 2),
        round(max(0.0, metodos_pago_mes['Credito']), 2)
    ]

    return render_template('analiticas.html',
                           valor_inventario=f"${valor_total:,.2f}",
                           dinero_reinversion=f"${dinero_reinvertir:,.2f}",
                           total_credito_str=f"${total_credito_pendiente:,.2f}",
                           alertas_stock=productos_bajos,
                           desayunos_proyectados=desayunos_proyectados,
                           comidas_proyectadas=comidas_proyectadas,
                           nombres_platillos=nombres_v,
                           cantidades_platillos=cantidades_v,
                           nombres_platillos_dinero=nombres_dinero,
                           montos_platillos_dinero=montos_dinero,
                           dias_7_labels=dias_7_labels,
                           dias_7_ventas=dias_7_ventas,
                           dias_7_gastos=dias_7_gastos,
                           dias_7_utilidad=dias_7_utilidad,
                           metodos_dona=metodos_dona,
                           top_clientes=top_clientes,
                           cumpleaneros=cumpleaneros,
                           hoy_str=f"${int(redondear_comercial(ingresos_hoy)):,}",
                           gastos_hoy_str=f"${int(redondear_comercial(gastos_hoy)):,}",
                           utilidad_hoy_str=f"${int(redondear_comercial(utilidad_hoy)):,}",
                           utilidad_hoy_num=utilidad_hoy,
                           semana_str=f"${int(redondear_comercial(ingresos_semana)):,}",
                           gastos_semana_str=f"${int(redondear_comercial(gastos_semana)):,}",
                           utilidad_semana_str=f"${int(redondear_comercial(utilidad_semana)):,}",
                           utilidad_semana_num=utilidad_semana,
                           mes_str=f"${int(redondear_comercial(ingresos_mes)):,}",
                           gastos_mes_str=f"${int(redondear_comercial(gastos_mes)):,}",
                           utilidad_mes_str=f"${int(redondear_comercial(utilidad_mes)):,}",
                           utilidad_mes_num=utilidad_mes)

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

    raw_contenido = request.form.get('nuevo_contenido')
    nuevo_contenido = None
    if raw_contenido is not None and str(raw_contenido).strip() != '':
        try:
            nuevo_contenido = float(raw_contenido)
            if nuevo_contenido <= 0:
                nuevo_contenido = 1.0
        except (ValueError, TypeError):
            nuevo_contenido = None

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
                    if nuevo_contenido is not None:
                        fila['Contenido'] = nuevo_contenido
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

            # 🔄 Si cambió el nombre del insumo, actualizamos también en recetas.csv para no romper recetas
            if nuevo_nombre and nuevo_nombre.lower() != producto_busqueda.lower() and os.path.exists('recetas.csv'):
                recetas_actualizadas = []
                enc_recetas = ['Platillo', 'Insumo', 'Cantidad a utilizar', 'Margen']
                with open('recetas.csv', mode='r', encoding='utf-8') as f_r:
                    for fila_r in csv.DictReader(f_r):
                        if (fila_r.get('Insumo') or '').strip().lower() == producto_busqueda.lower():
                            fila_r['Insumo'] = nuevo_nombre
                        recetas_actualizadas.append({
                            'Platillo': fila_r.get('Platillo', ''),
                            'Insumo': fila_r.get('Insumo', ''),
                            'Cantidad a utilizar': fila_r.get('Cantidad a utilizar', 0),
                            'Margen': fila_r.get('Margen', 40.0) or 40.0
                        })
                with open('recetas.csv', mode='w', encoding='utf-8', newline='') as f_r:
                    esc_r = csv.DictWriter(f_r, fieldnames=enc_recetas, extrasaction='ignore')
                    esc_r.writeheader()
                    esc_r.writerows(recetas_actualizadas)

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

    # Mapa rápido de medidas por insumo
    mapa_medidas = {p['Producto'].lower().strip(): p.get('Medida', '') for p in base_de_datos if p.get('Producto')}

    if platillo:
        for r in recetas_bd:
            if r.get('Platillo') == platillo:
                r_copia = dict(r)
                r_copia['Medida'] = mapa_medidas.get((r.get('Insumo') or '').lower().strip(), '')
                ingredientes_actuales.append(r_copia)
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
    monto_descuento = 0.0
    descuento_pct = 0
    motivo_descuento = "General"
    puntos_descontar = 0.0

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
            platillo = fila[0].strip()
            try:
                precio = float(fila[2])
            except ValueError:
                precio = 0.0

            # Separamos descuentos y pagos con puntos para mostrarlos en el pie del ticket
            if precio < 0 and platillo == "Pago con Puntos":
                puntos_descontar += abs(precio)
                total_compra += precio
                continue
            elif precio < 0 and platillo.startswith("Desc "):
                monto_descuento += abs(precio)
                total_compra += precio
                try:
                    partes = platillo[5:].split("%:", 1)
                    descuento_pct = int(float(partes[0].strip()))
                    if len(partes) > 1 and partes[1].strip():
                        motivo_descuento = partes[1].strip()
                except Exception:
                    pass
                continue

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

    total_compra = max(0.0, total_compra)
    elementos_ticket = list(elementos_agrupados.values())
    num_recibo_final = recibo_ref if recibo_ref else f"R-{id_fila}"

    puntos_ganados = "N/A"
    puntos_totales = "N/A"

    if cliente_ref != 'General' and os.path.exists('suscripciones.csv'):
        with open('suscripciones.csv', mode='r', encoding='utf-8') as f:
            for fila in csv.DictReader(f):
                if fila.get('Cliente', '').lower().strip() == cliente_ref.lower().strip():
                    try: pts = float(fila.get('Puntos', 0) or 0)
                    except: pts = 0.0
                    puntos_totales = round(pts, 2)
                    puntos_ganados = round(total_compra * 0.05, 2)
                    break

    return render_template('ticket.html',
                           num_recibo=num_recibo_final,
                           fecha_ticket=fecha_ref,
                           cliente=cliente_ref,
                           elementos=elementos_ticket,
                           total=int(total_compra),
                           puntos_ganados=puntos_ganados,
                           puntos_totales=puntos_totales,
                           metodo_pago=metodo_ref,
                           monto_descuento=int(monto_descuento),
                           descuento_pct=int(descuento_pct),
                           motivo_descuento=motivo_descuento,
                           puntos_descontar=int(puntos_descontar))

# =====================================================================
# --- RUTAS DE FASE 1: CORTE DE CAJA, GASTOS Y TURNOS (COMPLETAS) ---
# =====================================================================

@app.route('/caja')
@login_required
def modulo_caja():
    cargar_datos_iniciales()
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

    return render_template('caja.html',
                           estado_turno=estado_turno,
                           fondo_inicial=fondo_inicial,
                           desglose_ventas=desglose_ventas,
                           total_ventas=total_ventas,
                           gastos=gastos_hoy,
                           total_gastos=total_gastos,
                           efectivo_esperado=efectivo_esperado,
                           fondo_final_real=fondo_final_real,
                           diferencia=diferencia,
                           fecha=fecha_hoy,
                           inventario=base_de_datos)

@app.route('/eliminar_gasto/<int:id_fila>', methods=['POST'])
@login_required
def eliminar_gasto(id_fila):
    import re
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

            # 🔄 Si el gasto era una compra de insumo (ej. "📦 Huevo (+1000 g)"), descontamos ese stock del inventario
            nota_inventario = ""
            coincidencia = re.match(r'^📦\s+(.+?)\s+\(\+([0-9.]+)\s+([^)]+)\)$', concepto.strip())
            if coincidencia:
                nombre_insumo_rev = coincidencia.group(1).strip()
                try:
                    cant_rev = float(coincidencia.group(2))
                except ValueError:
                    cant_rev = 0.0
                medida_rev = coincidencia.group(3).strip()

                archivo_inv = 'inventario.csv'
                if cant_rev > 0 and os.path.exists(archivo_inv):
                    filas_inv = []
                    encabezados_inv = ['Producto', 'Precio', 'Contenido', 'Medida', 'Cantidad', 'Presentación', 'Minimo']
                    se_desconto = False
                    with open(archivo_inv, mode='r', encoding='utf-8-sig') as f_inv:
                        lector_inv = csv.DictReader(f_inv)
                        if lector_inv.fieldnames:
                            encabezados_inv = [field.strip() for field in lector_inv.fieldnames if field]
                        for fila_i in lector_inv:
                            prod_nom = (fila_i.get('Producto') or '').strip()
                            if prod_nom.lower() == nombre_insumo_rev.lower():
                                try:
                                    stock_act = float(fila_i.get('Cantidad') or 0)
                                except (ValueError, TypeError):
                                    stock_act = 0.0
                                fila_i['Cantidad'] = round(max(0.0, stock_act - cant_rev), 2)
                                se_desconto = True
                            filas_inv.append(fila_i)

                    if se_desconto:
                        with open(archivo_inv, mode='w', encoding='utf-8', newline='') as f_inv:
                            esc_inv = csv.DictWriter(f_inv, fieldnames=encabezados_inv, extrasaction='ignore')
                            esc_inv.writeheader()
                            esc_inv.writerows(filas_inv)
                        cargar_datos_iniciales()
                        nota_inventario = f"\n📦 Se descontaron -{cant_rev:g} {medida_rev} de '{nombre_insumo_rev}' en el inventario."

            enviar_alerta_telegram(f"❌ Retiro Cancelado\n\nSe eliminó el gasto de: {concepto}\nEl monto de +${monto} ha regresado a la caja.{nota_inventario}")

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
    es_compra_insumo = request.form.get('es_compra_insumo') == '1'
    try:
        monto = float(request.form.get('monto', 0))
    except (ValueError, TypeError):
        monto = 0.0

    fecha_hoy = obtener_fecha_hoy()
    archivo_gastos = 'gastos.csv'
    nota_telegram_inventario = ""

    if es_compra_insumo:
        insumo_nombre = (request.form.get('insumo_nombre') or '').strip()
        try:
            cantidad_comprada = float(request.form.get('cantidad_comprada', 0))
        except (ValueError, TypeError):
            cantidad_comprada = 0.0

        medida_nueva = (request.form.get('medida_insumo') or 'g').strip() or 'g'
        presentacion_nueva = (request.form.get('presentacion_insumo') or '').strip()
        try:
            minimo_nuevo = float(request.form.get('minimo_insumo', 5))
        except (ValueError, TypeError):
            minimo_nuevo = 5.0

        if insumo_nombre and cantidad_comprada > 0:
            archivo_inv = 'inventario.csv'
            encabezados_inv = ['Producto', 'Precio', 'Contenido', 'Medida', 'Cantidad', 'Presentación', 'Minimo']
            filas_inv = []
            encontrado = False
            medida_registrada = medida_nueva

            if os.path.exists(archivo_inv):
                with open(archivo_inv, mode='r', encoding='utf-8-sig') as f_inv:
                    lector_inv = csv.DictReader(f_inv)
                    if lector_inv.fieldnames:
                        encabezados_inv = [field.strip() for field in lector_inv.fieldnames if field]
                    if 'Minimo' not in encabezados_inv:
                        encabezados_inv.append('Minimo')

                    for fila in lector_inv:
                        prod_csv = (fila.get('Producto') or '').strip()
                        if prod_csv.lower() == insumo_nombre.lower():
                            encontrado = True
                            insumo_nombre = prod_csv # Conservamos el nombre oficial del inventario
                            medida_registrada = (fila.get('Medida') or medida_nueva).strip()

                            # 1. Sumamos la cantidad comprada al stock actual
                            try:
                                stock_actual = float(fila.get('Cantidad') or 0)
                            except (ValueError, TypeError):
                                stock_actual = 0.0
                            nuevo_stock = round(stock_actual + cantidad_comprada, 2)
                            fila['Cantidad'] = nuevo_stock

                            # 2. Verificamos si cambió el precio proporcionalmente a su Contenido base
                            try:
                                contenido_base = float(fila.get('Contenido') or 1)
                                if contenido_base <= 0:
                                    contenido_base = cantidad_comprada
                                    fila['Contenido'] = contenido_base
                            except (ValueError, TypeError):
                                contenido_base = cantidad_comprada
                                fila['Contenido'] = contenido_base

                            precio_ant_str = str(fila.get('Precio') or '0').replace('$', '').replace(',', '').strip()
                            try:
                                precio_anterior = float(precio_ant_str)
                            except (ValueError, TypeError):
                                precio_anterior = 0.0

                            # Nuevo precio para el contenido base = (monto pagado / cantidad comprada) * contenido_base
                            nuevo_precio_base = round((monto / cantidad_comprada) * contenido_base, 2)
                            precio_formateado = f"${int(nuevo_precio_base)}" if nuevo_precio_base.is_integer() else f"${nuevo_precio_base:.2f}"
                            fila['Precio'] = precio_formateado

                            if abs(nuevo_precio_base - precio_anterior) >= 0.01:
                                nota_telegram_inventario = (
                                    f"\n📦 Stock sumado: +{cantidad_comprada:g} {medida_registrada} (Total: {nuevo_stock:g} {medida_registrada})"
                                    f"\n🏷️ Precio actualizado: de ${precio_anterior:g} a {precio_formateado} (por cada {contenido_base:g} {medida_registrada}) en Inventario y Recetario."
                                )
                            else:
                                nota_telegram_inventario = f"\n📦 Stock sumado al inventario: +{cantidad_comprada:g} {medida_registrada} (Total: {nuevo_stock:g} {medida_registrada})"

                        filas_inv.append(fila)

            if not encontrado:
                # Es un insumo nuevo: lo damos de alta automáticamente en inventario.csv
                precio_formateado = f"${int(monto)}" if monto.is_integer() else f"${monto:.2f}"
                if not presentacion_nueva:
                    presentacion_nueva = f"{cantidad_comprada:g} {medida_registrada}"
                filas_inv.append({
                    'Producto': insumo_nombre,
                    'Precio': precio_formateado,
                    'Contenido': cantidad_comprada,
                    'Medida': medida_registrada,
                    'Cantidad': cantidad_comprada,
                    'Presentación': presentacion_nueva,
                    'Minimo': minimo_nuevo
                })
                nota_telegram_inventario = (
                    f"\n🆕 Nuevo insumo creado en Inventario: {insumo_nombre}"
                    f"\n📦 Stock inicial: {cantidad_comprada:g} {medida_registrada} | Costo base: {precio_formateado}"
                )

            with open(archivo_inv, mode='w', encoding='utf-8', newline='') as f_inv:
                esc_inv = csv.DictWriter(f_inv, fieldnames=encabezados_inv, extrasaction='ignore')
                esc_inv.writeheader()
                esc_inv.writerows(filas_inv)

            cargar_datos_iniciales()
            concepto = f"📦 {insumo_nombre} (+{cantidad_comprada:g} {medida_registrada})"
        else:
            concepto = request.form.get('concepto', 'Gasto General').strip() or 'Compra de Insumo'
    else:
        concepto = request.form.get('concepto', 'Gasto General').strip() or 'Gasto General'

    encabezados = ['Fecha', 'Concepto', 'Monto']
    if not os.path.exists(archivo_gastos):
        with open(archivo_gastos, mode='w', encoding='utf-8', newline='') as f:
            escritor = csv.DictWriter(f, fieldnames=encabezados)
            escritor.writeheader()

    with open(archivo_gastos, mode='a', encoding='utf-8', newline='') as f:
        escritor = csv.DictWriter(f, fieldnames=encabezados)
        escritor.writerow({'Fecha': fecha_hoy, 'Concepto': concepto, 'Monto': monto})

    enviar_alerta_telegram(f"💸 Retiro de Caja (Gasto)\n\nConcepto: {concepto}\nMonto: -${int(monto)}{nota_telegram_inventario}")
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
    debug_activo = os.getenv('FLASK_DEBUG', '1') == '1'
    app.run(debug=debug_activo)