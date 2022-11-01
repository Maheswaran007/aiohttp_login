import asyncio
import sqlite3
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable, Dict

import aiohttp_jinja2
import aiohttp_session
import aiosqlite
import jinja2
from aiohttp import web


_WebHandler = Callable[[web.Request], Awaitable[web.StreamResponse]]


def require_login(func: _WebHandler) -> _WebHandler:
    
    func.__require_login__ = True  # type: ignore
    return func


@web.middleware
async def check_login(request: web.Request, handler: _WebHandler) -> web.StreamResponse:
    
    require_login = getattr(handler, "__require_login__", False)
    session = await aiohttp_session.get_session(request)
    username = session.get("username")
    password = session.get("password")
    if require_login:
        if not username or not password:
            raise web.HTTPSeeOther(location="/")
    return await handler(request)


async def username_ctx_processor(request: web.Request) -> Dict[str, Any]:
    # Jinja2 context processor
    session = await aiohttp_session.get_session(request)
    username = session.get("username")
    password = session.get("password")
    return {"username": username, "password": password}


@web.middleware
async def error_middleware(
    request: web.Request, handler: _WebHandler
) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except asyncio.CancelledError:
        raise
    except Exception as ex:
        return aiohttp_jinja2.render_template(
            "login.html", request, {"error_text": str(ex)}, status=400
        )


router = web.RouteTableDef()

@router.get("/")
@aiohttp_jinja2.template("login.html")
async def login(request: web.Request) -> Dict[str, Any]:
    
    return {}

@router.get("/index")
@aiohttp_jinja2.template("index.html")
async def login(request: web.Request) -> Dict[str, Any]:
    
    session = await aiohttp_session.get_session(request)
    if session["username"] == None:
        raise web.HTTPSeeOther(location="/")
    return {}


@router.post("/login")
async def login_apply(request: web.Request) -> web.Response:
    
    session = await aiohttp_session.get_session(request)
    form = await request.post()
    username = form["login_user"]
    ret = []
    db = request.config_dict["DB"]
    async with db.execute("SELECT username, password from users where username= ?", [username]) as cursor:
        async for row in cursor:
            ret.append({"username": row["username"], "password": row["password"]})
    
    if not ret:
        raise Exception("No User Found!!")
    if form["login_pass"] != ret[0].get("password"):
        raise Exception("Invalid Credentials!!")
    session["username"] = username
    raise web.HTTPSeeOther(location="/index")



@router.get("/logout")
async def logout(request: web.Request) -> web.Response:
    
    session = await aiohttp_session.get_session(request)
    session["username"] = None
    raise web.HTTPSeeOther(location="/")

def get_db_path() -> Path:
    
    here = Path.cwd()
    return here / "db.sqlite3"


async def init_db(app: web.Application) -> AsyncIterator[None]:
    
    sqlite_db = get_db_path()
    db = await aiosqlite.connect(sqlite_db)
    db.row_factory = aiosqlite.Row
    app["DB"] = db
    yield
    await db.close()


async def init_app() -> web.Application:
    
    app = web.Application(client_max_size=64 * 1024 ** 2)
    app.add_routes(router)
    app.cleanup_ctx.append(init_db)
    aiohttp_session.setup(app, aiohttp_session.SimpleCookieStorage())
    aiohttp_jinja2.setup(
        app,
        loader=jinja2.FileSystemLoader(str(Path(__file__).parent / "templates")),
        context_processors=[username_ctx_processor],
    )
    app.middlewares.append(error_middleware)
    app.middlewares.append(check_login)

    return app


def try_make_db() -> None:
    
    sqlite_db = get_db_path()
    if sqlite_db.exists():
        return

    with sqlite3.connect(sqlite_db) as conn:
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            password TEXT)
        """
        )
        conn.commit()
    
    with sqlite3.connect(sqlite_db) as conn:
        cur = conn.cursor()
        cur.execute(
            "Insert into users (username, password) values('admin', 'pass1234')"
        )
        conn.commit()


try_make_db()


web.run_app(init_app())