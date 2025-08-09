# IMPORTS
# Imports de construccion de la API
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import Annotated
import uuid as uuid_lib
# Imports de reintentos y manejo multihilo para no lockear las llamadas
import asyncio
import traceback
from tenacity import retry, stop_after_attempt, wait_fixed
# Import de cfdiclient requerimiento basico de validacion
from cfdiclient import Validacion


# --- Inicialización de la Aplicación FastAPI ---
app = FastAPI(
    title="API de Validación de Documentos CFDI",
    description="Una API RESTful para validar información de documentos CFDI usando RFC del emisor, RFC del receptor, total y UUID.",
    version="1.0.0"
)


# --- Modelos de Datos para la Solicitud y Respuesta ---
class DocumentRequest(BaseModel):
    """
    Define la estructura de datos para la solicitud POST al endpoint de validación.
    Utiliza Pydantic para la validación automática de los campos.
    """
    rfc_emisor: Annotated[str, Field(min_length=12, max_length=13)]
    rfc_receptor: Annotated[str, Field(min_length=12, max_length=13)]
    total: Annotated[float, Field(gt=-1)]
    uuid: Annotated[uuid_lib.UUID, Field()]


class DocumentResponse(BaseModel):
    """
    Define la estructura de datos para la respuesta del endpoint de validación.
    Proporciona información clara sobre el resultado de la operación.
    """
    mensaje: str = Field(description="Un mensaje descriptivo sobre el resultado de la operación.")
    datos_recibidos: dict = Field(description="Los datos exactos que fueron recibidos en la solicitud para su validación.")
    estado_validacion: str = Field(description="El estado de validación del documento CFDI. "
                                               "Valores posibles pueden incluir 'VIGENTE', 'CANCELADO', 'ERROR', etc., "
                                               "dependiendo de la respuesta del servicio de validación.")
    id_operacion: uuid_lib.UUID = Field(description="Un ID único generado para esta operación de validación específica, "
                                                    "útil para el seguimiento de solicitudes.")
    procesamiento_exitoso: bool = Field(description="Indica si la operación de procesamiento y validación se completó sin errores.")


# Reintento automático: hasta 3 intentos con 2 segundos entre cada uno
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def obtener_estado_con_reintento(validacion, documento):
    """
    Funcion de validacion con reintento, recibe el aobjeto de Validacion, y documento de request ya validado con el DocumentRequest
    """
    return validacion.obtener_estado(
        rfc_emisor=documento.rfc_emisor,
        rfc_receptor=documento.rfc_receptor,
        total=str(documento.total),
        uuid=str(documento.uuid)
    )


@app.post("/validar_factura/", response_model=DocumentResponse)
async def validar_factura(documento: DocumentRequest):
    """
    Endpoint POST que recibe los datos de un documento CFDI para su validación.
    Utiliza el módulo 'cfdiclient' para obtener el estado del documento y
    devuelve una respuesta estructurada con la información de la validación.

    **Parámetros de la Solicitud (en el cuerpo JSON):**
    - `rfc_emisor`: RFC del emisor (string, 12 o 13 caracteres)
    - `rfc_receptor`: RFC del receptor (string, 12 o 13 caracteres)
    - `total`: Monto total del documento (número flotante, mayor que 0)
    - `uuid`: UUID del documento (string en formato UUID)

    **Respuestas HTTP:**
    - `200 OK`: Retorna un `DocumentResponse` si la validación se procesa correctamente.
    - `422 Unprocessable Entity`: Si los datos de entrada no cumplen con las validaciones de Pydantic (ej. formato de RFC, tipo de total, formato de UUID).
    - `500 Internal Server Error`: Si ocurre un error inesperado durante la ejecución de la lógica de validación o al interactuar con 'cfdiclient'.
    """
    try:
        # Instancia la clase de validación del módulo 'cfdiclient'.
        # Esta instancia es la que interactúa con el servicio de validación real.
        validacion = Validacion(timeout=40)
        # Llama al método 'obtener_estado_con_reintento' con el objeto de validacion  en un su propio hilo para que no se bloqueé 
        estado_resultado = await asyncio.to_thread(obtener_estado_con_reintento, validacion, documento)

        # Extrae el estado de validación del diccionario de respuesta de 'cfdiclient'.
        # Si 'estado' no está presente, se asigna 'DESCONOCIDO' como valor por defecto.
        estado_cfdi = estado_resultado.get("estado", "DESCONOCIDO")

        # Convierte el objeto de solicitud Pydantic a un diccionario para incluirlo en la respuesta.
        datos_recibidos_dict = documento.model_dump()

        # Genera un nuevo UUID para esta operación de API, útil para rastrear cada solicitud.
        id_operacion = uuid_lib.uuid4()

        # Retorna la respuesta exitosa con los datos de validación.
        return DocumentResponse(
            mensaje="Factura procesada y validada exitosamente.",
            datos_recibidos=datos_recibidos_dict,
            estado_validacion=estado_cfdi,
            procesamiento_exitoso=True,
            id_operacion=id_operacion
        )
    except Exception as e:
        # Manejo de excepciones: Si ocurre cualquier error inesperado durante el proceso
        # de validación, se captura y se retorna un error 500 al cliente.
        # El detalle incluye el mensaje de la excepción para facilitar la depuración.
        traceback_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
        print(f"ERROR durante validación: {traceback_str}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor al validar la factura: {str(e)}"
        )


# --- Instrucciones para Ejecutar la Aplicación ---
# Para ejecutar esta aplicación:
# 1. Guarda el código en un archivo Python (ej. main.py).
# 2. Asegúrate de tener FastAPI y Uvicorn instalados:
#    pip install fastapi "uvicorn[standard]"
# 3. Ejecuta la aplicación desde tu terminal en el mismo directorio:
#    uvicorn main:app --reload

# Una vez en ejecución, puedes acceder a:
# - La documentación interactiva de la API (Swagger UI): http://127.0.0.1:8000/docs
# - El endpoint para enviar solicitudes POST: http://127.0.0.1:8000/validar_factura/