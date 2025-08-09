import mysql.connector
import requests
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- Configuración del logging para mostrar en consola y guardar en archivo ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- Configuración de la Base de Datos ---
DB_CONFIG = {
    'host': '200.1.0.36',
    'database': 'analisis_sat',
    'user': 'soporte',
    'password': 'o!&36N2Sd$37q*'
}

# --- Configuración del Endpoint de Validación ---
API_URL = 'http://localhost:8000/validar_factura/'
API_URL = 'http://200.1.1.245:5000/validar_factura/'

# --- Configuración de Concurrencia ---
# Número máximo de hilos (solicitudes concurrentes)
MAX_WORKERS = 1000

def get_db_connection():
    """Establece y retorna una conexión a la base de datos."""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        logging.info("Conexión a la base de datos establecida exitosamente.")
        return conn
    except mysql.connector.Error as err:
        logging.error(f"Error al conectar a la base de datos: {err}")
        return None

def get_invoices_from_db(conn, table_name, year, month):
    """
    Obtiene facturas de la tabla especificada para un año y mes dados.
    Retorna una lista de diccionarios con los datos de las facturas.
    """
    cursor = conn.cursor(dictionary=True)
    invoices = []
    try:
        query = f"""
            SELECT uuid, rfc_emi, rfc_recep, total, estado
            FROM {table_name}
            WHERE YEAR(fecha) = %s AND MONTH(fecha) = %s
        """
        cursor.execute(query, (year, month))
        invoices = cursor.fetchall()
        logging.info(f"Se recuperaron {len(invoices)} facturas de la tabla '{table_name}' para {month}/{year}.")
    except mysql.connector.Error as err:
        logging.error(f"Error al obtener facturas de la DB: {err}")
    finally:
        cursor.close()
    return invoices

def validate_invoice_with_api(invoice_data):
    """
    Llama al endpoint de validación de facturas.
    Retorna una tupla (uuid, respuesta_json) o (uuid, None) en caso de error.
    """
    uuid = invoice_data['uuid']
    payload = {
        "rfc_emisor": invoice_data['rfc_emi'],
        "rfc_receptor": invoice_data['rfc_recep'],
        "total": float(invoice_data['total']), # Asegúrate de que el total sea un float
        "uuid": uuid
    }
    try:
        response = requests.post(API_URL, json=payload)
        response.raise_for_status()  # Lanza una excepción para códigos de estado HTTP 4xx/5xx
        return uuid, response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error al llamar al API para UUID {uuid}: {e}")
        return uuid, None
    except json.JSONDecodeError:
        logging.error(f"Error al decodificar la respuesta JSON para UUID {uuid}.")
        return uuid, None

def update_invoice_status_in_db(conn, table_name, uuid, new_status):
    """
    Actualiza el estado de una factura en la base de datos.
    """
    cursor = conn.cursor()
    try:
        query = f"""
            UPDATE {table_name}
            SET estado = %s
            WHERE uuid = %s
        """
        cursor.execute(query, (new_status, uuid))
        conn.commit()
        logging.info(f"Estado de la factura UUID {uuid} actualizado a {new_status} en la tabla '{table_name}'.")
    except mysql.connector.Error as err:
        logging.error(f"Error al actualizar el estado de la factura UUID {uuid}: {err}")
        conn.rollback() # Deshacer cambios en caso de error
    finally:
        cursor.close()

def map_api_status_to_db(api_status):
    """Mapea el estado del API ('Vigente', 'Cancelado') a un valor de DB (1, 0)."""
    if api_status == "Vigente":
        return 1
    elif api_status == "Cancelado":
        return 0
    else:
        # Manejar otros estados si es necesario, o retornar un valor por defecto
        logging.warning(f"Estado de API desconocido: {api_status}. Asumiendo 1 (Vigente).")
        return 1

def main():
    """Función principal para ejecutar el proceso de validación."""
    year = int(input("Introduce el año (ej. 2023): "))
    month = int(input("Introduce el mes (1-12): "))
    
    while True:
        table_type = input("¿Deseas revisar facturas 'emitidos' o 'recibidos'? ").lower()
        if table_type in ['emitidos', 'recibidos']:
            table_name = f"Xml_{table_type}"
            break
        else:
            print("Entrada inválida. Por favor, escribe 'emitidos' o 'recibidos'.")

    conn = None
    try:
        conn = get_db_connection()
        if not conn:
            return

        invoices = get_invoices_from_db(conn, table_name, year, month)

        if not invoices:
            logging.info(f"No se encontraron facturas para {month}/{year} en la tabla '{table_name}'.")
            return

        # Diccionario para mapear UUIDs a sus datos de DB originales
        invoice_data_map = {inv['uuid']: inv for inv in invoices}

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # Enviar todas las tareas al ThreadPoolExecutor
            future_to_uuid = {executor.submit(validate_invoice_with_api, invoice): invoice['uuid'] for invoice in invoices}

            for future in as_completed(future_to_uuid):
                uuid = future_to_uuid[future]
                try:
                    # El resultado de la tarea es una tupla (uuid, api_response)
                    _, api_response = future.result() 
                    db_invoice_data = invoice_data_map[uuid]
                    db_status = db_invoice_data['estado'] # Estado actual en la DB (1 o 0)

                    if api_response and api_response.get('procesamiento_exitoso'):
                        api_validation_status = api_response.get('estado_validacion')
                        if api_validation_status:
                            mapped_api_status = map_api_status_to_db(api_validation_status)

                            if mapped_api_status != db_status:
                                logging.warning(f"Discrepancia encontrada para UUID {uuid}:")
                                logging.warning(f"  DB Estado: {'Vigente' if db_status == 1 else 'Cancelado'} ({db_status})")
                                logging.warning(f"  API Estado: {api_validation_status} ({mapped_api_status})")
                                update_invoice_status_in_db(conn, table_name, uuid, mapped_api_status)
                            else:
                                logging.info(f"  UUID {uuid}: Estado consistente ({api_validation_status}).")
                        else:
                            logging.warning(f"  UUID {uuid}: La respuesta del API no contiene 'estado_validacion'.")
                    else:
                        logging.error(f"  UUID {uuid}: Fallo en el procesamiento del API o 'procesamiento_exitoso' es falso.")
                except Exception as exc:
                    logging.error(f"UUID {uuid} generó una excepción: {exc}")

    finally:
        if conn:
            conn.close()
            logging.info("Conexión a la base de datos cerrada.")

if __name__ == "__main__":
    main()
