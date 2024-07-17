"""
Простой HTTP сервер для обслуживания статических файлов.

Этот сервер слушает подключения на указанном хосте и порте, принимает GET запросы
и отправляет соответствующие статические файлы, если они существуют в папке "static".
В случае ошибок или неверных запросов возвращает соответствующие HTTP ошибки.

Используемые константы:
- STATIC_ROOT: Корневая папка, где находятся статические файлы сервера.
- HOST: IP адрес, на котором сервер слушает подключения.
- PORT: Порт, на котором сервер слушает подключения.
- RESPONSE_TEMPLATE: Шаблон HTTP ответа для отправки файлов.

Функции:
- iter_lines(sock: socket.socket, bufsize: int = 16_384) -> typing.Generator[bytes, None, bytes]:
    Читает все строки, разделенные CRLF, из сокета и возвращает их в генераторе.

- serve_file(sock: socket.socket, path: str) -> None:
    Отправляет файл по указанному пути через сокет, если он существует в STATIC_ROOT.

- Request: Кортеж с именованными полями для представления HTTP запроса.
  Методы:
    - from_socket(sock: socket.socket) -> "Request":
        Читает и парсит запрос из сокета, возвращая объект Request.

Используемые HTTP коды ответа:
- 200 OK: Успешный ответ с запрашиваемым файлом.
- 400 Bad Request: Ошибка в запросе клиента.
- 404 Not Found: Файл не найден в STATIC_ROOT.
- 405 Method Not Allowed: Запрошенный метод не поддерживается сервером.

Пример использования:
1. Запустите сервер на указанном хосте и порте.
2. Подключайтесь к серверу с использованием браузера или другого клиента HTTP.

"""
import mimetypes
import os
import socket
import typing

STATIC_ROOT = "static"

HOST = "127.0.0.1"
PORT = 9000

RESPONSE_TEMPLATE = """\
HTTP/1.1 {status}
Content-type: {content_type}
Content-length: {content_length}

""".replace("\n", "\r\n")

METHOD_NOT_ALLOWED_RESPONSE = b"""\
HTTP/1.1 405 Method Not Allowed
Content-type: text/plain
Content-length: 17

Method Not Allowed""".replace(b"\n", b"\r\n")

NOT_FOUND_RESPONSE = b"""\
HTTP/1.1 404 Not Found
Content-type: text/plain
Content-length: 9

Not Found""".replace(b"\n", b"\r\n")

BAD_REQUEST_RESPONSE = b"""\
HTTP/1.1 400 Bad Request
Content-type: text/plain
Content-length: 11

Bad Request""".replace(b"\n", b"\r\n")


def iter_lines(sock: socket.socket, bufsize: int = 16_384) -> typing.Generator[bytes, None, bytes]:
    """Читает все строки, разделенные CRLF, из сокета и возвращает их в генераторе."""
    buff = b""
    while True:
        data = sock.recv(bufsize)
        if not data:
            return b""

        buff += data
        while True:
            try:
                i = buff.index(b"\r\n")
                line, buff = buff[:i], buff[i + 2:]
                if not line:
                    return buff

                yield line
            except IndexError:
                break


def serve_file(sock: socket.socket, path: str) -> None:
    """Отправляет файл по указанному пути через сокет, если он существует."""
    if path == "/":
        path = "/index.html"

    abspath = os.path.normpath(os.path.join(STATIC_ROOT, path.lstrip("/")))
    if not abspath.startswith(STATIC_ROOT):
        sock.sendall(NOT_FOUND_RESPONSE)
        return

    try:
        with open(abspath, "rb") as f:
            stat = os.fstat(f.fileno())
            content_type, encoding = mimetypes.guess_type(abspath)
            if content_type is None:
                content_type = "application/octet-stream"

            if encoding is not None:
                content_type += f"; charset={encoding}"

            response_headers = RESPONSE_TEMPLATE.format(
                status="200 OK",
                content_type=content_type,
                content_length=stat.st_size,
            ).encode("ascii")

            sock.sendall(response_headers)
            sock.sendfile(f)
    except FileNotFoundError:
        sock.sendall(NOT_FOUND_RESPONSE)
        return


class Request(typing.NamedTuple):
    method: str
    path: str
    headers: typing.Mapping[str, str]

    @classmethod
    def from_socket(cls, sock: socket.socket) -> "Request":
        """Читает и парсит запрос из сокета."""
        lines = iter_lines(sock)

        try:
            request_line = next(lines).decode("ascii")
        except StopIteration:
            raise ValueError("Отсутствует строка запроса.")

        try:
            method, path, _ = request_line.split(" ")
        except ValueError:
            raise ValueError(f"Неправильная строка запроса {request_line!r}.")

        headers = {}
        for line in lines:
            try:
                name, _, value = line.decode("ascii").partition(":")
                headers[name.lower()] = value.lstrip()
            except ValueError:
                raise ValueError(f"Неправильная строка заголовка {line!r}.")

        return cls(method=method.upper(), path=path, headers=headers)


with socket.socket() as server_sock:
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind((HOST, PORT))
    server_sock.listen(0)
    print(f"Слушаем {HOST}:{PORT}...")

    while True:
        client_sock, client_addr = server_sock.accept()
        print(f"Получено соединение от {client_addr}...")
        with client_sock:
            try:
                request = Request.from_socket(client_sock)
                if request.method != "GET":
                    client_sock.sendall(METHOD_NOT_ALLOWED_RESPONSE)
                    continue

                serve_file(client_sock, request.path)
            except Exception as e:
                print(f"Ошибка при разборе запроса: {e}")
                client_sock.sendall(BAD_REQUEST_RESPONSE)
