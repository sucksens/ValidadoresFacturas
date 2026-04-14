# IMPORTS
# Imports de construccion de la API
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, EmailStr
from typing import Annotated, Optional
import uuid as uuid_lib

# Imports de reintentos y manejo multihilo para no lockear las llamadas
import asyncio
import traceback
from tenacity import retry, stop_after_attempt, wait_fixed

# Import de cfdiclient requerimiento basico de validacion
from cfdiclient import Validacion

# import del endpoint de email
import dns.resolver
import aiosmtplib

# Import de pycfdi-transform para parsear XML
from pycfdi_transform import CFDI32SAXHandler, CFDI33SAXHandler, CFDI40SAXHandler
from fastapi import File, UploadFile
from fastapi import File, UploadFile


# --- Inicialización de la Aplicación FastAPI ---
app = FastAPI(
    title="API de Validaciónes Interna",
    description="Una API RESTful para hacer diferentes validaciones, desde cfdis hasta validaciones de correo. ",
    version="1.0.1",
)


"""
    -----------------------------------------------------------------------------------------------------
    Modelos de Solicitud: 
    -----------------------------------------------------------------------------------------------------
"""


class DocumentRequest(BaseModel):
    """
    Define la estructura de datos para la solicitud POST al endpoint de validación.
    Utiliza Pydantic para la validación automática de los campos.
    """

    rfc_emisor: Annotated[str, Field(min_length=12, max_length=13)]
    rfc_receptor: Annotated[str, Field(min_length=12, max_length=13)]
    total: Annotated[float, Field(gt=-1)]
    uuid: Annotated[uuid_lib.UUID, Field()]


class EmailRequest(BaseModel):
    """
    Modelos del Request del endpoint de validacion de correo
    """

    email: Annotated[EmailStr, Field(min_length=5)]
    tipo: bool


class XmlResponse(BaseModel):
    """
    Modelo de respuesta para el endpoint de parseo XML
    """

    exito: bool = Field(description="Indica si el XML fue parseado exitosamente")
    version: Optional[str] = Field(
        description="Versión del CFDI detectada", default=None
    )
    datos: Optional[dict] = Field(
        description="Estructura de datos del XML parseado", default=None
    )
    error: Optional[str] = Field(
        description="Mensaje de error si el XML no pudo ser parseado", default=None
    )


# Configuración de seguridad para parseo XML
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_MIME_TYPES = ["text/xml", "application/xml"]

# Configuración segura del parser XML (protección XXE)
import lxml.etree as etree

XML_PARSER = etree.XMLParser(
    resolve_entities=False,
    no_network=True,
    dtd_validation=False,
    load_dtd=False,
    huge_tree=False,
)


"""
    -----------------------------------------------------------------------------------------------------
    Modelos de Respuesta: 
    -----------------------------------------------------------------------------------------------------
"""


class DocumentResponse(BaseModel):
    """
    Define la estructura de datos para la respuesta del endpoint de validación.
    Proporciona información clara sobre el resultado de la operación.
    """

    mensaje: str = Field(
        description="Un mensaje descriptivo sobre el resultado de la operación."
    )
    datos_recibidos: dict = Field(
        description="Los datos exactos que fueron recibidos en la solicitud para su validación."
    )
    estado_validacion: str = Field(
        description="El estado de validación del documento CFDI. "
        "Valores posibles pueden incluir 'VIGENTE', 'CANCELADO', 'ERROR', etc., "
        "dependiendo de la respuesta del servicio de validación."
    )
    id_operacion: uuid_lib.UUID = Field(
        description="Un ID único generado para esta operación de validación específica, "
        "útil para el seguimiento de solicitudes."
    )
    procesamiento_exitoso: bool = Field(
        description="Indica si la operación de procesamiento y validación se completó sin errores."
    )


class EmailValidationResponse(BaseModel):
    """
    Define la estructura de datos de la respues del endpoint de validacion del correo.
    Proporciona informacion clara sobre los resultados de la operacion.
    """

    email: str = Field(description="El correo que se envio a validar")
    domain_has_mx: bool = Field(
        description="Un booleano que te dice si el dominio existe y si tiene correo"
    )
    domain_mx_records: Optional[list[str]] = None
    smtp_check_possible: bool = False
    smtp_check_result: Optional[str] = (
        None  # "accepted", "rejected", "timeout", "error"
    )
    exists: Optional[bool] = None  # Solo si el smtp check es positivo
    error: Optional[str] = None


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
        uuid=str(documento.uuid),
    )


"""
    -----------------------------------------------------------------------------------------------------
    Endpoints: 
    -----------------------------------------------------------------------------------------------------
"""


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
        estado_resultado = await asyncio.to_thread(
            obtener_estado_con_reintento, validacion, documento
        )

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
            id_operacion=id_operacion,
        )
    except Exception as e:
        # Manejo de excepciones: Si ocurre cualquier error inesperado durante el proceso
        # de validación, se captura y se retorna un error 500 al cliente.
        # El detalle incluye el mensaje de la excepción para facilitar la depuración.
        traceback_str = "".join(traceback.format_exception(None, e, e.__traceback__))
        print(f"ERROR durante validación: {traceback_str}")
        raise HTTPException(
            status_code=500,
            detail=f"Error interno del servidor al validar la factura: {str(e)}",
        )


@app.post("/validar_email/", response_model=EmailValidationResponse)
async def validar_email(request: EmailRequest):
    email = request.email
    tipo = request.tipo
    domain = email.split("@")[1]

    response = EmailValidationResponse(
        email=email,
        domain_has_mx=False,
        domain_mx_records=[],
        smtp_check_possible=False,
        smtp_check_result=None,
        exists=None,
        error=None,
    )

    # 1. Verificar registros MX del dominio
    try:
        mx_records = dns.resolver.resolve(domain, "MX")
        mx_list = [str(mx.exchange).rstrip(".") for mx in mx_records]
        response.domain_has_mx = True
        response.domain_mx_records = mx_list
    except Exception as e:
        response.error = f"Error resolving MX records: {str(e)}"
        return response

    if tipo:
        return response
    # 2. Opcional: Intentar verificar existencia real del correo vía SMTP (con advertencias)
    # ⚠️ Esto NO es 100% confiable. Muchos servidores rechazan o ignoran estos checks por anti-spam.
    try:
        # Tomar el primer servidor MX
        mx_host = response.domain_mx_records[0]
        # Conectar al servidor SMTP del dominio
        server = aiosmtplib.SMTP(timeout=10)
        await server.connect(hostname=mx_host, port=25)  # Puerto 25 estándar para SMTP

        # Enviar comandos SMTP básicos
        await server.helo()  # o ehlo
        await server.mail("validator@motormexa.mx")  # Remitente ficticio
        code, message = await server.rcpt(email)  # Intentar destinatario

        await server.quit()

        # Interpretar respuesta
        if code == 250:
            response.smtp_check_possible = True
            response.smtp_check_result = "accepted"
            response.exists = True
        elif code in (550, 553):
            response.smtp_check_possible = True
            response.smtp_check_result = "rejected"
            response.exists = False
        else:
            response.smtp_check_possible = True
            response.smtp_check_result = f"unknown_code_{code}"
            response.exists = None  # Incierto

    except asyncio.TimeoutError:
        response.smtp_check_result = "timeout"
    except Exception as smtp_error:
        response.smtp_check_result = "error"
        response.error = f"SMTP check failed: {str(smtp_error)}"

    return response


def validar_xml_seguro(xml_content: bytes) -> bool:
    """
    Valida que el contenido sea XML válido y no contenga estructuras maliciosas.
    Retorna True si es válido, False si hay problemas.
    """
    try:
        root = etree.fromstring(xml_content, parser=XML_PARSER)
        return True
    except etree.XMLSyntaxError:
        return False
    except etree.XMLParserError:
        return False
    except Exception:
        return False


def detectar_version_cfdi(xml_content: str) -> Optional[str]:
    """
    Detecta la versión del CFDI desde el contenido XML
    """
    import re

    # Buscar versión en el atributo Version del nodo principal
    version_match = re.search(r'version="([3-4]\.[0-9])"', xml_content.lower())
    if version_match:
        return version_match.group(1)

    # Buscar versión en el atributo Version del nodo Comprobante
    comprobante_match = re.search(
        r'cfdi:comprobante[^>]*version="([3-4]\.[0-9])"', xml_content.lower()
    )
    if comprobante_match:
        return comprobante_match.group(1)

    # Buscar versión en el namespace
    namespace_match = re.search(
        r"http://www\.sat\.gob\.mx/cfd/([3-4])", xml_content.lower()
    )
    if namespace_match:
        return (
            f"{namespace_match.group(1)}.0"
            if namespace_match.group(1) == "3"
            else "4.0"
        )

    return None


@app.post("/parsear_xml/", response_model=XmlResponse)
async def parsear_xml(file: UploadFile = File(...)):
    """
    Endpoint que recibe un archivo XML CFDI y lo parsea usando pycfdi-transform.
    Soporta versiones 3.2, 3.3 y 4.0 del CFDI.

    **Parámetros de la Solicitud (multipart/form-data):**
    - `file`: Archivo XML a parsear

    **Respuestas HTTP:**
    - `200 OK`: Retorna un `XmlResponse` con los datos parseados o error
    - `400 Bad Request`: Si el archivo no es válido
    - `413 Payload Too Large`: Si el archivo excede el tamaño máximo
    - `422 Unprocessable Entity`: Si los datos de entrada no cumplen con las validaciones
    - `500 Internal Server Error`: Si ocurre un error inesperado durante el procesamiento
    """
    detected_version = None

    try:
        # Validación 1: Verificar extensión del archivo
        if not file.filename or not file.filename.lower().endswith(".xml"):
            raise HTTPException(
                status_code=400,
                detail="El archivo debe tener extensión .xml",
            )

        # Validación 2: Verificar tamaño del archivo
        if file.size and file.size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE // (1024 * 1024)}MB",
            )

        # Leer contenido del archivo
        content = await file.read()

        # Validación 3: Verificar que no esté vacío
        if not content or len(content) == 0:
            raise HTTPException(
                status_code=400,
                detail="El archivo está vacío",
            )

        # Validación 4: Verificar tamaño real después de leer
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo excede el tamaño máximo de {MAX_FILE_SIZE // (1024 * 1024)}MB",
            )

        # Convertir a string para detección de versión
        xml_content = content.decode("utf-8")

        # Validar que el XML es seguro y está bien formado
        if not validar_xml_seguro(content):
            return XmlResponse(
                exito=False,
                version=None,
                datos=None,
                error="XML malformado o estructura inválida",
            )

        # Detectar la versión del CFDI
        detected_version = detectar_version_cfdi(xml_content)

        if not detected_version:
            return XmlResponse(
                exito=False,
                version=None,
                datos=None,
                error="No se pudo detectar la versión del CFDI",
            )

        # Seleccionar el handler apropiado según la versión
        if detected_version == "3.2":
            transformer = (
                CFDI32SAXHandler().use_concepts_cfdi32().use_ventavehiculos11()
            )
        elif detected_version == "3.3":
            transformer = (
                CFDI33SAXHandler()
                .use_concepts_cfdi33()
                .use_pagos10()
                .use_related_cfdis()
                .use_ventavehiculos11()
            )
        elif detected_version == "4.0":
            transformer = (
                CFDI40SAXHandler()
                .use_concepts_cfdi40()
                .use_pagos20()
                .use_related_cfdis()
                .use_ventavehiculos11()
            )
        else:
            return XmlResponse(
                exito=False,
                version=detected_version,
                datos=None,
                error=f"Versión de CFDI {detected_version} no soportada",
            )

        # Parsear el XML desde el string
        cfdi_data = transformer.transform_from_string(xml_content)

        return XmlResponse(
            exito=True,
            version=detected_version,
            datos=cfdi_data,
            error=None,
        )

    except HTTPException:
        raise

    except Exception as e:
        # Manejar errores de XML malformado o que no es CFDI
        error_msg = str(e)

        # Determinar si es un error de XML malformado
        if "XML" in error_msg.upper() or "PARS" in error_msg.upper():
            error_msg = "XML malformado o no es un CFDI válido"

        return XmlResponse(
            exito=False,
            version=detected_version,
            datos=None,
            error=error_msg,
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
