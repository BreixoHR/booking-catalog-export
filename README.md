# Booking Catalog Export

Herramienta en **Python** (solo biblioteca estándar) que descarga el **catálogo y las tarifas** de plataformas de reserva (**Regiondo** y **TuriTop**) y los exporta en tres formatos:

- **JSON** normalizado, igual para todas las plataformas;
- **CSV** para que operaciones revise precios en Excel;
- **esqueleto de producto para Google Things To Do**, con los precios en formato `Money`, listo para completar y validar en [things-to-do-feed-builder](https://github.com/BreixoHR/things-to-do-feed-builder).

![python](https://img.shields.io/badge/python-3.10%20%E2%80%93%203.13-3776AB) ![deps](https://img.shields.io/badge/dependencias-0-brightgreen) ![tests](https://img.shields.io/badge/unittest-11%20tests-brightgreen) ![license](https://img.shields.io/badge/license-MIT-blue)

```bash
export REGIONDO_PUBLIC_KEY=… REGIONDO_SECRET=…
python -m catalog regiondo --out catalogo --ttd-landing "https://www.example.com/reservar?p={product_id}&v={variation_id}"
# 45 productos | 135 tarifas | 47 llamadas -> catalogo/

export TURITOP_SHORT_ID=… TURITOP_SECRET=…
python -m catalog turitop --products P1,P2,P3 --out catalogo
```

## Qué resuelve

Dar de alta los productos en Google Things To Do exigía copiar a mano los precios por tipo de cliente de cada producto (adulto, niño, bebé, senior…) desde varias plataformas. Esta herramienta lo automatiza:

| | Regiondo | TuriTop |
|---|---|---|
| Autenticación | HMAC-SHA256 de (timestamp + clave pública + querystring ordenada) | OAuth propio: *grant* y *refresh*. Ante un 401 renueva el token y reintenta **una sola vez** |
| Catálogo | `/products` paginado y `/products/availoptions/{variation}` | `/tickets/get` por producto, sin *add-ons*, ordenado |
| Particularidades | — | Algunos textos llegan en Unicode NFD (`"Niños"`): se normalizan a NFC |

Común a las dos:

- **tope de llamadas por ejecución** y pausa entre peticiones, para proteger la cuota de la API;
- **credenciales solo por variables de entorno**;
- **importes como texto decimal exacto**, nunca `float`.

## Clasificación de tipos de cliente

Las plataformas devuelven nombres de tarifa libres y en varios idiomas. [`customer_groups.py`](src/catalog/customer_groups.py) interpreta primero el **rango de edad** y, si no lo hay, busca **palabras clave** en español, inglés, francés, alemán e italiano:

| Tarifa | Grupo |
|---|---|
| `Adultos (+18)` · `Erwachsene` · `Entrada general` | adult |
| `Niños (6-10)` · `Child 4-12` · `Kinder bis 5 Jahre` · `Enfant` | child |
| `Jóvenes (12-18)` · `Estudiante` | youth |
| `Bebé (0-2)` | infant |
| `Senior 65+` | senior |

> La versión anterior (scripts sueltos) buscaba `"0"` o `"18"` como subcadena: **"Niños (6-10)" salía como bebé** porque contiene un 0, y "Jóvenes (12-18)" como adulto. Además no reconocía "Niños" porque solo buscaba palabras en inglés.

## Mejoras respecto a los scripts originales

| Antes | Ahora |
|---|---|
| Claves de API escritas en el código | Variables de entorno |
| Clasificación por subcadenas | Rangos de edad y palabras clave multilingües, con tests |
| Un script por plataforma, cada uno con su formato de salida | Modelo común (`Product → Variation → Price`) y exportadores compartidos |
| Contador global de llamadas en una variable `global` | `HttpClient` con presupuesto y pausa configurables |
| `requests` y `pandas` como dependencias | Cero dependencias: funciona con el Python del sistema |
| Precios como texto y sin conversión | `Money` exacto con `Decimal` (`"19.90"` → `units: "19", nanos: 900000000`) |
| — | La CLI fallaba al final en consolas de Windows por imprimir caracteres no ASCII (lo detectó el test de la CLI) |

## Tests

```bash
PYTHONPATH=src:tests python -m unittest discover -s tests -v
```

Los tests levantan **servidores HTTP locales que imitan las dos APIs**. El de Regiondo **verifica la firma HMAC** de cada petición, igual que el real. El de TuriTop hace caducar el token entre llamadas. Cubren:

- la paginación (45 productos en 2 páginas);
- la firma y la clave incorrecta;
- el tope de llamadas;
- el *grant* y el *refresh* (que se hacen una sola vez);
- la normalización NFC y la exclusión de *add-ons*;
- la clasificación de tipos de cliente;
- el formato `Money`;
- el CSV con comas;
- la CLI completa, generando los tres ficheros.

## Licencia

[MIT](LICENSE)
