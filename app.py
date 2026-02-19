from flask import (
    Flask, render_template, request, redirect, url_for,
    jsonify, session, make_response, flash
)
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import csv, io, os, base64

import qrcode
import qrcode.image.svg  # SVG

# =========================
# CONFIGURAÇÃO BASE
# =========================
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates"),
    static_folder=os.path.join(BASE_DIR, "static"),
)

app.secret_key = os.environ.get("SECRET_KEY", "dev")

# --- QR Code (formulário do técnico) ---
QR_PIN = os.environ.get("QR_PIN", "1234")
BASE_URL = os.environ.get("BASE_URL", "").rstrip("/")

# =========================
# BANCO DE DADOS
# =========================
db_url = os.environ.get("DATABASE_URL")

if db_url:
    # Se vier como postgres:// (Render antigo)
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    # Força usar psycopg v3 (senão tenta psycopg2)
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
else:
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///manutencoes_v3.db"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
PREDEFINED_TIPOS = ["Overlock", "Galoneira", "Travetadeira", "Reta", "Interlock"]
PREDEFINED_PROBLEMAS = [
    "Agulha quebrada",
    "Barulho estranho",
    "Motor não liga",
    "Ponto irregular",
    "Manutenção preventiva",
    "Alimentação de tecido irregular",
]


# -------------------- MODELS --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default="factory")  # 'admin' or 'factory'

    def check_password(self, pwd):
        return check_password_hash(self.password_hash, pwd)


class Machine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    patrimonio = db.Column(db.String(80), unique=True, nullable=False)
    tipo = db.Column(db.String(80), nullable=False)
    setor = db.Column(db.String(80), nullable=True)
    status = db.Column(db.String(30), default="Ativa")  # Ativa, Em manutenção, Desativada


class Manutencao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machine.id"), nullable=False)
    problema = db.Column(db.String(120), nullable=False)
    observacoes = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default="Aberto")  # Aberto, Em andamento, Concluído
    data_abertura = db.Column(db.DateTime, default=datetime.utcnow)
    aberto_por = db.Column(db.String(80), nullable=True)
    machine = db.relationship("Machine", backref="manutencoes")

@app.route("/admin/reset_maquinas_costura", methods=["GET"])
def reset_maquinas_costura():
    if session.get("role") != "admin":
        return "Forbidden", 403

    csv_path = os.path.join(BASE_DIR, "maquinas_costura_importar.csv")
    if not os.path.exists(csv_path):
        return "CSV não encontrado no servidor. Suba 'maquinas_costura_importar.csv' no GitHub.", 400

    # apaga tudo
    Manutencao.query.delete()
    Machine.query.delete()
    db.session.commit()

    inserted = 0
    seen = set()

    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            patrimonio = (row.get("patrimonio") or "").strip()
            tipo = (row.get("tipo") or "").strip()
            setor = (row.get("setor") or "").strip()
            status = (row.get("status") or "Ativa").strip()

            if not patrimonio or patrimonio in seen:
                continue
            seen.add(patrimonio)

            db.session.add(Machine(patrimonio=patrimonio, tipo=tipo, setor=setor, status=status))
            inserted += 1

    db.session.commit()
    return f"OK! Reset feito. Máquinas importadas: {inserted}"



# -------------------- AUTH HELPERS --------------------
def is_logged_in():
    return "user" in session


def current_user_role():
    return session.get("role")


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


# -------------------- QR (SEM PILLOW) --------------------
def _qr_data_uri(url: str) -> str:
    """
    Gera QR em SVG (sem Pillow) e devolve data URI base64
    para usar em <img src="...">.
    """
    factory = qrcode.image.svg.SvgImage
    img = qrcode.make(url, image_factory=factory)

    buf = io.BytesIO()
    img.save(buf)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/svg+xml;base64,{b64}"


# -------------------- INIT DB (Flask 3) --------------------
_db_initialized = False

@app.before_request
def create_tables_once():
    """
    No Flask 3.x o before_first_request foi removido.
    Rodamos uma vez usando flag.
    """
    global _db_initialized
    if _db_initialized:
        return

    db.create_all()

    # seed users
    if User.query.count() == 0:
        admin = User(username="admin", password_hash=generate_password_hash("1234"), role="admin")
        potencia = User(username="potencia", password_hash=generate_password_hash("2524"), role="factory")
        db.session.add_all([admin, potencia])
        db.session.commit()

    # seed machines
   
    _db_initialized = True


# -------------------- ROUTES --------------------
@app.route("/")
def index():
    machines = (
        Machine.query
        .filter(Machine.status != "Desativada")
        .order_by(Machine.tipo, Machine.patrimonio)
        .all()
    )
    return render_template(
        "index.html",
        machines=machines,
        problemas=PREDEFINED_PROBLEMAS,
        user=session.get("user"),
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        u = User.query.filter_by(username=username).first()

        if u and u.check_password(password):
            session["user"] = u.username
            session["role"] = u.role
            return redirect(url_for("dashboard") if u.role == "admin" else url_for("index"))

        return render_template("login.html", error="Usuário ou senha inválidos", user=session.get("user"))

    return render_template("login.html", user=session.get("user"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/novo", methods=["POST"])
def novo():
    machine_id = request.form.get("machine_id", type=int)
    problema = request.form.get("problema")
    observacoes = (request.form.get("observacoes") or "").strip()
    aberto_por = session.get("user") or (request.form.get("aberto_por") or "").strip() or "anonimo"

    if not machine_id or not problema:
        return redirect(url_for("index"))

    m = Manutencao(
        machine_id=machine_id,
        problema=problema,
        observacoes=observacoes,
        status="Aberto",
        aberto_por=aberto_por,
    )
    db.session.add(m)
    db.session.commit()
    return redirect(url_for("index"))


@app.route("/machines", methods=["GET", "POST"])
def machines():
    if not is_logged_in() or current_user_role() != "admin":
        return redirect(url_for("login"))

    if request.method == "POST":
        patrimonio = (request.form.get("patrimonio") or "").strip()
        tipo = request.form.get("tipo")
        setor = (request.form.get("setor") or "").strip()
        status = request.form.get("status") or "Ativa"

        if patrimonio and tipo:
            if not Machine.query.filter_by(patrimonio=patrimonio).first():
                db.session.add(
                    Machine(
                        patrimonio=patrimonio,
                        tipo=tipo,
                        setor=setor or None,
                        status=status,
                    )
                )
                db.session.commit()

        return redirect(url_for("machines"))

    maquinas = Machine.query.order_by(Machine.tipo, Machine.patrimonio).all()
    sectors = sorted({m.setor for m in maquinas if m.setor})
    return render_template(
        "machines.html",
        maquinas=maquinas,
        tipos=PREDEFINED_TIPOS,
        sectors=sectors,
        user=session.get("user"),
    )


@app.route("/machines/edit/<int:id>", methods=["GET", "POST"])
def edit_machine(id):
    if not is_logged_in() or current_user_role() != "admin":
        return redirect(url_for("login"))

    m = Machine.query.get_or_404(id)
    if request.method == "POST":
        m.patrimonio = (request.form.get("patrimonio") or "").strip()
        m.tipo = request.form.get("tipo")
        m.setor = (request.form.get("setor") or "").strip() or None
        m.status = request.form.get("status") or "Ativa"
        db.session.commit()
        return redirect(url_for("machines"))

    return render_template("edit_machine.html", m=m, tipos=PREDEFINED_TIPOS, user=session.get("user"))


@app.route("/list")
def listagem():
    if not is_logged_in() or current_user_role() != "admin":
        return redirect(url_for("login"))

    manut = Manutencao.query.order_by(Manutencao.data_abertura.desc()).all()
    return render_template("listagem.html", manutencoes=manut, user=session.get("user"))


@app.route("/update_status/<int:id>", methods=["POST"])
def update_status(id):
    if not is_logged_in() or current_user_role() != "admin":
        return redirect(url_for("login"))

    novo_status = request.form.get("status")
    m = Manutencao.query.get_or_404(id)
    if novo_status in ["Aberto", "Em andamento", "Concluído"]:
        m.status = novo_status
        db.session.commit()

    return redirect(url_for("listagem"))


@app.route("/dashboard")
def dashboard():
    if not is_logged_in() or current_user_role() != "admin":
        return redirect(url_for("login"))

    sectors = sorted({m.setor for m in Machine.query.all() if m.setor})
    now = datetime.now()
    return render_template(
        "dashboard.html",
        tipos=PREDEFINED_TIPOS,
        sectors=sectors,
        now=now,
        user=session.get("user"),
    )


@app.route("/api/stats")
def api_stats():
    from sqlalchemy import func

    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    setor = request.args.get("setor", type=str)

    q = Manutencao.query.join(Machine)

    if setor:
        q = q.filter(Machine.setor == setor)

    if year and month:
        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
        q = q.filter(Manutencao.data_abertura >= start, Manutencao.data_abertura < end)

    totals_tipo = q.with_entities(Machine.tipo, func.count(Manutencao.id)).group_by(Machine.tipo).all()
    totals_tipo_dict = {t: c for t, c in totals_tipo}

    totals_machine = q.with_entities(Machine.patrimonio, func.count(Manutencao.id)).group_by(Machine.patrimonio).all()
    totals_machine_dict = {p: c for p, c in totals_machine}

    problems = (
        q.with_entities(Machine.patrimonio, Manutencao.problema, func.count(Manutencao.id))
        .group_by(Machine.patrimonio, Manutencao.problema)
        .all()
    )

    problems_dict = {}
    for p, prob, c in problems:
        problems_dict.setdefault(p, []).append({"problema": prob, "count": c})
    for p in problems_dict:
        problems_dict[p] = sorted(problems_dict[p], key=lambda x: x["count"], reverse=True)

    return jsonify(
        {
            "totals_tipo": {t: totals_tipo_dict.get(t, 0) for t in PREDEFINED_TIPOS},
            "totals_machine": totals_machine_dict,
            "problems": problems_dict,
        }
    )


@app.route("/export_machines.csv")
def export_machines_csv():
    if not is_logged_in() or current_user_role() != "admin":
        return redirect(url_for("login"))

    sector = request.args.get("setor")
    q = Machine.query
    if sector:
        q = q.filter(Machine.setor == sector)

    items = q.order_by(Machine.tipo, Machine.patrimonio).all()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["patrimonio", "tipo", "setor", "status"])
    for it in items:
        cw.writerow([it.patrimonio, it.tipo, it.setor or "", it.status])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=machines.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output


@app.route("/export_manutencoes.csv")
def export_manutencoes_csv():
    if not is_logged_in() or current_user_role() != "admin":
        return redirect(url_for("login"))

    year = request.args.get("year", type=int)
    month = request.args.get("month", type=int)
    setor = request.args.get("setor", type=str)

    q = Manutencao.query.join(Machine)
    if setor:
        q = q.filter(Machine.setor == setor)
    if year and month:
        start = datetime(year, month, 1)
        end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
        q = q.filter(Manutencao.data_abertura >= start, Manutencao.data_abertura < end)

    items = q.order_by(Manutencao.data_abertura.desc()).all()

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["id", "patrimonio", "tipo", "setor", "problema", "observacoes", "status", "data_abertura", "aberto_por"])
    for it in items:
        cw.writerow([
            it.id,
            it.machine.patrimonio,
            it.machine.tipo,
            it.machine.setor or "",
            it.problema,
            it.observacoes or "",
            it.status,
            it.data_abertura.isoformat(),
            it.aberto_por or "",
        ])

    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=manutencoes.csv"
    output.headers["Content-type"] = "text/csv; charset=utf-8"
    return output


# -------------------- QR PAGES --------------------
@app.route("/qrcodes")
@login_required
def qrcodes():
    """Página para admin imprimir/baixar os QRs por máquina."""
    if current_user_role() != "admin":
        return redirect(url_for("index"))

    machines = Machine.query.order_by(Machine.patrimonio.asc()).all()
    base = BASE_URL or request.url_root.rstrip("/")

    items = []
    for m in machines:
        url = f"{base}/qr/{m.patrimonio}"
        items.append(
            {
                "patrimonio": m.patrimonio,
                "nome": m.patrimonio,  # <-- FIX: não existe m.nome
                "tipo": m.tipo,
                "setor": m.setor,
                "url": url,
                "qr": _qr_data_uri(url),  # SVG base64
            }
        )

    return render_template("qrcodes.html", items=items, base=base, user=session.get("user"))


@app.route("/qr/<patrimonio>", methods=["GET", "POST"])
def qr_form(patrimonio):
    """Formulário simples para o técnico via QR (sem login)."""
    machine = Machine.query.filter_by(patrimonio=patrimonio).first()
    if not machine:
        return "Máquina não encontrada", 404

    if request.method == "POST":
        pin = (request.form.get("pin") or "").strip()
        if pin != QR_PIN:
            flash("PIN incorreto.", "danger")
            return redirect(url_for("qr_form", patrimonio=patrimonio))

        tecnico = (request.form.get("tecnico") or "").strip() or "Técnico"
        problema = (request.form.get("problema") or "").strip()
        observacoes = (request.form.get("observacoes") or "").strip()

        if not problema:
            flash("Selecione o problema.", "warning")
            return redirect(url_for("qr_form", patrimonio=patrimonio))

        m = Manutencao(
            machine_id=machine.id,
            problema=problema,
            observacoes=observacoes,
            status="Aberto",
            aberto_por=tecnico,
        )
        db.session.add(m)
        db.session.commit()

        return render_template("qr_sucesso.html", machine=machine, manutencao=m)

    return render_template("qr_form.html", machine=machine, problemas=PREDEFINED_PROBLEMAS)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
