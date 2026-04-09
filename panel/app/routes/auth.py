from __future__ import annotations

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse

from ..core import templates, template_context, settings, with_base
from ..deps import require_login, verify_password

router = APIRouter()


@router.get("/login")
def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", template_context(request))


@router.post("/login")
def login_action(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
):
    if username == settings.admin_user and verify_password(password):
        request.session["user"] = username
        return RedirectResponse(with_base("/"), status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        template_context(request, error="Неверные данные"),
    )


@router.post("/logout")
def logout_action(request: Request):
    request.session.clear()
    return RedirectResponse(with_base("/login"), status_code=303)


@router.get("/")
def index(request: Request):
    require_login(request)
    return templates.TemplateResponse(request, "index.html", template_context(request))
